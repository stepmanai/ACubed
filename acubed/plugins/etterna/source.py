from __future__ import annotations

import asyncio
import base64
import io
import os
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
from acubed.infrastructure.environment.variables import env_int
from acubed.infrastructure.logging import get_logger

from .config import EtternaConfig


class EtternaRemoteSource(ChartSource):
    supports_assets = True

    _MAX_RETRIES = 5
    _DEFAULT_MAX_CONNECTIONS = env_int(
        "ETTERNA_MAX_CONNECTIONS", 64, minimum=1
    )
    _PAGE_CONCURRENCY = env_int("ETTERNA_PAGE_CONCURRENCY", 16, minimum=1)
    _PACK_PAGE_LIMIT = 5000
    _SONG_PAGE_LIMIT = 1000
    _PACK_ASSET_CONCURRENCY = env_int(
        "ETTERNA_PACK_ASSET_CONCURRENCY",
        4,
        minimum=1,
    )
    _SM_FETCH_CONCURRENCY = env_int(
        "ETTERNA_SM_FETCH_CONCURRENCY",
        6,
        minimum=1,
    )
    _RETRYABLE_STATUSES = {408, 429, 500, 502, 503, 504}
    _ZIP_TAIL_READ_SIZE = 65557
    _LOG_SLOW_PACK_SECONDS = 10.0
    _PROGRESS_LOG_SECONDS = 30.0

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
        self._pack_locks: dict[str, asyncio.Lock] = {}
        self._logger = get_logger()

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(connect=5, read=15, write=15, pool=15),
                limits=httpx.Limits(
                    max_connections=self._DEFAULT_MAX_CONNECTIONS,
                    max_keepalive_connections=self._DEFAULT_MAX_CONNECTIONS,
                ),
            )
        return self._client

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None

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

        for attempt in range(self._MAX_RETRIES):
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
                if attempt == self._MAX_RETRIES - 1:
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
            sem = asyncio.Semaphore(self._PAGE_CONCURRENCY)

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
        for attempt in range(self._MAX_RETRIES):
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
                if attempt == self._MAX_RETRIES - 1:
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
        sem = asyncio.Semaphore(self._SM_FETCH_CONCURRENCY)

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
            if os.getenv("ETTERNA_ALLOW_FULL_ZIP_FALLBACK") == "1":
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

    async def fetch_packs(self) -> list[Pack]:
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

    async def fetch_pack_charts(self, pack_id: str) -> list[ChartRef]:
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

    async def stream_many(
        self,
        charts: list[ChartRef],
        secrets: dict,
        concurrency: int = 2,
    ):
        if not self.supports_assets:
            return

        charts_by_pack: dict[str, list[ChartRef]] = defaultdict(list)
        for chart in charts:
            charts_by_pack[chart.pack_id].append(chart)

        sem = asyncio.Semaphore(
            max(min(concurrency, self._PACK_ASSET_CONCURRENCY), 1)
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
                "ETTERNA_PROGRESS_LOG_SECONDS",
                self._PROGRESS_LOG_SECONDS,
            )
        )
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
