# plugins/ffr/source.py

from __future__ import annotations

import httpx

from acubed.application.ingestion.async_utils import iter_completed_bounded
from acubed.domain.chart.types import AssetResponse, ChartRef, Pack
from acubed.domain.game.protocols import ChartSource
from acubed.infrastructure.http.retry import RetryPolicy, request_with_retries
from acubed.infrastructure.logging import progress_bar

from .config import FFRConfig


class FFRRemoteSource(ChartSource):
    _RETRYABLE_STATUSES = {408, 429, 500, 502, 503, 504}

    def __init__(self, config: FFRConfig):
        self.config = config
        self._client: httpx.AsyncClient | None = None
        self._collection_payloads: dict[str, dict] = {}
        self._retry_policy = RetryPolicy(
            max_retries=self.config.max_retries,
            retryable_statuses=self._RETRYABLE_STATUSES,
            min_retry_after=0.1,
            retry_value_errors=True,
        )

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
                read=self.config.request_timeout,
                write=30.0,
                pool=30.0,
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

    # -------------------------
    # packs
    # -------------------------
    async def fetch_packs(
        self, secrets: dict[str, str] | None = None
    ) -> list[Pack]:
        del secrets
        return [
            Pack(
                id="ffr_default_engine",
                name="FlashFlashRevolution Engine Playlist",
                raw_payload={
                    "id": "ffr_default_engine",
                    "name": "FlashFlashRevolution Engine Playlist",
                    "playlist_url": self.config.playlist_url,
                },
            )
        ]

    def resolve_pack_payload(self, pack_id: str):
        return self._collection_payloads.get(pack_id)

    # -------------------------
    # pack charts
    # -------------------------
    async def fetch_pack_charts(
        self, pack_id: str, secrets: dict[str, str] | None = None
    ) -> list[ChartRef]:
        del secrets

        client = self._get_client()

        async def request_playlist() -> httpx.Response:
            response = await client.get(self.config.playlist_url)
            if response.status_code not in self._RETRYABLE_STATUSES:
                response.json()
            return response

        response = await request_with_retries(
            request_playlist,
            self._retry_policy,
        )

        playlist = response.json()
        self._collection_payloads[pack_id] = {
            "id": pack_id,
            "playlist_url": str(response.url),
            "songs": playlist,
        }

        charts = []
        for song in playlist:
            charts.append(
                ChartRef(
                    id=str(song["level"]),
                    title=song["name"],
                    artist=song["author"],
                    pack_id=pack_id,
                    raw_payload=song,
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
        response: httpx.Response | None = None

        try:

            async def request_chart() -> httpx.Response:
                nonlocal response
                response = await client.get(
                    self.config.base_api_url,
                    params={
                        **secrets,
                        "action": "chart",
                        "level": chart_id,
                    },
                )

                if response.status_code not in self._RETRYABLE_STATUSES:
                    response.json()

                return response

            response = await request_with_retries(
                request_chart,
                self._retry_policy,
            )
            payload = response.json()

            return AssetResponse(
                metadata=payload["info"],
                raw_chart=payload["chart"],
                raw_payload=payload,
            )

        except (httpx.HTTPError, ValueError) as exc:
            details = (
                self._debug_dump(chart_id, response, str(exc))
                if response is not None
                else str(exc)
            )
            raise ValueError(
                f"FAILED chart_id={chart_id} "
                f"after {self.config.max_retries} retries:\n\n"
                f"{details}"
            ) from exc

    # -------------------------
    # concurrency layer
    # -------------------------
    async def fetch_many(
        self,
        charts: list[ChartRef],
        secrets: dict,
        concurrency: int = 8,
    ) -> list[tuple[ChartRef, AssetResponse]]:

        results: list[tuple[ChartRef, AssetResponse]] = []

        async def fetch_chart(chart: ChartRef):
            result = await self.fetch_assets(chart.id, secrets)
            return chart, result

        completed = iter_completed_bounded(
            charts,
            fetch_chart,
            concurrency=max(
                min(concurrency, self.config.chart_asset_concurrency),
                1,
            ),
        )
        with progress_bar(
            total=len(charts), desc="Downloading source files", unit="chart"
        ) as progress:
            async for result in completed:
                results.append(result)
                progress.update(1)

        return results
