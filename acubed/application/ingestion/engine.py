from __future__ import annotations

import asyncio
import time

from tqdm import tqdm

from acubed.domain.chart.types import AssetResponse, ChartRef, Pack, Stepfile
from acubed.domain.game.definition import GameDefinition
from acubed.infrastructure.logging import get_logger


class GameIngestionEngine:
    def __init__(
        self,
        game: GameDefinition,
        secrets: dict[str, str] | None = None,
        concurrency: int = 8,
    ):
        self.game = game
        self.secrets = secrets or {}
        self.concurrency = concurrency
        self.logger = get_logger()

    async def _fetch_charts_for_packs(
        self,
        packs: list[Pack],
    ) -> list[ChartRef]:
        source = self.game.source
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
            charts.extend(pack_charts)

        return charts

    async def _fetch_assets(
        self,
        charts: list[ChartRef],
    ) -> list[tuple[ChartRef, AssetResponse]]:
        source = self.game.source
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
        results: list[tuple[ChartRef, AssetResponse]] = []

        for coro in tqdm(
            asyncio.as_completed(tasks),
            total=len(tasks),
            desc="Charts",
            unit="chart",
        ):
            results.append(await coro)

        return results

    async def _parse_assets(
        self,
        assets: list[tuple[ChartRef, AssetResponse]],
    ) -> list[Stepfile]:
        sem = asyncio.Semaphore(self.concurrency)

        async def parse_asset(asset: tuple[ChartRef, AssetResponse]):
            _, response = asset
            async with sem:
                loop = asyncio.get_running_loop()
                return await loop.run_in_executor(
                    None,
                    self.game.parser.parse,
                    response,
                )

        tasks = [asyncio.create_task(parse_asset(asset)) for asset in assets]
        stepfiles: list[Stepfile] = []

        try:
            for task in tqdm(
                asyncio.as_completed(tasks),
                total=len(tasks),
                desc="Parse",
                unit="chart",
            ):
                stepfiles.append(await task)
        except Exception:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise

        return stepfiles

    async def run(self) -> list[Stepfile]:
        self.logger.info("Starting %s ingestion pipeline", self.game.name)

        source = self.game.source

        try:
            phase_start = time.perf_counter()
            packs = list(await source.fetch_packs())
            self.logger.info(
                "Fetched %d pack(s) in %.2fs",
                len(packs),
                time.perf_counter() - phase_start,
            )

            phase_start = time.perf_counter()
            charts = await self._fetch_charts_for_packs(packs)

            self.logger.info(
                "Discovered %d charts in %.2fs",
                len(charts),
                time.perf_counter() - phase_start,
            )

            phase_start = time.perf_counter()
            assets = await self._fetch_assets(charts)
            self.logger.info(
                "Downloaded %d chart asset(s) in %.2fs",
                len(assets),
                time.perf_counter() - phase_start,
            )

            phase_start = time.perf_counter()
            stepfiles = await self._parse_assets(assets)
            self.logger.info(
                "Parsed %d stepfile(s) in %.2fs",
                len(stepfiles),
                time.perf_counter() - phase_start,
            )

        finally:
            await source.close()

        self.logger.info("%s ingestion complete", self.game.name)

        return stepfiles
