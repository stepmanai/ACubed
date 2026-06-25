from __future__ import annotations

import asyncio

from tqdm import tqdm

from acubed.domain.chart.types import Stepfile
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

    async def run(self) -> list[Stepfile]:
        self.logger.info("Starting %s ingestion pipeline", self.game.name)

        source = self.game.source
        stepfiles: list[Stepfile] = []

        sem = asyncio.Semaphore(self.concurrency)

        try:
            packs = await source.fetch_packs()

            for pack in tqdm(packs, desc="Packs"):
                charts = await source.fetch_pack_charts(pack.id)

                self.logger.info("%s: %d charts", pack.name, len(charts))

                async def run_chart(chart):
                    async with sem:
                        return await source.fetch_assets(
                            chart.id,
                            self.secrets,
                        )

                tasks = [run_chart(c) for c in charts]

                for coro in tqdm(
                    asyncio.as_completed(tasks),
                    total=len(tasks),
                    desc=pack.name,
                    unit="chart",
                ):
                    response = await coro

                    stepfile = self.game.parser.parse(response)
                    stepfiles.append(stepfile)

        finally:
            await source.close()

        self.logger.info("%s ingestion complete", self.game.name)

        return stepfiles
