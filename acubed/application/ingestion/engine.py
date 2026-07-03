from __future__ import annotations

import asyncio
import time

from tqdm import tqdm

from acubed.domain.chart.types import AssetResponse, ChartRef, Pack
from acubed.domain.game.definition import GameDefinition
from acubed.infrastructure.logging import get_logger, log_event

AssetResult = tuple[ChartRef, AssetResponse]
BronzeEvent = tuple[str, list[Pack] | list[ChartRef] | list[AssetResult]]


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
        fetch_charts_for_packs = getattr(
            source, "fetch_charts_for_packs", None
        )
        if callable(fetch_charts_for_packs):
            return list(
                await fetch_charts_for_packs(
                    packs,
                    concurrency=self.concurrency,
                )
            )

        sem = asyncio.Semaphore(self.concurrency)
        charts: list[ChartRef] = []

        async def fetch_pack(pack: Pack) -> tuple[Pack, list[ChartRef]]:
            async with sem:
                return pack, list(await source.fetch_pack_charts(pack.id))

        tasks = [asyncio.create_task(fetch_pack(pack)) for pack in packs]

        resolver = getattr(source, "resolve_pack_name", None)

        for task in tqdm(
            asyncio.as_completed(tasks),
            total=len(tasks),
            desc="Packs",
            unit="pack",
        ):
            pack, pack_charts = await task

            if resolver is not None:
                pack_name = resolver(pack.id)
            else:
                pack_name = pack.name

            self.logger.info("%s: %d charts", pack_name, len(pack_charts))
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

        fetch_many = getattr(source, "fetch_many", None)

        if callable(fetch_many):
            bulk_fetch = fetch_many
            return await bulk_fetch(
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

        for coro in tqdm(
            asyncio.as_completed(tasks),
            total=len(tasks),
            desc="Charts",
            unit="chart",
        ):
            results.append(await coro)

        return results

    async def _stream_assets(
        self,
        charts: list[ChartRef],
    ):
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

        stream_many = getattr(source, "stream_many", None)
        if callable(stream_many):
            progress = tqdm(total=len(charts), desc="Charts", unit="chart")
            try:
                async for batch in stream_many(
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
            for task in tqdm(
                asyncio.as_completed(tasks),
                total=len(tasks),
                desc="Charts",
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
        resolver = getattr(source, "resolve_pack_payload", None)

        if not callable(resolver):
            return packs

        return [
            Pack(
                id=pack.id,
                name=pack.name,
                raw_payload=resolver(pack.id) or pack.raw_payload,
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
            log_event(
                self.logger,
                "fetch_packs",
                status="starting",
                game_id=self.game.id,
            )
            packs = list(await source.fetch_packs())
            log_event(
                self.logger,
                "fetch_packs",
                status="completed",
                packs=len(packs),
                elapsed_seconds=time.perf_counter() - phase_start,
            )
            yield "collections", self._collection_rows_for_packs(packs)

            phase_start = time.perf_counter()
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
