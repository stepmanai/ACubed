# api.py

import requests
import time
from concurrent.futures import ThreadPoolExecutor


class FFRClient:

    def __init__(
        self,
        api_key,
        base_api_url,
        playlist_url,
        timeout=10,
        retries=5,
        thread_pool_size=4
    ):
        self.api_key = api_key
        self.base_api_url = base_api_url
        self.playlist_url = playlist_url
        self.timeout = timeout
        self.retries = retries
        self.thread_pool_size = thread_pool_size

        self.session = requests.Session()

    def fetch_songlist(self):
        response = self.session.get(
            self.base_api_url,
            params={
                "key": self.api_key,
                "action": "songlist"
            },
            timeout=self.timeout
        )

        response.raise_for_status()

        return response.json()

    def fetch_chart(self, song_id):
        url = (
            f"{self.base_api_url}"
            f"?key={self.api_key}"
            f"&action=chart"
            f"&level={song_id}"
        )

        for attempt in range(self.retries):
            try:
                response = self.session.get(
                    url,
                    timeout=self.timeout
                )

                response.raise_for_status()

                payload = response.json()

                return {
                    "song_id": song_id,
                    "info": payload.get("info"),
                    "chart": payload.get("chart")
                }

            except Exception:
                if attempt == self.retries - 1:
                    return None

                time.sleep(2 ** attempt)

    def fetch_charts_parallel(self, song_ids):
        with ThreadPoolExecutor(
            max_workers=self.thread_pool_size
        ) as executor:

            results = list(
                executor.map(
                    self.fetch_chart,
                    song_ids
                )
            )

        return [
            r for r in results
            if r is not None
        ]

    def fetch_playlist(self):
        headers = {
            "User-Agent": "Mozilla/5.0"
        }

        response = self.session.get(
            self.playlist_url,
            headers=headers,
            timeout=self.timeout
        )

        response.raise_for_status()

        return response.json()