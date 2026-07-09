from __future__ import annotations

import asyncio
import io
import re
import tarfile
import time
import zipfile
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urljoin

import httpx

from acubed.application.ingestion.assets import empty_asset_response
from acubed.domain.chart.types import AssetResponse, ChartRef, Pack
from acubed.domain.game.protocols import ChartSource
from acubed.infrastructure.http.retry import RetryPolicy, request_with_retries
from acubed.infrastructure.logging import get_logger, progress_bar

from .config import OsuManiaConfig


class OsuManiaRemoteSource(ChartSource):
    supports_assets = True

    _RETRYABLE_STATUSES = {408, 429, 500, 502, 503, 504}
    _DATA_ARCHIVE_RE = re.compile(
        r"(?P<name>\d{4}_\d{2}_\d{2}_osu_files\.tar\.bz2)"
    )

    def __init__(self, config: OsuManiaConfig):
        self.config = config
        self._client: httpx.AsyncClient | None = None
        self._access_token: str | None = None
        self._access_token_expires_at = 0.0
        self._pack_cache: dict[str, str] = {}
        self._pack_payload_cache: dict[str, dict] = {}
        self._chart_payload_cache: dict[str, dict] = {}
        self._pack_osu_cache: dict[str, dict[str, dict]] = {}
        self._pack_locks: dict[str, asyncio.Lock] = {}
        self._osu_extract_executor: ThreadPoolExecutor | None = None
        self._data_archive_url: str | None = None
        self._direct_download_failures = 0
        self._logger = get_logger()
        self._retry_policy = RetryPolicy(
            max_retries=self.config.max_retries,
            retryable_statuses=self._RETRYABLE_STATUSES,
            retry_non_status_http_errors=True,
        )
        self._direct_retry_policy = RetryPolicy(
            max_retries=self.config.direct_max_retries,
            retryable_statuses=self._RETRYABLE_STATUSES,
            retry_non_status_http_errors=True,
            retry_value_errors=True,
        )

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            timeout = httpx.Timeout(
                connect=10.0,
                read=self.config.request_timeout,
                write=10.0,
                pool=10.0,
            )
            limits = httpx.Limits(
                max_connections=self.config.max_connections,
                max_keepalive_connections=self.config.max_connections,
            )
            self._client = httpx.AsyncClient(timeout=timeout, limits=limits)
        return self._client

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None
        if self._osu_extract_executor:
            self._osu_extract_executor.shutdown(wait=False)
            self._osu_extract_executor = None

    def _get_osu_extract_executor(self) -> ThreadPoolExecutor:
        if self._osu_extract_executor is None:
            self._osu_extract_executor = ThreadPoolExecutor(
                max_workers=self.config.osu_extract_concurrency,
                thread_name_prefix="osumania-osu-extract",
            )
        return self._osu_extract_executor

    def _credentials(
        self,
        secrets: dict[str, str] | None = None,
    ) -> tuple[str, str]:
        secrets = secrets or {}
        client_id = secrets.get("client_id")
        client_secret = secrets.get("client_secret")
        if not client_id or not client_secret:
            raise ValueError(
                "OSU_CLIENT_ID and OSU_CLIENT_SECRET are required for "
                "osu!mania ingestion."
            )
        return client_id, client_secret

    async def _token(self, secrets: dict[str, str] | None = None) -> str:
        now = time.time()
        if self._access_token and now < self._access_token_expires_at - 60:
            return self._access_token

        client_id, client_secret = self._credentials(secrets)
        response = await self._get_client().post(
            self.config.token_url,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "client_credentials",
                "scope": "public",
            },
        )
        response.raise_for_status()
        payload = response.json()
        self._access_token = payload["access_token"]
        self._access_token_expires_at = now + int(payload.get("expires_in", 0))
        return self._access_token

    async def _request(
        self,
        method: str,
        url: str,
        *,
        secrets: dict[str, str] | None = None,
        auth: bool = True,
        **kwargs,
    ) -> httpx.Response:
        headers = dict(kwargs.pop("headers", {}) or {})
        if auth:
            headers["Authorization"] = f"Bearer {await self._token(secrets)}"

        async def request() -> httpx.Response:
            response = await self._get_client().request(
                method,
                url,
                headers=headers,
                **kwargs,
            )

            if response.status_code == 401 and auth:
                self._access_token = None
                raise httpx.HTTPStatusError(
                    "Expired or invalid osu! OAuth token",
                    request=response.request,
                    response=response,
                )

            return response

        return await request_with_retries(request, self._retry_policy)

    async def _request_json(
        self,
        path: str,
        *,
        params: dict | None = None,
        secrets: dict[str, str] | None = None,
    ) -> dict:
        url = urljoin(f"{self.config.base_api_url.rstrip('/')}/", path)
        response = await self._request(
            "GET",
            url,
            params=params,
            secrets=secrets,
        )
        return response.json()

    async def _request_content(
        self,
        url: str,
        *,
        secrets: dict[str, str] | None = None,
        auth: bool = True,
    ) -> bytes:
        response = await self._request(
            "GET",
            url,
            secrets=secrets,
            auth=auth,
            follow_redirects=True,
        )
        return response.content

    async def _latest_data_archive_url(self) -> str:
        if self._data_archive_url is not None:
            return self._data_archive_url

        index_url = f"{self.config.data_base_url}/"
        response = await self._request(
            "GET",
            index_url,
            auth=False,
        )
        archive_names = sorted(
            set(self._DATA_ARCHIVE_RE.findall(response.text)),
            reverse=True,
        )
        if not archive_names:
            raise ValueError(
                f"No osu_files tar.bz2 archives found at {index_url}"
            )

        for archive_name in archive_names:
            archive_url = f"{self.config.data_base_url}/{archive_name}"
            try:
                await self._request("HEAD", archive_url, auth=False)
            except httpx.HTTPStatusError as exc:
                self._logger.warning(
                    "osu!mania data archive unavailable; trying older "
                    "archive: url=%s status=%s",
                    archive_url,
                    exc.response.status_code,
                )
                continue

            self._data_archive_url = archive_url
            self._logger.info(
                "osu!mania data archive selected: url=%s",
                archive_url,
            )
            break

        if self._data_archive_url is None:
            raise ValueError(
                f"No downloadable osu_files tar.bz2 archives found at "
                f"{index_url}"
            )

        return self._data_archive_url

    @staticmethod
    def _strip_tar_bz2(name: str) -> str:
        suffix = ".tar.bz2"
        return name[: -len(suffix)] if name.endswith(suffix) else name

    def _data_cache_paths(self, archive_url: str) -> tuple[Path, Path, Path]:
        cache_root = Path(self.config.data_cache_dir)
        archive_name = archive_url.rsplit("/", 1)[-1]
        archive_path = cache_root / archive_name
        extract_dir = cache_root / self._strip_tar_bz2(archive_name)
        complete_marker = extract_dir / ".acubed_complete"
        return archive_path, extract_dir, complete_marker

    def _download_data_archive_to_cache(
        self,
        archive_url: str,
        archive_path: Path,
    ) -> None:
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = archive_path.with_suffix(archive_path.suffix + ".part")
        started = time.perf_counter()

        with httpx.Client(
            timeout=self.config.data_archive_timeout,
            follow_redirects=True,
        ) as client:
            with client.stream("GET", archive_url) as response:
                response.raise_for_status()
                total_bytes = int(response.headers.get("content-length") or 0)
                progress = progress_bar(
                    total=total_bytes or None,
                    desc="Downloading source cache",
                    unit="B",
                    unit_scale=True,
                    unit_divisor=1024,
                )
                with temp_path.open("wb") as output:
                    try:
                        for chunk in response.iter_bytes(1024 * 1024):
                            output.write(chunk)
                            progress.update(len(chunk))
                    finally:
                        progress.close()

        temp_path.replace(archive_path)
        self._logger.info(
            "osu!mania data archive cached: path=%s bytes=%d "
            "elapsed_seconds=%.2f",
            archive_path,
            archive_path.stat().st_size,
            time.perf_counter() - started,
        )

    def _safe_cache_target(self, extract_dir: Path, member_name: str) -> Path:
        root = extract_dir.resolve()
        target = (extract_dir / member_name).resolve()
        if root not in target.parents and target != root:
            raise ValueError(f"Unsafe data archive member path: {member_name}")
        return target

    def resolve_pack_name(self, pack_id: str) -> str:
        return self._pack_cache.get(pack_id, f"osu!mania Beatmapset {pack_id}")

    def resolve_pack_payload(self, pack_id: str):
        return self._pack_payload_cache.get(pack_id)

    def _pack_name(self, payload: dict) -> str:
        artist = payload.get("artist") or ""
        title = payload.get("title") or f"Beatmapset {payload.get('id')}"
        return f"{artist} - {title}".strip(" -")

    def _pack_limit(self) -> int:
        return self.config.pack_limit

    def _direct_download_concurrency(self, concurrency: int) -> int:
        return max(
            min(
                max(concurrency, 1) * self.config.chart_asset_concurrency,
                self.config.max_connections,
            ),
            1,
        )

    async def fetch_packs(
        self, secrets: dict[str, str] | None = None
    ) -> list[Pack]:
        packs: list[Pack] = []
        cursor_string: str | None = None
        cursor: dict | None = None
        limit = self._pack_limit()

        while True:
            params = {
                "m": "3",
                "s": "ranked",
                "sort": self.config.search_sort,
            }
            if cursor_string:
                params["cursor_string"] = cursor_string
            elif cursor:
                for key, value in cursor.items():
                    params[f"cursor[{key}]"] = value

            data = await self._request_json(
                "beatmapsets/search", params=params, secrets=secrets
            )
            beatmapsets = data.get("beatmapsets") or []
            if not beatmapsets:
                break

            for beatmapset in beatmapsets:
                pack_id = str(beatmapset["id"])
                name = self._pack_name(beatmapset)
                self._pack_cache[pack_id] = name
                self._pack_payload_cache[pack_id] = beatmapset
                packs.append(
                    Pack(
                        id=pack_id,
                        name=name,
                        raw_payload=beatmapset,
                    )
                )
                if limit and len(packs) >= limit:
                    return packs

            cursor_string = data.get("cursor_string")
            cursor = data.get("cursor")
            if not cursor_string and not cursor:
                break

        return packs

    async def _pack_payload(
        self, pack_id: str, secrets: dict[str, str] | None = None
    ) -> dict:
        if pack_id in self._pack_payload_cache:
            return self._pack_payload_cache[pack_id]

        payload = await self._request_json(
            f"beatmapsets/{pack_id}", secrets=secrets
        )
        self._pack_payload_cache[pack_id] = payload
        self._pack_cache[pack_id] = self._pack_name(payload)
        return payload

    def _chart_payload(self, pack: dict, beatmap: dict) -> dict:
        beatmap_id = str(beatmap["id"])
        return {
            "id": beatmap_id,
            "beatmap_id": beatmap_id,
            "_acubed_song_id": str(pack.get("id")),
            "pack_id": str(pack.get("id")),
            "beatmapset_id": str(pack.get("id")),
            "name": pack.get("title"),
            "artist": pack.get("artist"),
            "creator": pack.get("creator"),
            "difficulty_name": beatmap.get("version"),
            "difficulty": beatmap.get("difficulty_rating"),
            "difficulty_rating": beatmap.get("difficulty_rating"),
            "keys": beatmap.get("cs"),
            "mode": beatmap.get("mode"),
            "status": beatmap.get("status"),
            "url": beatmap.get("url"),
            "beatmap": beatmap,
            "beatmapset": {
                key: value for key, value in pack.items() if key != "beatmaps"
            },
        }

    async def fetch_pack_charts(
        self, pack_id: str, secrets: dict[str, str] | None = None
    ) -> list[ChartRef]:
        pack = await self._pack_payload(pack_id, secrets)
        return self._charts_from_pack(pack)

    def _charts_from_pack(self, pack: dict) -> list[ChartRef]:
        pack_id = str(pack.get("id"))
        charts: list[ChartRef] = []

        for beatmap in pack.get("beatmaps") or []:
            if str(beatmap.get("mode") or "").lower() not in {"mania", "3"}:
                continue

            beatmap_id = beatmap.get("id")
            if beatmap_id is None:
                continue

            payload = self._chart_payload(pack, beatmap)
            self._chart_payload_cache[str(beatmap_id)] = payload
            charts.append(
                ChartRef(
                    id=str(beatmap_id),
                    title=pack.get("title") or "",
                    artist=pack.get("artist") or "",
                    pack_id=pack_id,
                    raw_payload=payload,
                )
            )

        return charts

    async def fetch_charts_for_packs(
        self,
        packs: list[Pack],
        secrets: dict[str, str] | None = None,
        concurrency: int = 8,
    ) -> list[ChartRef]:
        charts: list[ChartRef] = []
        missing_packs: list[Pack] = []

        for pack in packs:
            payload = self._pack_payload_cache.get(pack.id)
            if payload and payload.get("beatmaps"):
                charts.extend(self._charts_from_pack(payload))
            else:
                missing_packs.append(pack)

        if not missing_packs:
            self._logger.info(
                "osu!mania chart refs built from search payloads: %d chart(s)",
                len(charts),
            )
            return charts

        sem = asyncio.Semaphore(max(concurrency, 1))

        async def fetch_missing(pack: Pack) -> list[ChartRef]:
            async with sem:
                return await self.fetch_pack_charts(pack.id, secrets)

        tasks = [
            asyncio.create_task(fetch_missing(pack)) for pack in missing_packs
        ]
        for task in asyncio.as_completed(tasks):
            charts.extend(await task)

        self._logger.info(
            "osu!mania chart refs built: %d chart(s), %d beatmapset(s) "
            "hydrated individually",
            len(charts),
            len(missing_packs),
        )
        return charts

    def _osu_metadata(self, raw: bytes) -> dict[str, str]:
        text = raw.decode("utf-8-sig", errors="ignore")
        values: dict[str, str] = {}

        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("["):
                continue
            if ":" not in stripped:
                continue
            key, value = stripped.split(":", 1)
            key = key.strip()
            if key in {
                "BeatmapID",
                "BeatmapSetID",
                "Title",
                "Artist",
                "Version",
                "Mode",
                "CircleSize",
                "OverallDifficulty",
            }:
                values[key] = value.strip()

        return values

    def _osu_item_from_file(self, file_name: str, raw: bytes) -> dict | None:
        metadata = self._osu_metadata(raw)
        if metadata.get("Mode") != "3":
            return None

        return {
            "file_name": file_name,
            "raw": raw,
            "metadata": metadata,
        }

    def _index_osu_item(self, index: dict[str, dict], item: dict) -> None:
        metadata = item["metadata"]
        beatmap_id = metadata.get("BeatmapID")
        if beatmap_id:
            index[f"id:{beatmap_id}"] = item

        version = metadata.get("Version")
        if version:
            index[f"version:{version.casefold()}"] = item

    def _asset_from_cached_osu(
        self,
        chart: ChartRef,
        raw: bytes,
        source_file_name: str,
    ) -> tuple[ChartRef, AssetResponse]:
        metadata = dict(chart.raw_payload or {})
        metadata.setdefault("id", chart.id)
        metadata["source_file_name"] = source_file_name
        return chart, AssetResponse(
            metadata=metadata,
            raw_chart=raw,
            raw_payload={**metadata, "chart": raw},
        )

    async def _yield_data_cache_rows(
        self,
        rows: list[tuple[ChartRef, AssetResponse]],
    ):
        batch_size = max(self.config.direct_batch_size, 1)
        for index in range(0, len(rows), batch_size):
            yield rows[index : index + batch_size]

    async def _stream_existing_data_cache_assets(
        self,
        charts: list[ChartRef],
        secrets: dict[str, str] | None,
        *,
        data_dir: Path,
        direct_concurrency: int,
    ):
        batch_size = max(self.config.direct_batch_size, 1)
        batch: list[tuple[ChartRef, AssetResponse]] = []
        missing: list[ChartRef] = []

        progress = progress_bar(
            total=len(charts),
            desc="Reading source cache",
            unit="chart",
        )
        try:
            for chart in charts:
                path = data_dir / f"{chart.id}.osu"
                if not path.exists():
                    missing.append(chart)
                else:
                    batch.append(
                        self._asset_from_cached_osu(
                            chart,
                            path.read_bytes(),
                            path.name,
                        )
                    )

                progress.update(1)
                if len(batch) >= batch_size:
                    yield batch
                    batch = []
        finally:
            progress.close()

        if missing and self.config.direct_fallback:
            self._logger.info(
                "osu!mania data cache missing %d chart(s); "
                "falling back to direct .osu downloads",
                len(missing),
            )
            async for fallback_batch in self._yield_data_cache_rows(
                await self._fetch_direct_assets(
                    missing,
                    secrets,
                    concurrency=direct_concurrency,
                )
            ):
                yield fallback_batch
        else:
            batch.extend(
                (chart, empty_asset_response(chart)) for chart in missing
            )

        if batch:
            yield batch

    async def _stream_extract_data_cache_assets(
        self,
        charts: list[ChartRef],
        secrets: dict[str, str] | None,
        *,
        archive_path: Path,
        extract_dir: Path,
        complete_marker: Path,
        direct_concurrency: int,
    ):
        chart_by_id = {chart.id: chart for chart in charts}
        missing_ids = set(chart_by_id)
        batch: list[tuple[ChartRef, AssetResponse]] = []
        batch_size = max(self.config.direct_batch_size, 1)
        started = time.perf_counter()

        extract_dir.mkdir(parents=True, exist_ok=True)
        progress = progress_bar(
            total=len(charts),
            desc="Extracting source cache",
            unit="chart",
        )
        try:
            with tarfile.open(archive_path, mode="r:bz2") as archive:
                for member in archive:
                    if member.isdir():
                        self._safe_cache_target(
                            extract_dir,
                            member.name,
                        ).mkdir(parents=True, exist_ok=True)
                        continue
                    if not member.isfile():
                        continue

                    target = self._safe_cache_target(extract_dir, member.name)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    source = archive.extractfile(member)
                    if source is None:
                        continue

                    raw = source.read()
                    target.write_bytes(raw)

                    chart_id = Path(member.name).stem
                    chart = chart_by_id.get(chart_id)
                    if chart is None or chart_id not in missing_ids:
                        continue

                    missing_ids.remove(chart_id)
                    progress.update(1)
                    batch.append(
                        self._asset_from_cached_osu(
                            chart,
                            raw,
                            target.name,
                        )
                    )

                    if len(batch) >= batch_size:
                        yield batch
                        batch = []

            complete_marker.write_text(str(time.time()), encoding="utf-8")
        finally:
            progress.close()

        self._logger.info(
            "osu!mania data archive extracted with streaming assets: "
            "matched=%d missing=%d elapsed_seconds=%.2f dir=%s",
            len(charts) - len(missing_ids),
            len(missing_ids),
            time.perf_counter() - started,
            extract_dir,
        )

        if missing_ids and self.config.direct_fallback:
            missing = [chart_by_id[chart_id] for chart_id in missing_ids]
            self._logger.info(
                "osu!mania data cache missing %d chart(s); "
                "falling back to direct .osu downloads",
                len(missing),
            )
            async for fallback_batch in self._yield_data_cache_rows(
                await self._fetch_direct_assets(
                    missing,
                    secrets,
                    concurrency=direct_concurrency,
                )
            ):
                yield fallback_batch
        else:
            batch.extend(
                (
                    chart_by_id[chart_id],
                    empty_asset_response(chart_by_id[chart_id]),
                )
                for chart_id in missing_ids
            )

        if batch:
            yield batch

    async def _stream_data_cache_assets(
        self,
        charts: list[ChartRef],
        secrets: dict[str, str] | None,
        *,
        direct_concurrency: int,
    ):
        archive_url = await self._latest_data_archive_url()
        archive_path, extract_dir, complete_marker = self._data_cache_paths(
            archive_url
        )
        data_dir = extract_dir / self._strip_tar_bz2(archive_path.name)

        if complete_marker.exists():
            self._logger.info(
                "osu!mania data cache streaming: charts=%d dir=%s "
                "complete=True",
                len(charts),
                data_dir,
            )
            async for batch in self._stream_existing_data_cache_assets(
                charts,
                secrets,
                data_dir=data_dir,
                direct_concurrency=direct_concurrency,
            ):
                yield batch
            return

        if not archive_path.exists():
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                self._get_osu_extract_executor(),
                self._download_data_archive_to_cache,
                archive_url,
                archive_path,
            )

        self._logger.info(
            "osu!mania data cache streaming: charts=%d dir=%s complete=%s",
            len(charts),
            data_dir,
            complete_marker.exists(),
        )

        async for batch in self._stream_extract_data_cache_assets(
            charts,
            secrets,
            archive_path=archive_path,
            extract_dir=extract_dir,
            complete_marker=complete_marker,
            direct_concurrency=direct_concurrency,
        ):
            yield batch

    def _read_osu_item_from_archive(
        self,
        content: bytes,
        entry_name: str,
    ) -> dict | None:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            with archive.open(entry_name) as osu_file:
                raw = osu_file.read()

        return self._osu_item_from_file(Path(entry_name).name, raw)

    async def _index_pack_osu_files(
        self,
        content: bytes,
    ) -> dict[str, dict]:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            entry_names = [
                entry.filename
                for entry in archive.infolist()
                if not entry.is_dir()
                and Path(entry.filename).suffix.casefold() == ".osu"
            ]

        index: dict[str, dict] = {}
        if not entry_names:
            return index

        loop = asyncio.get_running_loop()
        executor = self._get_osu_extract_executor()
        sem = asyncio.Semaphore(self.config.osu_extract_concurrency)

        async def index_entry(entry_name: str) -> None:
            async with sem:
                item = await loop.run_in_executor(
                    executor,
                    self._read_osu_item_from_archive,
                    content,
                    entry_name,
                )
            if item is not None:
                self._index_osu_item(index, item)

        await asyncio.gather(*(index_entry(name) for name in entry_names))
        return index

    async def _download_osz(
        self,
        pack_id: str,
        secrets: dict[str, str] | None,
    ) -> bytes:
        url = (
            f"{self.config.web_base_url.rstrip('/')}/beatmapsets/"
            f"{pack_id}/download?noVideo=1"
        )
        content = await self._request_content(url, secrets=secrets, auth=True)
        if not content.startswith(b"PK"):
            raise ValueError(
                f"osu! beatmapset {pack_id} download returned non-ZIP content"
            )
        return content

    async def _pack_osu_files(
        self,
        pack_id: str,
        secrets: dict[str, str] | None,
    ) -> dict[str, dict]:
        if pack_id in self._pack_osu_cache:
            return self._pack_osu_cache[pack_id]

        lock = self._pack_locks.setdefault(pack_id, asyncio.Lock())
        async with lock:
            if pack_id in self._pack_osu_cache:
                return self._pack_osu_cache[pack_id]

            content = await self._download_osz(pack_id, secrets)
            index = await self._index_pack_osu_files(content)
            self._pack_osu_cache[pack_id] = index
            return index

    async def _fetch_direct_osu(
        self,
        chart_id: str,
        secrets: dict[str, str] | None,
    ) -> bytes:
        url = f"{self.config.web_base_url.rstrip('/')}/osu/{chart_id}"

        async def request_osu() -> httpx.Response:
            response = await self._request(
                "GET",
                url,
                secrets=secrets,
                auth=False,
                follow_redirects=True,
            )
            content = response.content
            if not content:
                raise ValueError(
                    f"Empty .osu response for chart_id={chart_id}"
                )
            normalized = content.lstrip()
            if normalized.startswith(b"\xef\xbb\xbf"):
                normalized = normalized[3:].lstrip()
            if not normalized.startswith(b"osu file format"):
                preview = content[:80].decode("utf-8", errors="replace")
                raise ValueError(
                    f"Non-.osu response for chart_id={chart_id}: {preview!r}"
                )
            return response

        response = await request_with_retries(
            request_osu,
            self._direct_retry_policy,
        )
        return response.content

    async def _fetch_direct_asset(
        self,
        chart: ChartRef,
        secrets: dict[str, str] | None,
    ) -> tuple[ChartRef, AssetResponse]:
        raw = await self._fetch_direct_osu(chart.id, secrets)
        metadata = dict(chart.raw_payload or {})
        metadata.setdefault("id", chart.id)
        metadata["source_file_name"] = f"{chart.id}.osu"
        return chart, AssetResponse(
            metadata=metadata,
            raw_chart=raw,
            raw_payload={**metadata, "chart": raw},
        )

    async def _fetch_direct_asset_or_empty(
        self,
        chart: ChartRef,
        secrets: dict[str, str] | None,
    ) -> tuple[ChartRef, AssetResponse]:
        try:
            return await self._fetch_direct_asset(chart, secrets)
        except (httpx.HTTPError, ValueError) as exc:
            self._direct_download_failures += 1
            if (
                self._direct_download_failures <= 10
                or self._direct_download_failures % 1000 == 0
            ):
                self._logger.warning(
                    "osu!mania direct .osu download failed; "
                    "emitting empty source row: chart_id=%s "
                    "failures=%d error=%s",
                    chart.id,
                    self._direct_download_failures,
                    exc,
                )
            return chart, empty_asset_response(chart)

    async def _fetch_direct_assets(
        self,
        charts: list[ChartRef],
        secrets: dict[str, str] | None,
        *,
        concurrency: int,
    ) -> list[tuple[ChartRef, AssetResponse]]:
        results = []
        async for result in self._iter_completed_windowed(
            charts,
            lambda chart: self._fetch_direct_asset_or_empty(chart, secrets),
            concurrency=concurrency,
        ):
            results.append(result)
        return results

    async def _iter_completed_windowed(
        self,
        items,
        worker,
        *,
        concurrency: int,
        heartbeat_seconds: float = 0,
        heartbeat_message=None,
        progress_desc: str | None = None,
        progress_unit: str = "item",
    ):
        item_iter = iter(items)
        total = len(items)
        completed = 0
        pending = set()
        stop_heartbeat = asyncio.Event()
        progress = (
            progress_bar(
                total=total,
                desc=progress_desc,
                unit=progress_unit,
            )
            if progress_desc
            else None
        )

        def schedule_next() -> None:
            try:
                item = next(item_iter)
            except StopIteration:
                return
            pending.add(asyncio.create_task(worker(item)))

        async def log_heartbeat() -> None:
            if heartbeat_seconds <= 0 or heartbeat_message is None:
                return

            while not stop_heartbeat.is_set():
                try:
                    await asyncio.wait_for(
                        stop_heartbeat.wait(),
                        timeout=heartbeat_seconds,
                    )
                except TimeoutError:
                    self._logger.info(heartbeat_message(completed, total))

        for _ in range(min(max(concurrency, 1), total)):
            schedule_next()

        heartbeat_task = asyncio.create_task(log_heartbeat())
        try:
            while pending:
                done, pending = await asyncio.wait(
                    pending,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in done:
                    yield await task
                    completed += 1
                    if progress is not None:
                        progress.update(1)
                    schedule_next()
        except Exception:
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            raise
        finally:
            stop_heartbeat.set()
            await asyncio.gather(heartbeat_task, return_exceptions=True)
            if progress is not None:
                progress.close()

    def _asset_from_osu_index(
        self,
        chart: ChartRef,
        index: dict[str, dict],
    ) -> AssetResponse | None:
        metadata = dict(chart.raw_payload or {})
        metadata.setdefault("id", chart.id)
        version = str(metadata.get("difficulty_name") or "").casefold()
        item = index.get(f"id:{chart.id}") or index.get(f"version:{version}")
        if item is None:
            return None

        metadata["source_file_name"] = str(item.get("file_name") or "")
        raw = item["raw"]
        return AssetResponse(
            metadata=metadata,
            raw_chart=raw,
            raw_payload={**metadata, "chart": raw},
        )

    async def fetch_assets(
        self,
        chart_id: str,
        secrets: dict[str, str] | None = None,
    ) -> AssetResponse:
        metadata = dict(self._chart_payload_cache.get(chart_id, {}))
        metadata.setdefault("id", chart_id)
        pack_id = str(metadata.get("pack_id") or "")
        version = str(metadata.get("difficulty_name") or "").casefold()
        raw = b""
        file_name = ""

        if pack_id and self.config.asset_mode != "direct":
            index = await self._pack_osu_files(pack_id, secrets)
            item = index.get(f"id:{chart_id}") or index.get(
                f"version:{version}"
            )
            if item:
                raw = item["raw"]
                file_name = str(item.get("file_name") or "")

        if not raw and self.config.direct_fallback:
            raw = await self._fetch_direct_osu(chart_id, secrets)
            file_name = f"{chart_id}.osu"

        metadata["source_file_name"] = file_name
        return AssetResponse(
            metadata=metadata,
            raw_chart=raw,
            raw_payload={**metadata, "chart": raw},
        )

    async def _fetch_pack_assets(
        self,
        pack_id: str,
        charts: list[ChartRef],
        secrets: dict[str, str] | None,
        direct_concurrency: int,
    ) -> list[tuple[ChartRef, AssetResponse]]:
        try:
            index = await self._pack_osu_files(pack_id, secrets)
            results = []
            missing_charts = []
            for chart in charts:
                asset = self._asset_from_osu_index(chart, index)
                if asset is None:
                    missing_charts.append(chart)
                else:
                    results.append((chart, asset))

            if missing_charts and self.config.direct_fallback:
                results.extend(
                    await self._fetch_direct_assets(
                        missing_charts,
                        secrets,
                        concurrency=direct_concurrency,
                    )
                )
            else:
                results.extend(
                    (chart, empty_asset_response(chart))
                    for chart in missing_charts
                )

            return results
        except (httpx.HTTPError, ValueError, zipfile.BadZipFile) as exc:
            if (
                self.config.asset_mode != "direct"
                and self.config.direct_fallback
            ):
                self._logger.info(
                    "osu!mania beatmapset %s (%s): .osz failed; "
                    "falling back to direct .osu download: %s",
                    pack_id,
                    self.resolve_pack_name(pack_id),
                    exc,
                )
                return await self._fetch_direct_assets(
                    charts,
                    secrets,
                    concurrency=direct_concurrency,
                )

            self._logger.warning(
                "osu!mania beatmapset %s (%s): failed; emitting %d blank "
                "source row(s): %s",
                pack_id,
                self.resolve_pack_name(pack_id),
                len(charts),
                exc,
            )
            return [(chart, empty_asset_response(chart)) for chart in charts]
        finally:
            self._pack_osu_cache.pop(pack_id, None)

    async def fetch_many(
        self,
        charts: list[ChartRef],
        secrets: dict,
        concurrency: int = 2,
    ) -> list[tuple[ChartRef, AssetResponse]]:
        results: list[tuple[ChartRef, AssetResponse]] = []
        async for batch in self.stream_many(charts, secrets, concurrency):
            results.extend(batch)
        return results

    async def stream_many(
        self,
        charts: list[ChartRef],
        secrets: dict,
        concurrency: int = 2,
    ):
        direct_concurrency = self._direct_download_concurrency(concurrency)
        asset_mode = self.config.asset_mode
        if asset_mode == "auto":
            asset_mode = (
                "cache"
                if len(charts) >= self.config.data_auto_min_charts
                else "direct"
            )
            self._logger.info(
                "osu!mania auto asset mode selected: mode=%s charts=%d "
                "threshold=%d",
                asset_mode,
                len(charts),
                self.config.data_auto_min_charts,
            )

        if asset_mode == "direct":
            async for batch in self._stream_direct_many(
                charts,
                secrets,
                concurrency,
            ):
                yield batch
            return

        if asset_mode in {"cache", "data"}:
            async for batch in self._stream_data_cache_assets(
                charts,
                secrets,
                direct_concurrency=direct_concurrency,
            ):
                yield batch
            return

        charts_by_pack: dict[str, list[ChartRef]] = defaultdict(list)
        for chart in charts:
            charts_by_pack[chart.pack_id].append(chart)

        async def fetch_pack(
            item: tuple[str, list[ChartRef]],
        ) -> list[tuple[ChartRef, AssetResponse]]:
            pack_id, pack_charts = item
            return await self._fetch_pack_assets(
                pack_id,
                pack_charts,
                secrets,
                direct_concurrency=direct_concurrency,
            )

        pack_items = list(charts_by_pack.items())
        pack_concurrency = max(
            min(concurrency, self.config.pack_asset_concurrency),
            1,
        )
        heartbeat_seconds = self.config.progress_log_seconds
        async for result in self._iter_completed_windowed(
            pack_items,
            fetch_pack,
            concurrency=pack_concurrency,
            heartbeat_seconds=heartbeat_seconds,
            heartbeat_message=lambda done, total: (
                "event=source_heartbeat source=osumania "
                "action=extract_beatmapset_assets "
                f"completed_beatmapsets={done} total_beatmapsets={total} "
                f"pending_beatmapsets={total - done}"
            ),
            progress_desc="Downloading source packs",
            progress_unit="set",
        ):
            yield result

    async def _stream_direct_many(
        self,
        charts: list[ChartRef],
        secrets: dict,
        concurrency: int,
    ):
        chart_concurrency = self._direct_download_concurrency(concurrency)
        direct_batch_size = max(self.config.direct_batch_size, 1)
        heartbeat_seconds = self.config.progress_log_seconds
        batch: list[tuple[ChartRef, AssetResponse]] = []

        async for row in self._iter_completed_windowed(
            charts,
            lambda chart: self._fetch_direct_asset_or_empty(chart, secrets),
            concurrency=chart_concurrency,
            heartbeat_seconds=heartbeat_seconds,
            heartbeat_message=lambda done, total: (
                "event=source_heartbeat source=osumania "
                "action=download_direct_osu "
                f"completed_charts={done} total_charts={total} "
                f"pending_charts={total - done} "
                f"concurrency={chart_concurrency}"
            ),
            progress_desc="Downloading source files",
            progress_unit="chart",
        ):
            batch.append(row)
            if len(batch) >= direct_batch_size:
                yield batch
                batch = []

        if batch:
            yield batch
