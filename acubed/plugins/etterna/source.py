from __future__ import annotations

import asyncio
import random
from urllib.parse import urljoin

import httpx

from acubed.domain.chart.types import AssetResponse, ChartRef, Pack
from acubed.domain.game.protocols import ChartSource

from .config import EtternaConfig


class EtternaRemoteSource(ChartSource):
    def __init__(self, config: EtternaConfig):
        self.config = config
        self._client: httpx.AsyncClient | None = None
        self._mapset_cache: dict[str, str] = {}
        self._mapset_payload_cache: dict[str, dict] = {}

    # -------------------------
    # client lifecycle
    # -------------------------
    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            timeout = httpx.Timeout(
                connect=5.0,
                read=10.0,
                write=10.0,
                pool=10.0,
            )

            limits = httpx.Limits(
                max_connections=20,
                max_keepalive_connections=10,
            )

            self._client = httpx.AsyncClient(
                timeout=timeout,
                limits=limits,
            )

        return self._client

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None

    def resolve_pack_name(self, pack_id: str) -> str:
        return self._mapset_cache.get(pack_id, f"Etterna Mapset {pack_id}")

    def resolve_pack_payload(self, pack_id: str):
        return self._mapset_payload_cache.get(pack_id)

    # -------------------------
    # request helpers
    # -------------------------
    async def _request_json(self, client: httpx.AsyncClient, url: str):
        for attempt in range(5):
            try:
                resp = await asyncio.wait_for(client.get(url), timeout=15)
                resp.raise_for_status()

                if not resp.content:
                    raise ValueError(f"EMPTY RESPONSE: {url}")

                return resp.json()

            except (TimeoutError, httpx.HTTPError, ValueError):
                if attempt == 4:
                    raise
                await asyncio.sleep((2**attempt) + random.uniform(0.1, 0.5))

    async def _request_content(self, client: httpx.AsyncClient, url: str):
        for attempt in range(5):
            try:
                resp = await asyncio.wait_for(client.get(url), timeout=15)
                resp.raise_for_status()

                if not resp.content:
                    raise ValueError(f"EMPTY RESPONSE: {url}")

                return resp.content

            except (TimeoutError, httpx.HTTPError, ValueError):
                if attempt == 4:
                    raise
                await asyncio.sleep((2**attempt) + random.uniform(0.1, 0.5))

    # -------------------------
    # packs (NO hydration here)
    # -------------------------
    async def fetch_packs(self) -> list[Pack]:
        client = self._get_client()

        url = urljoin(
            self.config.base_api_url, "packs?limit=1&sort=-popularity"
        )
        data = await self._request_json(client, url)
        print(data["meta"])
        # IMPORTANT: Pack is just an ID carrier
        return [
            Pack(
                id=str(mapset_id),
                name=self.resolve_pack_name(
                    str(mapset_id)
                ),  # safe fallback only
            )
            for mapset_id in data["mapsets"]
        ]

    # -------------------------
    # pack charts (hydration happens here)
    # -------------------------
    async def fetch_pack_charts(self, pack_id: str) -> list[ChartRef]:
        client = self._get_client()

        url = urljoin(self.config.base_api_url, f"v1/mapsets/{pack_id}")
        data = await self._request_json(client, url)

        mapset = data["mapset"]
        self._mapset_payload_cache[pack_id] = data

        # SINGLE SOURCE OF TRUTH UPDATE
        self._mapset_cache[pack_id] = mapset.get(
            "title",
            f"Etterna Mapset {pack_id}",
        )

        return [
            ChartRef(
                id=str(m["id"]),
                title=m["title"],
                artist=m["artist"],
                pack_id=pack_id,
                raw_payload=m,
            )
            for m in mapset["maps"]
        ]

    # -------------------------
    # assets
    # -------------------------
    async def _fetch_chart_info(
        self, client: httpx.AsyncClient, chart_id: str
    ):
        url = urljoin(self.config.base_api_url, f"v1/maps/{chart_id}")
        return await self._request_json(client, url)

    async def _fetch_chart_data(
        self, client: httpx.AsyncClient, chart_id: str
    ):
        url = urljoin(self.config.base_api_url, f"d/web/map/{chart_id}")
        return await self._request_content(client, url)

    async def fetch_assets(
        self,
        chart_id: str,
        secrets: dict[str, str] | None = None,
    ) -> AssetResponse:
        client = self._get_client()

        for attempt in range(10):
            try:
                info_task = asyncio.create_task(
                    self._fetch_chart_info(client, chart_id)
                )
                chart_task = asyncio.create_task(
                    self._fetch_chart_data(client, chart_id)
                )

                info, chart_bytes = await asyncio.gather(info_task, chart_task)

                if not chart_bytes:
                    raise ValueError(f"EMPTY CHART {chart_id}")

                return AssetResponse(
                    metadata=info,
                    raw_chart=chart_bytes,
                    raw_payload={**info, "chart": chart_bytes},
                )

            except (TimeoutError, httpx.HTTPError, ValueError):
                if attempt == 9:
                    raise
                await asyncio.sleep((2**attempt) + random.uniform(0.1, 0.5))

    # -------------------------
    # concurrency
    # -------------------------
    async def fetch_many(
        self,
        charts: list[ChartRef],
        secrets: dict,
        concurrency: int = 8,
    ) -> list[tuple[ChartRef, AssetResponse]]:

        self._get_client()
        sem = asyncio.Semaphore(concurrency)

        queue = asyncio.Queue()
        for chart in charts:
            queue.put_nowait(chart)

        results: list[tuple[ChartRef, AssetResponse]] = []

        async def worker():
            while True:
                try:
                    chart = queue.get_nowait()
                except asyncio.QueueEmpty:
                    return

                async with sem:
                    await asyncio.sleep(random.uniform(0.02, 0.1))

                    result = await self.fetch_assets(
                        chart.id,
                        secrets,
                    )

                    results.append((chart, result))

                queue.task_done()

        workers = [asyncio.create_task(worker()) for _ in range(concurrency)]

        await asyncio.gather(*workers)

        return results
