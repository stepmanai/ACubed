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
    _MAX_RETRIES = 5
    _DEFAULT_MAX_CONNECTIONS = 2
    _RETRYABLE_STATUSES = {408, 429, 500, 502, 503, 504}

    def __init__(self, config: EtternaConfig):
        self.config = config
        self._client: httpx.AsyncClient | None = None
        self._pack_cache: dict[str, str] = {}
        self._pack_payload_cache: dict[str, dict] = {}

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(connect=10, read=30, write=30, pool=30),
                limits=httpx.Limits(
                    max_connections=self._DEFAULT_MAX_CONNECTIONS,
                    max_keepalive_connections=self._DEFAULT_MAX_CONNECTIONS,
                ),
            )
        return self._client

    async def close(self):
        if self._client is not None:
            await self._client.aclose()
            self._client = None

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

    async def _request_json(self, url: str):
        client = self._get_client()

        for attempt in range(self._MAX_RETRIES):
            response = None

            try:
                response = await client.get(url)

                if response.status_code in self._RETRYABLE_STATUSES:
                    raise httpx.HTTPStatusError(
                        "Retryable status",
                        request=response.request,
                        response=response,
                    )

                response.raise_for_status()
                return response.json()

            except Exception:
                if attempt == self._MAX_RETRIES - 1:
                    raise

                await asyncio.sleep(self._retry_delay(attempt, response))

    # ------------------------------------------------------------------
    # Packs
    # ------------------------------------------------------------------

    def resolve_pack_name(self, pack_id: str) -> str:
        return self._pack_cache.get(pack_id, f"Etterna Pack {pack_id}")

    def resolve_pack_payload(self, pack_id: str):
        return self._pack_payload_cache.get(pack_id)

    async def fetch_packs(self) -> list[Pack]:
        first = await self._request_json(f"{self.config.base_api_url}/packs")
        last_page = first["meta"]["last_page"]

        packs: list[Pack] = []

        for page in range(1, last_page + 1):
            data = (
                first
                if page == 1
                else await self._request_json(
                    f"{self.config.base_api_url}/packs?page={page}"
                )
            )

            for pack in data["data"]:
                pid = str(pack["id"])

                self._pack_cache[pid] = pack["name"]
                self._pack_payload_cache[pid] = pack

                packs.append(
                    Pack(
                        id=pid,
                        name=pack["name"],
                        raw_payload=pack,
                    )
                )

            await asyncio.sleep(0.25)

        return packs

    async def fetch_pack_charts(self, pack_id: str) -> list[ChartRef]:
        data = await self._request_json(
            f"{self.config.base_api_url}/packs/{pack_id}/songs"
        )

        encoded_pack_name = base64.urlsafe_b64encode(
            self.resolve_pack_name(pack_id).encode("utf-8")
        ).decode("ascii")

        charts: list[ChartRef] = []

        for song in data.get("data", []):
            payload = dict(song)
            payload["encoded_pack_name"] = encoded_pack_name

            charts.append(
                ChartRef(
                    id=str(song["id"]),
                    title=song.get("title", ""),
                    artist=song.get("artist", ""),
                    pack_id=pack_id,
                    raw_payload=payload,
                )
            )

        await asyncio.sleep(0.25)

        return charts

    # ------------------------------------------------------------------
    # Assets
    # ------------------------------------------------------------------

    async def _fetch_chart_info(self, chart_id: str):
        url = urljoin(self.config.base_api_url + "/", f"songs/{chart_id}")
        return await self._request_json(url)

    async def _fetch_chart_data(self, chart_id: str):
        """
        Replace this with the real download endpoint if one exists.

        Currently returns the largest pack name for testing.
        """
        data = await self._fetch_chart_info(chart_id)

        packs = data.get("packs", [])

        if not packs:
            raise ValueError(f"No packs found for chart {chart_id}")

        return max(packs, key=lambda x: x["id"])["name"]

    async def fetch_assets(
        self,
        chart_id: str,
        secrets: dict[str, str] | None = None,
    ) -> AssetResponse:

        for attempt in range(self._MAX_RETRIES):
            try:
                info_task = asyncio.create_task(
                    self._fetch_chart_info(chart_id)
                )

                chart_task = asyncio.create_task(
                    self._fetch_chart_data(chart_id)
                )

                info, chart = await asyncio.gather(
                    info_task,
                    chart_task,
                )

                return AssetResponse(
                    metadata=info,
                    raw_chart=chart,
                    raw_payload={
                        **info,
                        "chart": chart,
                    },
                )

            except Exception:
                if attempt == self._MAX_RETRIES - 1:
                    raise

                await asyncio.sleep(self._retry_delay(attempt))

    # ------------------------------------------------------------------
    # Batch
    # ------------------------------------------------------------------

    async def fetch_many(
        self,
        charts: list[ChartRef],
        secrets: dict,
        concurrency: int = 2,
    ) -> list[tuple[ChartRef, AssetResponse]]:

        semaphore = asyncio.Semaphore(concurrency)

        async def fetch(chart: ChartRef):
            async with semaphore:
                assets = await self.fetch_assets(chart.id, secrets)
                return chart, assets

        return await asyncio.gather(*(fetch(chart) for chart in charts))
