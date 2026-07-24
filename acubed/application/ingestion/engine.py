from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator

from acubed.domain.chart.types import AssetResponse, ChartRef, Pack
from acubed.domain.game.definition import GameDefinition
from acubed.domain.game.protocols import (
    BulkAssetSource,
    BulkPackChartSource,
    PackNameResolver,
    PackPayloadResolver,
    StreamingAssetSource,
)
from acubed.infrastructure.logging import (
    get_logger,
    log_event,
    progress_bar,
    set_progress_phase,
)

AssetResult = tuple[ChartRef, AssetResponse]


class GameIngestionEngine:
    def __init__(
        self,
        game: GameDefinition,
        secrets: dict[str, str] | None = None,
        concurrency: int = 8,
        skip_source_ids: set[str] | None = None,
    ):
        self.game = game
        self.secrets = secrets or {}
        self.concurrency = concurrency
        self.skip_source_ids = skip_source_ids or set()
        self.logger = get_logger()

    async def _fetch_charts_for_packs(
        self,
        packs: list[Pack],
    ) -> list[ChartRef]:
        source = self.game.source
        if isinstance(source, BulkPackChartSource):
            return list(
                await source.fetch_charts_for_packs(
                    packs,
                    secrets=self.secrets,
                    concurrency=self.concurrency,
                )
            )

        sem = asyncio.Semaphore(self.concurrency)
        charts: list[ChartRef] = []

        async def fetch_pack(pack: Pack) -> tuple[Pack, list[ChartRef]]:
            async with sem:
                return pack, list(
                    await source.fetch_pack_charts(pack.id, self.secrets)
                )

        tasks = [asyncio.create_task(fetch_pack(pack)) for pack in packs]

        for task in progress_bar(
            asyncio.as_completed(tasks),
            total=len(tasks),
            desc="Fetching chart collections",
            unit="pack",
        ):
            pack, pack_charts = await task

            pack_name = (
                source.resolve_pack_name(pack.id)
                if isinstance(source, PackNameResolver)
                else pack.name
            )

            log_event(
                self.logger,
                "pack_charts",
                status="completed",
                pack_id=pack.id,
                pack_name=pack_name,
                charts=len(pack_charts),
            )
            charts.extend(pack_charts)

        return charts

    async def _fetch_assets(
        self,
        charts: list[ChartRef],
    ) -> list[AssetResult]:
        source = self.game.source
        if getattr(source, "supports_assets", True) is False:
            log_event(
                self.logger,
                "asset_fetch",
                status="skipped",
                game_id=self.game.id,
                reason="source_does_not_support_assets",
            )
            return []

        if isinstance(source, BulkAssetSource):
            return await source.fetch_many(
                charts,
                self.secrets,
                concurrency=self.concurrency,
            )

        sem = asyncio.Semaphore(self.concurrency)

        async def fetch_chart(chart: ChartRef):
            async with sem:
                result = await source.fetch_assets(chart.id, self.secrets)
                return chart, result

        tasks = [fetch_chart(chart) for chart in charts]
        results: list[AssetResult] = []

        for coro in progress_bar(
            asyncio.as_completed(tasks),
            total=len(tasks),
            desc="Downloading source files",
            unit="chart",
        ):
            results.append(await coro)

        return results

    async def _stream_assets(
        self,
        charts: list[ChartRef],
    ) -> AsyncIterator[list[AssetResult]]:
        source = self.game.source
        if getattr(source, "supports_assets", True) is False:
            log_event(
                self.logger,
                "asset_fetch",
                status="skipped",
                game_id=self.game.id,
                reason="source_does_not_support_assets",
            )
            return

        if self.skip_source_ids:
            original_count = len(charts)
            charts = [
                chart
                for chart in charts
                if str(chart.id) not in self.skip_source_ids
            ]
            skipped_count = original_count - len(charts)

            if skipped_count:
                log_event(
                    self.logger,
                    "asset_fetch",
                    status="skipping_existing_sources",
                    skipped_assets=skipped_count,
                    remaining_assets=len(charts),
                )

            if not charts:
                log_event(
                    self.logger,
                    "asset_fetch",
                    status="skipped",
                    reason="all_assets_already_have_source_rows",
                )
                return

        if isinstance(source, StreamingAssetSource):
            progress = progress_bar(
                total=len(charts),
                desc="Ingesting source files",
                unit="chart",
            )
            try:
                async for batch in source.stream_many(
                    charts,
                    self.secrets,
                    concurrency=self.concurrency,
                ):
                    progress.update(len(batch))
                    yield batch
            finally:
                progress.close()
            return

        sem = asyncio.Semaphore(self.concurrency)

        async def fetch_chart(chart: ChartRef):
            async with sem:
                result = await source.fetch_assets(chart.id, self.secrets)
                return chart, result

        tasks = [asyncio.create_task(fetch_chart(chart)) for chart in charts]

        try:
            for task in progress_bar(
                asyncio.as_completed(tasks),
                total=len(tasks),
                desc="Downloading source files",
                unit="chart",
            ):
                yield [await task]
        except Exception:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise

    # API parsing is disabled while bronze chart tables are being
    # built.
    # async def _parse_assets(
    #     self,
    #     assets: list[tuple[ChartRef, AssetResponse]],
    # ) -> list[Stepfile]:
    #     sem = asyncio.Semaphore(self.concurrency)
    #
    #     async def parse_asset(asset: tuple[ChartRef, AssetResponse]):
    #         chart, response = asset
    #         async with sem:
    #             loop = asyncio.get_running_loop()
    #             stepfile = await loop.run_in_executor(
    #                 None,
    #                 self.game.parser.parse,
    #                 response,
    #             )
    #             stepfile.source_chart_id = chart.id
    #             stepfile.raw_api_payload = _response_payload(response)
    #             return stepfile
    #
    #     tasks = [asyncio.create_task(parse_asset(asset)) for asset in assets]
    #     stepfiles: list[Stepfile] = []
    #
    #     try:
    #         for task in tqdm(
    #             asyncio.as_completed(tasks),
    #             total=len(tasks),
    #             desc="Parse",
    #             unit="chart",
    #         ):
    #             stepfiles.append(await task)
    #     except Exception:
    #         for task in tasks:
    #             task.cancel()
    #         await asyncio.gather(*tasks, return_exceptions=True)
    #         raise
    #
    #     return stepfiles

    def _collection_rows_for_packs(self, packs: list[Pack]) -> list[Pack]:
        source = self.game.source
        if not isinstance(source, PackPayloadResolver):
            return packs

        return [
            Pack(
                id=pack.id,
                name=pack.name,
                raw_payload=source.resolve_pack_payload(pack.id)
                or pack.raw_payload,
            )
            for pack in packs
        ]

    async def stream(self):
        log_event(
            self.logger,
            "ingestion",
            status="starting",
            game_id=self.game.id,
            game_name=self.game.name,
        )

        source = self.game.source

        try:
            phase_start = time.perf_counter()
            set_progress_phase("Fetching source collections", 0.08, 0.12)
            log_event(
                self.logger,
                "fetch_packs",
                status="starting",
                game_id=self.game.id,
            )
            packs = list(await source.fetch_packs(self.secrets))
            log_event(
                self.logger,
                "fetch_packs",
                status="completed",
                packs=len(packs),
                elapsed_seconds=time.perf_counter() - phase_start,
            )
            yield "collections", self._collection_rows_for_packs(packs)

            phase_start = time.perf_counter()
            set_progress_phase("Fetching chart metadata", 0.12, 0.18)
            log_event(
                self.logger,
                "fetch_chart_refs",
                status="starting",
                packs=len(packs),
                concurrency=self.concurrency,
            )
            charts = await self._fetch_charts_for_packs(packs)

            log_event(
                self.logger,
                "fetch_chart_refs",
                status="completed",
                charts=len(charts),
                elapsed_seconds=time.perf_counter() - phase_start,
            )
            yield "collections", self._collection_rows_for_packs(packs)
            yield "chart_refs", charts

            phase_start = time.perf_counter()
            downloaded = 0
            set_progress_phase("Ingesting source files", 0.18, 0.86)
            log_event(
                self.logger,
                "fetch_assets",
                status="starting",
                charts=len(charts),
                concurrency=self.concurrency,
            )
            async for assets in self._stream_assets(charts):
                downloaded += len(assets)
                log_event(
                    self.logger,
                    "fetch_assets",
                    status="batch_completed",
                    batch_assets=len(assets),
                    downloaded_assets=downloaded,
                    total_charts=len(charts),
                )
                yield "assets", assets

            log_event(
                self.logger,
                "fetch_assets",
                status="completed",
                downloaded_assets=downloaded,
                elapsed_seconds=time.perf_counter() - phase_start,
            )

            # API parsing is disabled while bronze chart tables are being
            # built.
            # phase_start = time.perf_counter()
            # stepfiles = await self._parse_assets(assets)
            # self.logger.info(
            #     "Parsed %d stepfile(s) in %.2fs",
            #     len(stepfiles),
            #     time.perf_counter() - phase_start,
            # )

        finally:
            await source.close()

        log_event(
            self.logger,
            "ingestion",
            status="completed",
            game_id=self.game.id,
            game_name=self.game.name,
        )

    async def run(self) -> list[AssetResult]:
        assets: list[AssetResult] = []
        async for event_type, payload in self.stream():
            if event_type == "assets":
                assets.extend(payload)

        return assets
