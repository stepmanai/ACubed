import asyncio
import json
import logging
from typing import Any

from aiohttp import ClientSession, ClientTimeout
from tqdm import tqdm

from .preprocessor import FFRChartPreprocessor


class FFRDatabaseConnectorOptimized(FFRChartPreprocessor):
    def __init__(self, config: dict):
        super().__init__()
        self.password: str = config["password"]
        for k, v in config.items():
            setattr(self, k, v)

        self.THREAD_POOL = 16
        self.BASE_API_URL = "https://www.flashflashrevolution.com/api/api.php"
        self.API_URL = f"{self.BASE_API_URL}?key={self.password}&action={{}}"
        self.urls: list[str] = []

    async def fetch(self, session: ClientSession, url: str, semaphore: asyncio.Semaphore) -> Any:
        async with semaphore:
            try:
                async with session.get(url) as response:
                    if response.status == 200:
                        return await response.json()
                    elif 500 <= response.status < 600:
                        logging.warning(f"Server error {response.status} for {url}, retrying once...")
                        await asyncio.sleep(2)
                        async with session.get(url) as retry_response:
                            if retry_response.status == 200:
                                return await retry_response.json()
                    else:
                        logging.error(f"Request failed {response.status} for {url}")
            except Exception:
                logging.exception(f"Exception during fetch {url}")
        return None

    async def download_charts(self, output_path: str = "charts.jsonl") -> None:
        semaphore = asyncio.Semaphore(self.THREAD_POOL)
        timeout = ClientTimeout(total=30)
        charts = []

        async with ClientSession(timeout=timeout) as session:
            tasks = [self.fetch(session, url, semaphore) for url in self.urls]

            with open(output_path, "w", encoding="utf-8") as f:
                for future in tqdm(asyncio.as_completed(tasks), total=len(tasks), desc="Downloading charts"):
                    res = await future
                    if res:
                        try:
                            chart = self.preprocess(res)
                            charts.append(chart)
                            f.write(json.dumps(chart) + "\n")
                        except Exception:
                            logging.exception("Error preprocessing chart")

        self.charts = {d["_id"]: {**d, "index": idx} for idx, d in enumerate(charts)}

    async def _get_chart_urls(self) -> None:
        timeout = ClientTimeout(total=30)
        async with ClientSession(timeout=timeout) as session:
            songlist_url = self.API_URL.format("songlist")
            try:
                async with session.get(songlist_url) as response:
                    response.raise_for_status()
                    songs = await response.json()
                    self.urls = [self.API_URL.format(f"chart&level={song['id']}") for song in songs]
            except Exception:
                logging.exception("Failed to fetch songlist")
                self.urls = []

    async def run(self) -> None:
        await self._get_chart_urls()
        await self.download_charts()
