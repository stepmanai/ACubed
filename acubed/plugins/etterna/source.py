from __future__ import annotations

import asyncio
import base64
import random
from urllib.parse import urljoin

import httpx

from acubed.domain.chart.types import AssetResponse, ChartRef, Pack
from acubed.domain.game.protocols import ChartSource

from .config import EtternaConfig


class EtternaRemoteSource(ChartSource):
    supports_assets = False

    _MAX_RETRIES = 5
    _DEFAULT_MAX_CONNECTIONS = 64
    _PAGE_CONCURRENCY = 16
    _PACK_PAGE_LIMIT = 5000
    _SONG_PAGE_LIMIT = 1000
    _RETRYABLE_STATUSES = {408, 429, 500, 502, 503, 504}

    def __init__(self, config: EtternaConfig):
        self.config = config
        self._client: httpx.AsyncClient | None = None
        self._pack_cache: dict[str, str] = {}
        self._pack_payload_cache: dict[str, dict] = {}
        self._pack_song_count_cache: dict[str, int] = {}

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
        raise NotImplementedError(
            "Etterna asset download is not implemented yet."
        )

    async def fetch_many(
        self,
        charts: list[ChartRef],
        secrets: dict,
        concurrency: int = 2,
    ) -> list[tuple[ChartRef, AssetResponse]]:
        if not self.supports_assets:
            return []

        sem = asyncio.Semaphore(concurrency)

        async def fetch(chart: ChartRef):
            async with sem:
                result = await self.fetch_assets(chart.id, secrets)
                return chart, result

        return await asyncio.gather(*(fetch(chart) for chart in charts))
