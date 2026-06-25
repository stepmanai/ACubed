# plugins/ffr/source.py

from __future__ import annotations

import asyncio
import random

import httpx

from acubed.domain.chart.types import AssetResponse, ChartRef, Pack
from acubed.domain.game.protocols import ChartSource

from .config import FFRConfig


class FFRRemoteSource(ChartSource):
    def __init__(self, config: FFRConfig):
        self.config = config
        self._client: httpx.AsyncClient | None = None

    def _debug_dump(
        self, chart_id: str, response: httpx.Response, reason: str
    ) -> str:
        body = response.text or ""
        return "\n".join(
            [
                "[FFR DEBUG FAILURE]",
                f"chart_id: {chart_id}",
                f"reason: {reason}",
                f"status_code: {response.status_code}",
                f"content_type: {response.headers.get('content-type')}",
                f"url: {response.url}",
                f"body_preview:\n{body[:1500]}",
            ]
        )

    # -------------------------
    # client lifecycle
    # -------------------------
    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            timeout = httpx.Timeout(
                connect=20.0,
                read=30.0,
                write=30.0,
                pool=30.0,
            )

            self._client = httpx.AsyncClient(timeout=timeout)

        return self._client

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None

    # -------------------------
    # packs
    # -------------------------
    async def fetch_packs(self) -> list[Pack]:

        return [
            Pack(
                id="ffr_default_engine",
                name="FlashFlashRevolution Engine Playlist",
            )
        ]

    # -------------------------
    # pack charts
    # -------------------------
    async def fetch_pack_charts(self, pack_id: str) -> list[ChartRef]:

        client = self._get_client()

        response = await client.get(self.config.playlist_url)
        response.raise_for_status()

        playlist = response.json()

        charts = []
        for song in playlist:
            charts.append(
                ChartRef(
                    id=str(song["level"]),
                    title=song["name"],
                    artist=song["author"],
                    pack_id=pack_id,
                )
            )

        return charts

    # -------------------------
    # single fetch (with retries)
    # -------------------------
    async def fetch_assets(
        self,
        chart_id: str,
        secrets: dict[str, str] | None = None,
    ) -> AssetResponse:
        client = self._get_client()
        secrets = secrets or {}

        max_retries = 10

        for attempt in range(max_retries):
            try:
                response = await client.get(
                    self.config.base_api_url,
                    params={
                        **secrets,
                        "action": "chart",
                        "level": chart_id,
                    },
                )

                response.raise_for_status()

                payload = response.json()

                return AssetResponse(
                    metadata=payload["info"],
                    raw_chart=payload["chart"],
                )

            except (
                httpx.ConnectTimeout,
                httpx.ReadTimeout,
                httpx.HTTPStatusError,
                ValueError,
            ) as e:
                if attempt == max_retries - 1:
                    raise ValueError(
                        f"FAILED chart_id={chart_id} "
                        f"after {max_retries} retries:\n\n"
                        f"{e}"
                    ) from e

                delay = (2**attempt) + random.uniform(0.1, 0.5)

                await asyncio.sleep(delay)

    # -------------------------
    # concurrency layer
    # -------------------------
    async def fetch_many(
        self,
        charts: list[ChartRef],
        secrets: dict,
        concurrency: int = 8,
    ) -> list[tuple[ChartRef, AssetResponse]]:

        sem = asyncio.Semaphore(concurrency)

        async def bounded(chart: ChartRef):
            await asyncio.sleep(random.uniform(0.05, 0.3))

            async with sem:
                result = await self.fetch_assets(chart.id, secrets)
                return chart, result

        tasks = [bounded(c) for c in charts]

        return await asyncio.gather(*tasks)
