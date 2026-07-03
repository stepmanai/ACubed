from __future__ import annotations

import asyncio
from urllib.parse import urljoin

import httpx

from acubed.application.ingestion.async_utils import gather_bounded
from acubed.domain.chart.types import AssetResponse, ChartRef, Pack
from acubed.domain.game.protocols import ChartSource
from acubed.infrastructure.http.retry import RetryPolicy, request_with_retries

from .config import QuaverConfig


class QuaverRemoteSource(ChartSource):
    _MAX_RETRIES = 5
    _CHART_RETRIES = 10
    _DEFAULT_MAX_CONNECTIONS = 100
    _RETRYABLE_STATUSES = {408, 429, 500, 502, 503, 504}

    def __init__(self, config: QuaverConfig):
        self.config = config
        self._client: httpx.AsyncClient | None = None

        # pack_id -> title cache (lazy hydration store)
        self._mapset_cache: dict[str, str] = {}
        self._mapset_payload_cache: dict[str, dict] = {}
        self._retry_policy = RetryPolicy(
            max_retries=self._MAX_RETRIES,
            retryable_statuses=self._RETRYABLE_STATUSES,
            min_retry_after=0.1,
        )
        self._chart_retry_policy = RetryPolicy(
            max_retries=self._CHART_RETRIES,
            retryable_statuses=self._RETRYABLE_STATUSES,
            min_retry_after=0.1,
        )

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
                max_connections=self._DEFAULT_MAX_CONNECTIONS,
                max_keepalive_connections=self._DEFAULT_MAX_CONNECTIONS,
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

    # -------------------------
    # request helpers
    # -------------------------
    async def _request_json(self, client: httpx.AsyncClient, url: str):
        response = await request_with_retries(
            lambda: client.get(url),
            self._retry_policy,
        )
        return response.json()

    async def _request_content(self, client: httpx.AsyncClient, url: str):
        response = await request_with_retries(
            lambda: client.get(url),
            self._retry_policy,
        )
        if not response.content:
            raise ValueError(f"EMPTY RESPONSE: {url}")

        return response.content

    # -------------------------
    # NAME RESOLUTION LAYER (IMPORTANT)
    # -------------------------
    def resolve_pack_name(self, pack_id: str) -> str:
        """
        Always safe for UI/logging.

        - cached real title if available
        - fallback otherwise
        """
        return self._mapset_cache.get(pack_id, f"Quaver Mapset {pack_id}")

    def resolve_pack_payload(self, pack_id: str):
        return self._mapset_payload_cache.get(pack_id)

    async def _hydrate_mapset(
        self, client: httpx.AsyncClient, pack_id: str
    ) -> str:
        """
        Fetch and cache real title (only once per pack_id).
        """
        if pack_id in self._mapset_cache:
            return self._mapset_cache[pack_id]

        url = urljoin(self.config.base_api_url, f"v1/mapsets/{pack_id}")
        data = await self._request_json(client, url)

        title = data["mapset"].get("title", f"Quaver Mapset {pack_id}")
        self._mapset_cache[pack_id] = title
        return title

    # -------------------------
    # packs (NO hydration here)
    # -------------------------
    async def fetch_packs(
        self, secrets: dict[str, str] | None = None
    ) -> list[Pack]:
        del secrets
        client = self._get_client()

        url = urljoin(self.config.base_api_url, "v1/mapsets/ranked")
        data = await self._request_json(client, url)

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
    async def fetch_pack_charts(
        self, pack_id: str, secrets: dict[str, str] | None = None
    ) -> list[ChartRef]:
        del secrets
        client = self._get_client()

        url = urljoin(self.config.base_api_url, f"v1/mapsets/{pack_id}")
        data = await self._request_json(client, url)

        mapset = data["mapset"]
        self._mapset_payload_cache[pack_id] = data

        # SINGLE SOURCE OF TRUTH UPDATE
        self._mapset_cache[pack_id] = mapset.get(
            "title",
            f"Quaver Mapset {pack_id}",
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

        async def request_pair() -> AssetResponse:
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

        for attempt in range(self._chart_retry_policy.max_retries):
            try:
                return await request_pair()
            except (TimeoutError, httpx.HTTPError, ValueError) as exc:
                if attempt == self._chart_retry_policy.max_retries - 1 or (
                    not isinstance(exc, ValueError)
                    and not self._chart_retry_policy.is_retryable(exc)
                ):
                    raise
                await asyncio.sleep(self._chart_retry_policy.delay(attempt))

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

        async def fetch_chart(chart: ChartRef):
            result = await self.fetch_assets(chart.id, secrets)
            return chart, result

        return await gather_bounded(
            charts,
            fetch_chart,
            concurrency=concurrency,
        )
