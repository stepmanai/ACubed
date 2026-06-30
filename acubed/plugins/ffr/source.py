# plugins/ffr/source.py

from __future__ import annotations

import asyncio
import random

import httpx
from tqdm import tqdm

from acubed.domain.chart.types import AssetResponse, ChartRef, Pack
from acubed.domain.game.protocols import ChartSource

from .config import FFRConfig


class FFRRemoteSource(ChartSource):
    _MAX_RETRIES = 10
    _MAX_CONNECTIONS = 100
    _RETRYABLE_STATUSES = {408, 429, 500, 502, 503, 504}

    def __init__(self, config: FFRConfig):
        self.config = config
        self._client: httpx.AsyncClient | None = None
        self._collection_payloads: dict[str, dict] = {}

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

            limits = httpx.Limits(
                max_connections=self._MAX_CONNECTIONS,
                max_keepalive_connections=self._MAX_CONNECTIONS,
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
    async def fetch_packs(self) -> list[Pack]:

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
    async def fetch_pack_charts(self, pack_id: str) -> list[ChartRef]:

        client = self._get_client()

        response = await client.get(self.config.playlist_url)
        response.raise_for_status()

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

    def _retry_delay(
        self,
        attempt: int,
        response: httpx.Response | None = None,
    ) -> float:
        if response is not None and response.status_code == 429:
            retry_after = response.headers.get("retry-after")
            if retry_after:
                try:
                    return max(float(retry_after), 0.1)
                except ValueError:
                    pass

        return min(2**attempt, 30) + random.uniform(0.1, 0.5)

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

        for attempt in range(self._MAX_RETRIES):
            response: httpx.Response | None = None
            try:
                response = await client.get(
                    self.config.base_api_url,
                    params={
                        **secrets,
                        "action": "chart",
                        "level": chart_id,
                    },
                )

                if response.status_code in self._RETRYABLE_STATUSES:
                    raise httpx.HTTPStatusError(
                        f"Retryable HTTP {response.status_code}",
                        request=response.request,
                        response=response,
                    )

                response.raise_for_status()

                payload = response.json()

                return AssetResponse(
                    metadata=payload["info"],
                    raw_chart=payload["chart"],
                    raw_payload=payload,
                )

            except (
                httpx.HTTPError,
                ValueError,
            ) as e:
                if attempt == self._MAX_RETRIES - 1:
                    details = (
                        self._debug_dump(chart_id, response, str(e))
                        if response is not None
                        else str(e)
                    )
                    raise ValueError(
                        f"FAILED chart_id={chart_id} "
                        f"after {self._MAX_RETRIES} retries:\n\n"
                        f"{details}"
                    ) from e

                await asyncio.sleep(self._retry_delay(attempt, response))

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
            async with sem:
                result = await self.fetch_assets(chart.id, secrets)
                return chart, result

        tasks = [asyncio.create_task(bounded(chart)) for chart in charts]
        results: list[tuple[ChartRef, AssetResponse]] = []

        try:
            for task in tqdm(
                asyncio.as_completed(tasks),
                total=len(tasks),
                desc="Download FFR charts",
                unit="chart",
            ):
                results.append(await task)
        except Exception:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise

        return results
