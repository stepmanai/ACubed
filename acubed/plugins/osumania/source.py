from __future__ import annotations

import asyncio
import io
import os
import random
import time
import zipfile
from collections import defaultdict
from pathlib import Path
from urllib.parse import urljoin

import httpx

from acubed.domain.chart.types import AssetResponse, ChartRef, Pack
from acubed.domain.game.protocols import ChartSource
from acubed.infrastructure.logging import get_logger

from .config import OsuManiaConfig


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


class OsuManiaRemoteSource(ChartSource):
    supports_assets = True

    _MAX_RETRIES = 5
    _RETRYABLE_STATUSES = {408, 429, 500, 502, 503, 504}
    _PROGRESS_LOG_SECONDS = 30.0

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
        self._logger = get_logger()

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

    def _credentials(
        self,
        secrets: dict[str, str] | None = None,
    ) -> tuple[str, str]:
        secrets = secrets or {}
        client_id = secrets.get("client_id") or os.getenv("OSU_CLIENT_ID")
        client_secret = secrets.get("client_secret") or os.getenv(
            "OSU_CLIENT_SECRET"
        )
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

    def _retry_delay(
        self,
        attempt: int,
        response: httpx.Response | None = None,
    ) -> float:
        if response is not None and response.status_code == 429:
            retry_after = response.headers.get("retry-after")
            if retry_after:
                try:
                    return max(float(retry_after), 0.5)
                except ValueError:
                    pass

        return min(2**attempt, 30) + random.uniform(0.1, 0.5)

    def _is_retryable_exception(self, exc: BaseException) -> bool:
        if isinstance(exc, httpx.HTTPStatusError):
            response = exc.response
            return response.status_code in self._RETRYABLE_STATUSES

        return isinstance(exc, (TimeoutError, httpx.TimeoutException))

    async def _request(
        self,
        method: str,
        url: str,
        *,
        secrets: dict[str, str] | None = None,
        auth: bool = True,
        **kwargs,
    ) -> httpx.Response:
        response: httpx.Response | None = None

        for attempt in range(self._MAX_RETRIES):
            try:
                headers = dict(kwargs.pop("headers", {}) or {})
                if auth:
                    headers["Authorization"] = (
                        f"Bearer {await self._token(secrets)}"
                    )
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

                if response.status_code in self._RETRYABLE_STATUSES:
                    raise httpx.HTTPStatusError(
                        f"Retryable HTTP {response.status_code}: {url}",
                        request=response.request,
                        response=response,
                    )

                response.raise_for_status()
                return response

            except (TimeoutError, httpx.HTTPError) as exc:
                if (
                    attempt == self._MAX_RETRIES - 1
                    or not self._is_retryable_exception(exc)
                ):
                    raise
                await asyncio.sleep(self._retry_delay(attempt, response))

        raise RuntimeError(f"Unreachable retry state: {url}")

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

    def resolve_pack_name(self, pack_id: str) -> str:
        return self._pack_cache.get(pack_id, f"osu!mania Beatmapset {pack_id}")

    def resolve_pack_payload(self, pack_id: str):
        return self._pack_payload_cache.get(pack_id)

    def _pack_name(self, payload: dict) -> str:
        artist = payload.get("artist") or ""
        title = payload.get("title") or f"Beatmapset {payload.get('id')}"
        return f"{artist} - {title}".strip(" -")

    def _pack_limit(self) -> int:
        return max(_env_int("OSUMANIA_PACK_LIMIT", 0), 0)

    async def fetch_packs(self) -> list[Pack]:
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
                "beatmapsets/search", params=params
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

    async def _pack_payload(self, pack_id: str) -> dict:
        if pack_id in self._pack_payload_cache:
            return self._pack_payload_cache[pack_id]

        payload = await self._request_json(f"beatmapsets/{pack_id}")
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

    async def fetch_pack_charts(self, pack_id: str) -> list[ChartRef]:
        pack = await self._pack_payload(pack_id)
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
                return await self.fetch_pack_charts(pack.id)

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

    def _index_osu_file(
        self,
        index: dict[str, dict],
        file_name: str,
        raw: bytes,
    ) -> None:
        metadata = self._osu_metadata(raw)
        if metadata.get("Mode") != "3":
            return

        item = {
            "file_name": file_name,
            "raw": raw,
            "metadata": metadata,
        }
        beatmap_id = metadata.get("BeatmapID")
        if beatmap_id:
            index[f"id:{beatmap_id}"] = item

        version = metadata.get("Version")
        if version:
            index[f"version:{version.casefold()}"] = item

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
                f"osu! beatmapset {pack_id} did not return an .osz ZIP"
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
            index: dict[str, dict] = {}

            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                for entry in archive.infolist():
                    if entry.is_dir():
                        continue
                    path = Path(entry.filename)
                    if path.suffix.casefold() != ".osu":
                        continue
                    with archive.open(entry) as osu_file:
                        raw = osu_file.read()
                    self._index_osu_file(index, path.name, raw)

            self._pack_osu_cache[pack_id] = index
            return index

    async def _fetch_direct_osu(
        self,
        chart_id: str,
        secrets: dict[str, str] | None,
    ) -> bytes:
        url = f"{self.config.web_base_url.rstrip('/')}/osu/{chart_id}"
        return await self._request_content(url, secrets=secrets, auth=False)

    def _empty_asset_response(self, chart: ChartRef) -> AssetResponse:
        metadata = dict(chart.raw_payload or {})
        metadata.setdefault("id", chart.id)
        metadata.setdefault("pack_id", chart.pack_id)
        metadata["source_file_name"] = ""
        return AssetResponse(
            metadata=metadata,
            raw_chart=b"",
            raw_payload={**metadata, "chart": b""},
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
    ) -> list[tuple[ChartRef, AssetResponse]]:
        try:
            results = []
            for chart in charts:
                results.append(
                    (chart, await self.fetch_assets(chart.id, secrets))
                )
            return results
        except (httpx.HTTPError, ValueError, zipfile.BadZipFile) as exc:
            if (
                self.config.asset_mode != "direct"
                and self.config.direct_fallback
            ):
                self._logger.warning(
                    "osu!mania beatmapset %s (%s): .osz failed; "
                    "falling back to direct .osu download: %s",
                    pack_id,
                    self.resolve_pack_name(pack_id),
                    exc,
                )
                results = []
                for chart in charts:
                    try:
                        raw = await self._fetch_direct_osu(chart.id, secrets)
                        metadata = dict(chart.raw_payload or {})
                        metadata["source_file_name"] = f"{chart.id}.osu"
                        results.append(
                            (
                                chart,
                                AssetResponse(
                                    metadata=metadata,
                                    raw_chart=raw,
                                    raw_payload={**metadata, "chart": raw},
                                ),
                            )
                        )
                    except (httpx.HTTPError, ValueError):
                        results.append(
                            (chart, self._empty_asset_response(chart))
                        )
                return results

            self._logger.warning(
                "osu!mania beatmapset %s (%s): failed; emitting %d blank "
                "source row(s): %s",
                pack_id,
                self.resolve_pack_name(pack_id),
                len(charts),
                exc,
            )
            return [
                (chart, self._empty_asset_response(chart)) for chart in charts
            ]
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
        if self.config.asset_mode == "direct":
            async for batch in self._stream_direct_many(
                charts,
                secrets,
                concurrency,
            ):
                yield batch
            return

        charts_by_pack: dict[str, list[ChartRef]] = defaultdict(list)
        for chart in charts:
            charts_by_pack[chart.pack_id].append(chart)

        sem = asyncio.Semaphore(
            max(min(concurrency, self.config.pack_asset_concurrency), 1)
        )

        async def fetch_pack(
            pack_id: str,
            pack_charts: list[ChartRef],
        ) -> list[tuple[ChartRef, AssetResponse]]:
            async with sem:
                return await self._fetch_pack_assets(
                    pack_id,
                    pack_charts,
                    secrets,
                )

        tasks = [
            asyncio.create_task(fetch_pack(pack_id, pack_charts))
            for pack_id, pack_charts in charts_by_pack.items()
        ]
        heartbeat_seconds = float(
            os.getenv(
                "OSUMANIA_PROGRESS_LOG_SECONDS",
                self._PROGRESS_LOG_SECONDS,
            )
        )
        stop_heartbeat = asyncio.Event()

        async def log_heartbeat() -> None:
            if heartbeat_seconds <= 0:
                return

            total = len(tasks)
            while not stop_heartbeat.is_set():
                try:
                    await asyncio.wait_for(
                        stop_heartbeat.wait(),
                        timeout=heartbeat_seconds,
                    )
                except TimeoutError:
                    done = sum(1 for task in tasks if task.done())
                    self._logger.info(
                        "osu!mania asset extraction heartbeat: "
                        "%d/%d beatmapset(s) complete, %d pending",
                        done,
                        total,
                        total - done,
                    )

        heartbeat_task = asyncio.create_task(log_heartbeat())

        try:
            for task in asyncio.as_completed(tasks):
                yield await task
        except Exception:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise
        finally:
            stop_heartbeat.set()
            await asyncio.gather(heartbeat_task, return_exceptions=True)

    async def _stream_direct_many(
        self,
        charts: list[ChartRef],
        secrets: dict,
        concurrency: int,
    ):
        chart_concurrency = max(
            min(
                max(concurrency, 1) * self.config.chart_asset_concurrency,
                self.config.max_connections,
            ),
            1,
        )
        sem = asyncio.Semaphore(chart_concurrency)

        async def fetch_chart(
            chart: ChartRef,
        ) -> tuple[ChartRef, AssetResponse]:
            async with sem:
                try:
                    result = await self.fetch_assets(chart.id, secrets)
                except (httpx.HTTPError, ValueError):
                    result = self._empty_asset_response(chart)
                return chart, result

        tasks = [asyncio.create_task(fetch_chart(chart)) for chart in charts]
        direct_batch_size = max(self.config.direct_batch_size, 1)
        heartbeat_seconds = float(
            os.getenv(
                "OSUMANIA_PROGRESS_LOG_SECONDS",
                self._PROGRESS_LOG_SECONDS,
            )
        )
        stop_heartbeat = asyncio.Event()

        async def log_heartbeat() -> None:
            if heartbeat_seconds <= 0:
                return

            total = len(tasks)
            while not stop_heartbeat.is_set():
                try:
                    await asyncio.wait_for(
                        stop_heartbeat.wait(),
                        timeout=heartbeat_seconds,
                    )
                except TimeoutError:
                    done = sum(1 for task in tasks if task.done())
                    self._logger.info(
                        "osu!mania direct asset heartbeat: "
                        "%d/%d chart(s) complete, %d pending, concurrency=%d",
                        done,
                        total,
                        total - done,
                        chart_concurrency,
                    )

        heartbeat_task = asyncio.create_task(log_heartbeat())

        try:
            batch: list[tuple[ChartRef, AssetResponse]] = []
            for task in asyncio.as_completed(tasks):
                batch.append(await task)
                if len(batch) >= direct_batch_size:
                    yield batch
                    batch = []

            if batch:
                yield batch
        except Exception:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise
        finally:
            stop_heartbeat.set()
            await asyncio.gather(heartbeat_task, return_exceptions=True)
