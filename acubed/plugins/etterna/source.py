from __future__ import annotations

import asyncio
import base64
import io
import json
import random
import re
import struct
import time
import zipfile
import zlib
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote, unquote, urljoin, urlsplit, urlunsplit

import httpx

from acubed.application.ingestion.assets import empty_asset_response
from acubed.application.ingestion.async_utils import iter_completed_tasks
from acubed.domain.chart.types import AssetResponse, ChartRef, Pack
from acubed.domain.game.protocols import ChartSource
from acubed.infrastructure.logging import get_logger, progress_bar

from .config import EtternaConfig


class EtternaRemoteSource(ChartSource):
    supports_assets = True

    _PACK_PAGE_LIMIT = 5000
    _SONG_PAGE_LIMIT = 1000
    _RETRYABLE_STATUSES = {408, 429, 500, 502, 503, 504}
    _ZIP_TAIL_READ_SIZE = 65557
    _LOG_SLOW_PACK_SECONDS = 10.0
    _GOOGLE_DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.readonly"
    _GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"

    def __init__(self, config: EtternaConfig):
        self.config = config
        self._client: httpx.AsyncClient | None = None
        self._pack_cache: dict[str, str] = {}
        self._pack_payload_cache: dict[str, dict] = {}
        self._pack_song_count_cache: dict[str, int] = {}
        self._chart_payload_cache: dict[str, dict] = {}
        self._pack_sm_cache: dict[str, dict[str, list[dict]]] = {}
        self._sm_file_cache: dict[tuple[str, str], bytes] = {}
        self._sm_chart_cache: dict[tuple[str, str], bytes] = {}
        self._data_sm_cache: dict[str, list[dict]] | None = None
        self._google_access_token: str | None = None
        self._google_access_token_expires_at = 0.0
        self._pack_locks: dict[str, asyncio.Lock] = {}
        self._logger = get_logger()

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(
                    connect=5,
                    read=self.config.request_timeout,
                    write=15,
                    pool=15,
                ),
                limits=httpx.Limits(
                    max_connections=self.config.max_connections,
                    max_keepalive_connections=self.config.max_connections,
                ),
            )
        return self._client

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None

    @staticmethod
    def _b64url(raw: bytes) -> str:
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

    def _google_credentials(self) -> dict:
        path = self.config.google_credentials_path
        if not path:
            raise ValueError("Etterna Google Drive credentials path is empty.")

        credentials_path = Path(path)
        if not credentials_path.exists():
            raise FileNotFoundError(
                f"Etterna Google Drive credentials not found: {path}"
            )

        return json.loads(credentials_path.read_text(encoding="utf-8"))

    def _google_drive_token(self) -> str:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding

        now = time.time()
        if (
            self._google_access_token
            and now < self._google_access_token_expires_at - 60
        ):
            return self._google_access_token

        credentials = self._google_credentials()
        token_uri = credentials.get("token_uri") or self._GOOGLE_TOKEN_URL
        issued_at = int(now)
        claims = {
            "iss": credentials["client_email"],
            "scope": self._GOOGLE_DRIVE_SCOPE,
            "aud": token_uri,
            "iat": issued_at,
            "exp": issued_at + 3600,
        }
        header = {"alg": "RS256", "typ": "JWT"}
        signing_input = ".".join(
            (
                self._b64url(
                    json.dumps(header, separators=(",", ":")).encode("utf-8")
                ),
                self._b64url(
                    json.dumps(claims, separators=(",", ":")).encode("utf-8")
                ),
            )
        ).encode("ascii")

        private_key = serialization.load_pem_private_key(
            credentials["private_key"].encode("utf-8"),
            password=None,
        )
        signature = private_key.sign(
            signing_input,
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        assertion = (
            f"{signing_input.decode('ascii')}.{self._b64url(signature)}"
        )

        with httpx.Client(
            timeout=self.config.data_archive_timeout,
            follow_redirects=True,
        ) as client:
            response = client.post(
                token_uri,
                data={
                    "grant_type": (
                        "urn:ietf:params:oauth:grant-type:jwt-bearer"
                    ),
                    "assertion": assertion,
                },
            )
            response.raise_for_status()
            payload = response.json()

        self._google_access_token = payload["access_token"]
        self._google_access_token_expires_at = now + int(
            payload.get("expires_in", 3600)
        )
        return self._google_access_token

    def _google_drive_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._google_drive_token()}"}

    def _latest_drive_archive(self) -> dict:
        folder_id = self.config.google_drive_folder_id
        query = (
            f"'{folder_id}' in parents and trashed = false "
            "and mimeType != 'application/vnd.google-apps.folder'"
        )
        params = {
            "q": query,
            "fields": (
                "files(id,name,mimeType,size,modifiedTime),nextPageToken"
            ),
            "pageSize": 1000,
            "orderBy": "modifiedTime desc",
            "supportsAllDrives": "true",
            "includeItemsFromAllDrives": "true",
        }

        files: list[dict] = []
        with httpx.Client(
            timeout=self.config.data_archive_timeout,
            follow_redirects=True,
        ) as client:
            while True:
                response = client.get(
                    "https://www.googleapis.com/drive/v3/files",
                    headers=self._google_drive_headers(),
                    params=params,
                )
                response.raise_for_status()
                payload = response.json()
                files.extend(payload.get("files", []))
                page_token = payload.get("nextPageToken")
                if not page_token:
                    break
                params["pageToken"] = page_token

        archives = [
            file
            for file in files
            if str(file.get("name") or "").casefold().endswith(".zip")
        ]
        if not archives:
            raise ValueError(
                "No .zip files were found in the configured Etterna "
                "Google Drive folder."
            )

        return max(
            archives,
            key=lambda file: str(file.get("modifiedTime") or ""),
        )

    @staticmethod
    def _safe_cache_name(name: str) -> str:
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
        return safe or "etterna_data.zip"

    def _data_cache_paths(
        self, archive: dict
    ) -> tuple[Path, Path, Path, Path]:
        cache_root = Path(self.config.data_cache_dir)
        archive_name = self._safe_cache_name(str(archive.get("name") or ""))
        archive_path = cache_root / archive_name
        extract_dir = cache_root / archive_path.stem
        index_path = extract_dir / ".acubed_sm_index.json"
        complete_marker = extract_dir / ".acubed_complete"
        return archive_path, extract_dir, index_path, complete_marker

    def _download_drive_archive_to_cache(
        self,
        archive: dict,
        archive_path: Path,
    ) -> None:
        if archive_path.exists() and archive_path.stat().st_size > 0:
            return

        archive_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = archive_path.with_suffix(archive_path.suffix + ".part")
        file_id = archive["id"]
        total_bytes = int(archive.get("size") or 0)

        with httpx.Client(
            timeout=self.config.data_archive_timeout,
            follow_redirects=True,
        ) as client:
            with client.stream(
                "GET",
                f"https://www.googleapis.com/drive/v3/files/{file_id}",
                headers=self._google_drive_headers(),
                params={
                    "alt": "media",
                    "supportsAllDrives": "true",
                },
            ) as response:
                response.raise_for_status()
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

    def _safe_cache_target(self, extract_dir: Path, member_name: str) -> Path:
        root = extract_dir.resolve()
        target = (extract_dir / member_name).resolve()
        if root not in target.parents and target != root:
            raise ValueError(
                f"Unsafe Etterna archive member path: {member_name}"
            )
        return target

    def _load_data_sm_index(self, index_path: Path) -> dict[str, list[dict]]:
        data = json.loads(index_path.read_text(encoding="utf-8"))
        return {
            key: list(value)
            for key, value in data.items()
            if isinstance(value, list)
        }

    def _write_data_sm_index(
        self,
        index_path: Path,
        index: dict[str, list[dict]],
    ) -> None:
        index_path.write_text(
            json.dumps(index, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )

    def _extract_drive_archive_to_cache(
        self,
        archive_path: Path,
        extract_dir: Path,
        index_path: Path,
        complete_marker: Path,
    ) -> dict[str, list[dict]]:
        if complete_marker.exists() and index_path.exists():
            return self._load_data_sm_index(index_path)

        extract_dir.mkdir(parents=True, exist_ok=True)
        index: dict[str, list[dict]] = {}
        with zipfile.ZipFile(archive_path) as archive:
            entries = [
                entry for entry in archive.infolist() if not entry.is_dir()
            ]
            progress = progress_bar(
                total=len(entries),
                desc="Extracting source cache",
                unit="file",
            )
            try:
                for entry in entries:
                    progress.update(1)
                    path = Path(entry.filename)
                    if not path.name.casefold().endswith(".sm"):
                        continue

                    target = self._safe_cache_target(
                        extract_dir,
                        entry.filename,
                    )
                    target.parent.mkdir(parents=True, exist_ok=True)

                    with archive.open(entry) as source:
                        raw = source.read()
                    target.write_bytes(raw)

                    self._index_sm_file(
                        index,
                        path.name,
                        path.parent.name,
                        self._sm_metadata(raw),
                        source_path=entry.filename,
                        notes_blocks=self._sm_notes_blocks(self._sm_text(raw)),
                        local_path=str(target),
                    )
            finally:
                progress.close()

        self._write_data_sm_index(index_path, index)
        complete_marker.write_text(str(time.time()), encoding="utf-8")
        return index

    async def _data_sm_files(self) -> dict[str, list[dict]]:
        if self._data_sm_cache is not None:
            return self._data_sm_cache

        loop = asyncio.get_running_loop()
        archive = await loop.run_in_executor(None, self._latest_drive_archive)
        archive_path, extract_dir, index_path, complete_marker = (
            self._data_cache_paths(archive)
        )
        await loop.run_in_executor(
            None,
            self._download_drive_archive_to_cache,
            archive,
            archive_path,
        )
        self._data_sm_cache = await loop.run_in_executor(
            None,
            self._extract_drive_archive_to_cache,
            archive_path,
            extract_dir,
            index_path,
            complete_marker,
        )
        return self._data_sm_cache

    def _retry_delay(
        self, attempt: int, response: httpx.Response | None = None
    ) -> float:
        if response is not None and response.status_code == 429:
            ra = response.headers.get("retry-after")
            if ra:
                try:
                    return max(float(ra), 0.5)
                except ValueError:
                    pass
        return min(2**attempt, 30) + random.uniform(0.1, 0.5)

    async def _request_json(self, path: str, params: dict | None = None):
        client = self._get_client()
        url = urljoin(f"{self.config.base_api_url.rstrip('/')}/", path)

        for attempt in range(self.config.max_retries):
            response = None
            try:
                response = await client.get(url, params=params)
                if response.status_code in self._RETRYABLE_STATUSES:
                    raise httpx.HTTPStatusError(
                        "retry",
                        request=response.request,
                        response=response,
                    )
                response.raise_for_status()
                if not response.content:
                    raise ValueError(f"EMPTY RESPONSE: {url}")
                return response.json()
            except (TimeoutError, httpx.HTTPError, ValueError):
                if attempt == self.config.max_retries - 1:
                    raise
                await asyncio.sleep(self._retry_delay(attempt, response))

        raise RuntimeError(f"Unreachable retry state: {url}")

    async def _fetch_paginated(
        self,
        path: str,
        *,
        limit: int | None = None,
    ) -> list[dict]:
        base_params = {"limit": limit} if limit is not None else None
        first = await self._request_json(path, params=base_params)
        pages = [first]
        last_page = int(first.get("meta", {}).get("last_page", 1) or 1)

        if last_page > 1:
            sem = asyncio.Semaphore(self.config.page_concurrency)

            async def fetch_page(page: int):
                async with sem:
                    params = {"page": page}
                    if limit is not None:
                        params["limit"] = limit
                    return await self._request_json(
                        path,
                        params=params,
                    )

            pages.extend(
                await asyncio.gather(
                    *(fetch_page(page) for page in range(2, last_page + 1))
                )
            )

        rows = []
        for page in pages:
            rows.extend(page.get("data", []))
        return rows

    def resolve_pack_name(self, pack_id: str) -> str:
        return self._pack_cache.get(pack_id, f"Etterna Pack {pack_id}")

    def resolve_pack_payload(self, pack_id: str):
        return self._pack_payload_cache.get(pack_id)

    @staticmethod
    def _normalize_lookup_name(value: str | None) -> str:
        if not value:
            return ""

        value = Path(value).stem
        value = value.casefold()
        value = re.sub(r"[^a-z0-9]+", "", value)
        return value

    def _pack_download_url(self, pack_id: str) -> str:
        payload = self._pack_payload_cache.get(pack_id) or {}
        return self._safe_download_url(str(payload.get("download") or ""))

    @staticmethod
    def _safe_download_url(url: str) -> str:
        if not url:
            return ""

        parts = urlsplit(url)
        path = quote(unquote(parts.path), safe="/")
        query = quote(unquote(parts.query), safe="=&?")
        return urlunsplit(
            (
                parts.scheme,
                parts.netloc,
                path,
                query,
                parts.fragment,
            )
        )

    async def _download_pack_zip(self, url: str) -> bytes:
        response = await self._download_request("GET", url)
        return response.content

    async def _content_length(self, url: str) -> int:
        response = await self._download_request("HEAD", url)
        return int(response.headers["content-length"])

    async def _request_range(self, url: str, start: int, end: int) -> bytes:
        response = await self._download_request(
            "GET",
            url,
            headers={"Range": f"bytes={start}-{end}"},
        )
        if response.status_code != 206:
            raise ValueError(f"Range requests are not supported by {url}")
        return response.content

    async def _download_request(
        self,
        method: str,
        url: str,
        **kwargs,
    ) -> httpx.Response:
        response = None
        for attempt in range(self.config.max_retries):
            try:
                response = await self._get_client().request(
                    method,
                    url,
                    **kwargs,
                )
                if response.status_code in self._RETRYABLE_STATUSES:
                    raise httpx.HTTPStatusError(
                        "retry",
                        request=response.request,
                        response=response,
                    )
                response.raise_for_status()
                return response
            except (TimeoutError, httpx.HTTPError):
                if attempt == self.config.max_retries - 1:
                    raise
                await asyncio.sleep(self._retry_delay(attempt, response))

        raise RuntimeError(f"Unreachable retry state: {url}")

    async def _zip_central_directory(self, url: str) -> bytes:
        size = await self._content_length(url)
        tail_start = max(size - self._ZIP_TAIL_READ_SIZE, 0)
        tail = await self._request_range(url, tail_start, size - 1)

        eocd_index = tail.rfind(b"PK\x05\x06")
        if eocd_index < 0:
            raise ValueError("ZIP end-of-central-directory record not found.")

        eocd = tail[eocd_index : eocd_index + 22]
        if len(eocd) < 22:
            raise ValueError("Incomplete ZIP end-of-central-directory record.")

        (
            _signature,
            _disk_number,
            _cd_start_disk,
            _disk_entries,
            _total_entries,
            cd_size,
            cd_offset,
            _comment_len,
        ) = struct.unpack("<4s4H2LH", eocd)
        if cd_size == 0xFFFFFFFF or cd_offset == 0xFFFFFFFF:
            raise ValueError("ZIP64 central directory is not supported.")

        return await self._request_range(
            url,
            cd_offset,
            cd_offset + cd_size - 1,
        )

    @staticmethod
    def _zip64_values(
        extra: bytes,
        *,
        compressed_size: int,
        uncompressed_size: int,
        local_header_offset: int,
    ) -> tuple[int, int, int]:
        values = {
            "compressed_size": compressed_size,
            "uncompressed_size": uncompressed_size,
            "local_header_offset": local_header_offset,
        }
        index = 0
        while index + 4 <= len(extra):
            header_id, data_size = struct.unpack_from("<HH", extra, index)
            index += 4
            data = extra[index : index + data_size]
            index += data_size
            if header_id != 0x0001:
                continue

            offset = 0
            for key in (
                "uncompressed_size",
                "compressed_size",
                "local_header_offset",
            ):
                if values[key] != 0xFFFFFFFF:
                    continue
                if offset + 8 > len(data):
                    break
                values[key] = struct.unpack_from("<Q", data, offset)[0]
                offset += 8

        return (
            values["compressed_size"],
            values["uncompressed_size"],
            values["local_header_offset"],
        )

    async def _zip_sm_entries(self, url: str) -> list[dict]:
        directory = await self._zip_central_directory(url)
        entries = []
        index = 0
        while index + 46 <= len(directory):
            if directory[index : index + 4] != b"PK\x01\x02":
                raise ValueError("Invalid ZIP central directory entry.")

            fields = struct.unpack_from("<4s6H3L5H2L", directory, index)
            (
                _signature,
                _version_made_by,
                _version_needed,
                flags,
                method,
                _mtime,
                _mdate,
                _crc,
                compressed_size,
                uncompressed_size,
                name_len,
                extra_len,
                comment_len,
                _disk_start,
                _internal_attrs,
                _external_attrs,
                local_header_offset,
            ) = fields
            index += 46

            raw_name = directory[index : index + name_len]
            index += name_len
            extra = directory[index : index + extra_len]
            index += extra_len + comment_len

            name = raw_name.decode(
                "utf-8" if flags & 0x800 else "cp437",
                errors="replace",
            )
            if not name.casefold().endswith(".sm"):
                continue

            (
                compressed_size,
                uncompressed_size,
                local_header_offset,
            ) = self._zip64_values(
                extra,
                compressed_size=compressed_size,
                uncompressed_size=uncompressed_size,
                local_header_offset=local_header_offset,
            )
            entries.append(
                {
                    "name": name,
                    "method": method,
                    "compressed_size": compressed_size,
                    "uncompressed_size": uncompressed_size,
                    "local_header_offset": local_header_offset,
                }
            )

        return entries

    async def _read_zip_member(self, url: str, entry: dict) -> bytes:
        header_offset = int(entry["local_header_offset"])
        local_header = await self._request_range(
            url,
            header_offset,
            header_offset + 29,
        )
        if local_header[:4] != b"PK\x03\x04":
            raise ValueError("Invalid ZIP local file header.")

        name_len, extra_len = struct.unpack_from("<HH", local_header, 26)
        data_start = header_offset + 30 + name_len + extra_len
        compressed_size = int(entry["compressed_size"])
        raw = await self._request_range(
            url,
            data_start,
            data_start + compressed_size - 1,
        )

        method = int(entry["method"])
        if method == 0:
            return raw
        if method == 8:
            return zlib.decompress(raw, -zlib.MAX_WBITS)

        raise ValueError(f"Unsupported ZIP compression method: {method}")

    def _index_sm_file(
        self,
        index: dict[str, list[dict]],
        file_name: str,
        parent_name: str = "",
        metadata: dict[str, str] | None = None,
        entry: dict | None = None,
        raw: bytes | None = None,
        source_path: str | None = None,
        local_path: str | None = None,
        notes_blocks: list[dict] | None = None,
    ) -> None:
        base_name = Path(file_name).name
        if not base_name.casefold().endswith(".sm"):
            return

        metadata = metadata or {}
        item = {
            "file_name": base_name,
            "source_path": source_path or base_name,
            "metadata": metadata,
            "notes_blocks": notes_blocks or [],
            "entry": entry,
            "raw": raw,
            "local_path": local_path,
        }
        candidates = [
            base_name,
            parent_name,
            metadata.get("title", ""),
            metadata.get("titletranslit", ""),
        ]

        for candidate in candidates:
            normalized = self._normalize_lookup_name(candidate)
            if not normalized:
                continue

            matches = index.setdefault(normalized, [])
            if not any(
                existing.get("source_path") == item["source_path"]
                for existing in matches
            ):
                matches.append(item)

    @staticmethod
    def _sm_text(raw: bytes) -> str:
        for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
            try:
                return raw.decode(encoding)
            except UnicodeDecodeError:
                continue

        return raw.decode("utf-8", errors="ignore")

    @classmethod
    def _sm_metadata(cls, raw: bytes) -> dict[str, str]:
        text = cls._sm_text(raw)

        metadata = {}
        for match in re.finditer(r"#([A-Z0-9]+):([^;]*);", text, re.I):
            key = match.group(1).casefold()
            if key in {"title", "titletranslit", "subtitle", "artist"}:
                metadata[key] = match.group(2).strip()
        return metadata

    @staticmethod
    def _parse_sm_notes_block(block: str) -> dict:
        body = re.sub(r"^#NOTES:\s*", "", block, flags=re.I).rstrip(";")
        fields = []

        for line in body.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if len(fields) < 5 and stripped.endswith(":"):
                fields.append(stripped[:-1].strip())
                continue
            break

        return {
            "chart_type": fields[0] if len(fields) > 0 else "",
            "description": fields[1] if len(fields) > 1 else "",
            "difficulty": fields[2] if len(fields) > 2 else "",
            "meter": fields[3] if len(fields) > 3 else "",
            "radar": fields[4] if len(fields) > 4 else "",
            "raw": block,
        }

    @classmethod
    def _sm_notes_blocks(cls, text: str) -> list[dict]:
        return [
            cls._parse_sm_notes_block(match.group(0))
            for match in re.finditer(r"#NOTES:\s*.*?;", text, re.I | re.S)
        ]

    @staticmethod
    def _difficulty_alias(value: str | None) -> str:
        value = EtternaRemoteSource._normalize_lookup_name(value)
        aliases = {
            "expert": "challenge",
            "heavy": "hard",
            "standard": "medium",
            "basic": "easy",
            "light": "easy",
            "novice": "beginner",
        }
        return aliases.get(value, value)

    @staticmethod
    def _chart_type_keys(chart_type: str | None) -> int | None:
        value = (chart_type or "").casefold()
        if "double" in value:
            return 8
        if "single" in value:
            return 4
        if "solo" in value:
            return 6
        return None

    @staticmethod
    def _float_value(value) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _notes_block_score(self, block: dict, metadata: dict) -> float:
        score = 0.0

        expected_diff = self._difficulty_alias(metadata.get("difficulty_name"))
        block_diff = self._difficulty_alias(block.get("difficulty"))
        if expected_diff and block_diff == expected_diff:
            score += 100.0

        expected_keys = metadata.get("keys")
        block_keys = self._chart_type_keys(block.get("chart_type"))
        if expected_keys is not None and block_keys == expected_keys:
            score += 20.0

        expected_msd = self._float_value(metadata.get("difficulty"))
        block_meter = self._float_value(block.get("meter"))
        if expected_msd is not None and block_meter is not None:
            score += max(0.0, 30.0 - abs(expected_msd - block_meter))

        return score

    def _best_notes_block(
        self,
        blocks: list[dict],
        metadata: dict,
    ) -> dict | None:
        if not blocks:
            return None

        scored = [
            (self._notes_block_score(block, metadata), block)
            for block in blocks
        ]
        scored.sort(key=lambda item: item[0], reverse=True)

        best_score, best_block = scored[0]
        if best_score <= 0:
            return None
        if len(scored) > 1 and best_score == scored[1][0]:
            return None

        return best_block

    def _sm_item_score(self, item: dict, metadata: dict) -> float:
        blocks = item.get("notes_blocks") or []
        best = self._best_notes_block(blocks, metadata)
        if best is None:
            return 0.0

        score = self._notes_block_score(best, metadata)

        item_metadata = item.get("metadata") or {}
        if self._normalize_lookup_name(
            item_metadata.get("title")
        ) == self._normalize_lookup_name(metadata.get("name")):
            score += 10.0

        return score

    def _difficulty_notes_block(
        self,
        text: str,
        metadata: dict,
    ) -> dict | None:
        blocks = self._sm_notes_blocks(text)
        return self._best_notes_block(blocks, metadata)

    def _chart_sm_bytes(
        self,
        raw: bytes,
        metadata: dict,
    ) -> bytes:
        text = self._sm_text(raw)
        block = self._difficulty_notes_block(text, metadata)
        if block is None:
            return b""

        first_notes = re.search(r"#NOTES:", text, re.I)
        header = text[: first_notes.start()].rstrip() if first_notes else ""
        chart_text = f"{header}\n\n{block['raw'].strip()}\n"
        return chart_text.encode("utf-8")

    async def _index_full_pack_zip_sm_files(self, url: str) -> dict[str, str]:
        content = await self._download_pack_zip(url)
        index: dict[str, str] = {}

        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            for entry in archive.infolist():
                if entry.is_dir():
                    continue

                path = Path(entry.filename)
                if not path.name.casefold().endswith(".sm"):
                    continue

                with archive.open(entry) as sm_file:
                    raw = sm_file.read()
                    metadata = self._sm_metadata(raw)
                    notes_blocks = self._sm_notes_blocks(self._sm_text(raw))
                self._index_sm_file(
                    index,
                    path.name,
                    path.parent.name,
                    metadata,
                    raw=raw,
                    source_path=entry.filename,
                    notes_blocks=notes_blocks,
                )

        return index

    async def _index_ranged_pack_zip_sm_files(
        self, url: str
    ) -> dict[str, str]:
        index: dict[str, str] = {}
        sem = asyncio.Semaphore(self.config.sm_fetch_concurrency)

        async def index_entry(entry: dict) -> None:
            path = Path(entry["name"])
            async with sem:
                raw = await self._read_zip_member(url, entry)
                metadata = self._sm_metadata(raw)
                notes_blocks = self._sm_notes_blocks(self._sm_text(raw))
            self._index_sm_file(
                index,
                path.name,
                path.parent.name,
                metadata,
                entry=entry,
                raw=raw,
                source_path=str(entry.get("name") or path.name),
                notes_blocks=notes_blocks,
            )

        await asyncio.gather(
            *(index_entry(entry) for entry in await self._zip_sm_entries(url))
        )

        return index

    async def _index_pack_zip_sm_files(self, url: str) -> dict[str, str]:
        try:
            return await self._index_ranged_pack_zip_sm_files(url)
        except (httpx.HTTPError, ValueError, zlib.error, struct.error):
            if self.config.allow_full_zip_fallback:
                return await self._index_full_pack_zip_sm_files(url)
            raise

    async def _pack_sm_files(self, pack_id: str) -> dict[str, list[dict]]:
        if pack_id in self._pack_sm_cache:
            return self._pack_sm_cache[pack_id]

        lock = self._pack_locks.setdefault(pack_id, asyncio.Lock())
        async with lock:
            if pack_id in self._pack_sm_cache:
                return self._pack_sm_cache[pack_id]

            url = self._pack_download_url(pack_id)
            index = await self._index_pack_zip_sm_files(url) if url else {}

            self._pack_sm_cache[pack_id] = index
            return index

    async def _resolve_sm_item(
        self,
        pack_id: str,
        metadata: dict,
    ) -> dict | None:
        sm_files = await self._pack_sm_files(pack_id)
        if not sm_files:
            return None

        normalized_song = self._normalize_lookup_name(metadata.get("name"))
        candidates = sm_files.get(normalized_song) or []
        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0]

        scored = [
            (self._sm_item_score(item, metadata), item) for item in candidates
        ]
        scored.sort(key=lambda item: item[0], reverse=True)

        best_score, best_item = scored[0]
        if best_score <= 0:
            return None
        if len(scored) > 1 and best_score == scored[1][0]:
            return None

        return best_item

    def _resolve_sm_item_from_index(
        self,
        index: dict[str, list[dict]],
        metadata: dict,
    ) -> dict | None:
        normalized_song = self._normalize_lookup_name(metadata.get("name"))
        candidates = index.get(normalized_song) or []
        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0]

        scored = [
            (self._sm_item_score(item, metadata), item) for item in candidates
        ]
        scored.sort(key=lambda item: item[0], reverse=True)

        best_score, best_item = scored[0]
        if best_score <= 0:
            return None
        if len(scored) > 1 and best_score == scored[1][0]:
            return None

        return best_item

    async def _asset_from_data_cache(
        self,
        chart: ChartRef,
        index: dict[str, list[dict]],
    ) -> tuple[ChartRef, AssetResponse] | None:
        metadata = dict(chart.raw_payload or {})
        metadata.setdefault("id", chart.id)
        item = self._resolve_sm_item_from_index(index, metadata)
        if item is None:
            return None

        raw = await self._read_sm_item(chart.pack_id, item)
        chart_bytes = self._chart_sm_bytes(raw, metadata)
        if not chart_bytes:
            return None

        metadata["source_file_name"] = str(item.get("file_name") or "")
        return chart, AssetResponse(
            metadata=metadata,
            raw_chart=chart_bytes,
            raw_payload={**metadata, "chart": chart_bytes},
        )

    async def _read_sm_item(self, pack_id: str, item: dict) -> bytes:
        source_path = str(
            item.get("source_path") or item.get("file_name") or ""
        )
        cache_key = (pack_id, source_path)
        if source_path and cache_key in self._sm_file_cache:
            return self._sm_file_cache[cache_key]

        raw = item.get("raw")
        if isinstance(raw, bytes):
            if source_path:
                self._sm_file_cache[cache_key] = raw
            return raw

        local_path = item.get("local_path")
        if local_path:
            path = Path(str(local_path))
            if path.exists():
                raw = path.read_bytes()
                if source_path:
                    self._sm_file_cache[cache_key] = raw
                return raw

        entry = item.get("entry")
        if not entry:
            return b""

        url = self._pack_download_url(pack_id)
        raw = await self._read_zip_member(url, entry) if url else b""
        if source_path:
            self._sm_file_cache[cache_key] = raw
        return raw

    async def _resolve_chart_sm(
        self,
        metadata: dict,
    ) -> tuple[str, bytes]:
        chart_id = str(metadata.get("id") or "")
        pack_id = str(metadata.get("pack_id") or "")
        if not chart_id or not pack_id:
            return "", b""

        cache_key = (pack_id, chart_id)
        if cache_key in self._sm_chart_cache:
            item = await self._resolve_sm_item(pack_id, metadata)
            file_name = str(item.get("file_name") or "") if item else ""
            return file_name, self._sm_chart_cache[cache_key]

        item = await self._resolve_sm_item(pack_id, metadata)
        if not item:
            return "", b""

        raw = await self._read_sm_item(pack_id, item)
        chart = self._chart_sm_bytes(raw, metadata)
        self._sm_chart_cache[cache_key] = chart
        return str(item.get("file_name") or ""), chart

    def _difficulty_value(self, difficulty: dict) -> float | None:
        value = difficulty.get("msd")
        if value is None:
            return None

        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _chart_payload(
        self,
        song: dict,
        difficulty: dict,
        pack_id: str,
        encoded_pack_name: str,
    ) -> dict:
        song_id = song.get("id")
        difficulty_id = difficulty.get("id")

        return {
            "id": difficulty_id,
            "_acubed_song_id": str(song_id) if song_id is not None else None,
            "name": song.get("name"),
            "name_translit": song.get("name_translit"),
            "subtitle": song.get("subtitle"),
            "subtitle_translit": song.get("subtitle_translit"),
            "artist": song.get("artist"),
            "artist_translit": song.get("artist_translit"),
            "author": song.get("author"),
            "play_count": song.get("play_count"),
            "min_bpm": song.get("min_bpm"),
            "max_bpm": song.get("max_bpm"),
            "length": song.get("length"),
            "nsfw": song.get("nsfw"),
            "difficulty_name": difficulty.get("name"),
            "difficulty": self._difficulty_value(difficulty),
            "keys": difficulty.get("keys"),
            "pack_id": pack_id,
            "encoded_pack_name": encoded_pack_name,
        }

    async def fetch_packs(
        self, secrets: dict[str, str] | None = None
    ) -> list[Pack]:
        del secrets
        packs = []
        for pack in await self._fetch_paginated(
            "packs",
            limit=self._PACK_PAGE_LIMIT,
        ):
            pid = str(pack["id"])
            name = pack.get("name", f"Etterna Pack {pid}")
            self._pack_cache[pid] = name
            self._pack_payload_cache[pid] = pack
            self._pack_song_count_cache[pid] = int(pack.get("song_count") or 0)

            packs.append(
                Pack(
                    id=pid,
                    name=name,
                    raw_payload=pack,
                )
            )

        return packs

    async def fetch_pack_charts(
        self, pack_id: str, secrets: dict[str, str] | None = None
    ) -> list[ChartRef]:
        del secrets
        pack_name = self.resolve_pack_name(pack_id)
        song_count = self._pack_song_count_cache.get(pack_id)
        if song_count == 0:
            return []

        limit = (
            min(max(song_count, 1), self._SONG_PAGE_LIMIT)
            if song_count is not None
            else self._SONG_PAGE_LIMIT
        )
        encoded = base64.urlsafe_b64encode(pack_name.encode("utf-8")).decode(
            "ascii"
        )

        charts = []

        for song in await self._fetch_paginated(
            f"packs/{pack_id}/songs",
            limit=limit,
        ):
            title = song.get("title") or song.get("name") or ""

            for difficulty in song.get("difficulties", []):
                difficulty_id = difficulty.get("id")
                if difficulty_id is None:
                    continue

                payload = self._chart_payload(
                    song,
                    difficulty,
                    pack_id,
                    encoded,
                )
                self._chart_payload_cache[str(difficulty_id)] = payload

                charts.append(
                    ChartRef(
                        id=str(difficulty_id),
                        title=title,
                        artist=song.get("artist", ""),
                        pack_id=pack_id,
                        raw_payload=payload,
                    )
                )

        return charts

    async def fetch_assets(
        self,
        chart_id: str,
        secrets: dict[str, str] | None = None,
    ) -> AssetResponse:
        metadata = dict(self._chart_payload_cache.get(chart_id, {}))
        metadata.setdefault("id", chart_id)

        file_name, chart = await self._resolve_chart_sm(metadata)
        metadata["source_file_name"] = file_name

        return AssetResponse(
            metadata=metadata,
            raw_chart=chart,
            raw_payload={**metadata, "chart": chart},
        )

    async def fetch_many(
        self,
        charts: list[ChartRef],
        secrets: dict,
        concurrency: int = 2,
    ) -> list[tuple[ChartRef, AssetResponse]]:
        if not self.supports_assets:
            return []

        results: list[tuple[ChartRef, AssetResponse]] = []
        async for batch in self.stream_many(charts, secrets, concurrency):
            results.extend(batch)
        return results

    async def _fetch_pack_assets(
        self,
        pack_id: str,
        charts: list[ChartRef],
        secrets: dict,
    ) -> list[tuple[ChartRef, AssetResponse]]:
        started = time.perf_counter()
        pack_name = self.resolve_pack_name(pack_id)
        try:
            await self._pack_sm_files(pack_id)
            results = []
            for chart in charts:
                results.append(
                    (chart, await self.fetch_assets(chart.id, secrets))
                )
            elapsed = time.perf_counter() - started
            if elapsed >= self._LOG_SLOW_PACK_SECONDS:
                self._logger.info(
                    "Etterna pack %s (%s): extracted %d chart(s) in %.2fs",
                    pack_id,
                    pack_name,
                    len(charts),
                    elapsed,
                )
            return results
        except (
            httpx.HTTPError,
            TimeoutError,
            ValueError,
            zlib.error,
            struct.error,
        ) as exc:
            elapsed = time.perf_counter() - started
            self._logger.warning(
                "Etterna pack %s (%s): failed after %.2fs; "
                "emitting %d blank source row(s): %s",
                pack_id,
                pack_name,
                elapsed,
                len(charts),
                exc,
            )
            return [(chart, empty_asset_response(chart)) for chart in charts]
        finally:
            self._pack_sm_cache.pop(pack_id, None)
            for key in list(self._sm_file_cache):
                if key[0] == pack_id:
                    self._sm_file_cache.pop(key, None)
            for key in list(self._sm_chart_cache):
                if key[0] == pack_id:
                    self._sm_chart_cache.pop(key, None)

    async def _stream_data_cache_assets(
        self,
        charts: list[ChartRef],
        secrets: dict,
        *,
        concurrency: int,
    ):
        index = await self._data_sm_files()
        batch: list[tuple[ChartRef, AssetResponse]] = []
        missing: list[ChartRef] = []
        batch_size = max(self.config.direct_batch_size, 1)

        progress = progress_bar(
            total=len(charts),
            desc="Reading source cache",
            unit="chart",
        )
        try:
            for chart in charts:
                result = await self._asset_from_data_cache(chart, index)
                if result is None:
                    missing.append(chart)
                else:
                    batch.append(result)

                progress.update(1)
                if len(batch) >= batch_size:
                    yield batch
                    batch = []
        finally:
            progress.close()

        if missing and self.config.direct_fallback:
            charts_by_pack: dict[str, list[ChartRef]] = defaultdict(list)
            for chart in missing:
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
            progress = progress_bar(
                total=len(tasks),
                desc="Downloading missing source files",
                unit="pack",
            )
            try:
                async for fallback_batch in iter_completed_tasks(tasks):
                    progress.update(1)
                    batch.extend(fallback_batch)
                    if len(batch) >= batch_size:
                        yield batch
                        batch = []
            finally:
                progress.close()
        else:
            batch.extend(
                (chart, empty_asset_response(chart)) for chart in missing
            )

        if batch:
            yield batch

    async def stream_many(
        self,
        charts: list[ChartRef],
        secrets: dict,
        concurrency: int = 2,
    ):
        if not self.supports_assets:
            return

        asset_mode = self.config.asset_mode
        if asset_mode == "auto":
            asset_mode = (
                "cache"
                if len(charts) >= self.config.data_auto_min_charts
                else "pack"
            )

        if asset_mode in {"cache", "data"}:
            try:
                async for batch in self._stream_data_cache_assets(
                    charts,
                    secrets,
                    concurrency=concurrency,
                ):
                    yield batch
                return
            except (
                FileNotFoundError,
                httpx.HTTPError,
                KeyError,
                ValueError,
                zipfile.BadZipFile,
            ) as exc:
                if not self.config.direct_fallback:
                    raise
                self._logger.warning(
                    "Etterna data cache unavailable; falling back to pack "
                    "ZIP extraction: %s",
                    exc,
                )

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
        heartbeat_seconds = self.config.progress_log_seconds
        async for result in iter_completed_tasks(
            tasks,
            heartbeat_seconds=heartbeat_seconds,
            logger=self._logger,
            heartbeat_message=lambda done, total: (
                "event=source_heartbeat source=etterna "
                "action=extract_pack_assets "
                f"completed_packs={done} total_packs={total} "
                f"pending_packs={total - done}"
            ),
        ):
            yield result
