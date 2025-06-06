import argparse
import asyncio
import json
import logging
from datetime import datetime
from functools import lru_cache
from hashlib import md5
from pathlib import Path
from typing import Any, Dict, List, Tuple, Union

import dlt
import httpx

# Setup logger
logger = logging.getLogger(__name__)

# Define the schema directory
DUCKDB_DIR = Path(__file__).parent.parent / "duckdb"


@lru_cache()
def load_schema(filename: str) -> Dict[str, Any]:
    """Load a JSON schema from disk."""
    with open(DUCKDB_DIR / "schema" / filename, encoding="utf-8") as f:
        return json.load(f)


def generate_md5_from_tuple(values: Tuple[Union[str, int], ...]) -> str:
    """Generate a stable MD5 hash from a tuple using JSON to preserve structure."""
    serialized = json.dumps(values, separators=(',', ':'))
    return md5(serialized.encode()).hexdigest()


class AsyncRESTClient:
    """A lightweight async wrapper around httpx for REST calls."""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url
        self.client = httpx.AsyncClient(base_url=base_url, timeout=30)

    async def get(self, endpoint: str, params: Dict[str, Any] = None) -> httpx.Response:
        return await self.client.get(endpoint or "/", params=params)

    async def close(self) -> None:
        await self.client.aclose()


@dlt.source
def ffr_source(
    song_id_filters: List[int] = None,
    base_url: str = dlt.config.value,
    api_key: str = dlt.secrets.value,
):
    """DLT source for Flash Flash Revolution chart and metadata data."""
    client = AsyncRESTClient(base_url=base_url)

    async def fetch_chart_for_song(song_id: int) -> List[Dict[str, Any]]:
        params = {"key": api_key, "action": "chart", "level": song_id}
        response = await client.get("", params=params)
        response.raise_for_status()
        chart_notes = response.json().get("chart", [])

        logger.info("Fetched %d notes for song ID %d", len(chart_notes), song_id)

        columns = ["framers", "orientation", "color", "timestamp"]
        return [
            {
                "note_id": generate_md5_from_tuple((song_id, index)),
                "song_id": song_id,
                "index": index,
                **dict(zip(columns, note_data)),
            }
            for index, note_data in enumerate(chart_notes)
        ]

    @dlt.resource(
        name="metadata",
        primary_key="id",
        incremental=dlt.sources.incremental("swf_version"),
        write_disposition="merge",
        columns=load_schema("metadata.json"),
    )
    def fetch_metadata():
        """Fetch song metadata and collect song IDs in source_state."""
        state = dlt.current.resource_state().get("incremental", {}).get("swf_version", {})
        last_seen_version = state.get("last_value")

        if isinstance(last_seen_version, str):
            try:
                last_seen_version = datetime.fromisoformat(last_seen_version)
            except ValueError:
                last_seen_version = None

        source_state = dlt.current.source_state()
        source_state["song_ids"] = []

        params = {"key": api_key, "action": "songlist"}
        response = httpx.get(base_url, params=params)
        response.raise_for_status()

        for song in response.json():
            song_id = song.get("id")
            if song_id_filters and song_id not in song_id_filters:
                continue

            swf_version = song.get("swf_version")
            if isinstance(swf_version, str):
                try:
                    swf_version = datetime.fromisoformat(swf_version)
                except ValueError:
                    continue

            if not last_seen_version or (swf_version and swf_version > last_seen_version):
                source_state["song_ids"].append(song_id)
                yield song

    @dlt.resource(
        name="steps",
        write_disposition="replace",
        columns=load_schema("steps.json"),
    )
    def fetch_steps():
        """Defer async chart fetching for all collected song IDs."""
        song_ids = dlt.current.source_state().get("song_ids", [])
        for song_id in song_ids:
            yield dlt.defer(lambda song_id=song_id: fetch_chart_for_song(song_id))

    # Attach client to the source for use outside
    ffr_source.client = client

    return [fetch_metadata, fetch_steps]


def configure_logging() -> None:
    """Set logging level and suppress noisy libraries."""
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)


def run_pipeline() -> None:
    """Parse arguments and execute the DLT pipeline."""
    parser = argparse.ArgumentParser(
        description="Ingest FFR data into DuckDB using the DLT pipeline."
    )
    parser.add_argument("--debug", action="store_true", help="Limit to filtered song IDs")
    args = parser.parse_args()

    configure_logging()

    debug_ids = [2783, 1405, 960, 281, 3347]
    selected_ids = debug_ids if args.debug else []

    pipeline = dlt.pipeline(
        pipeline_name=f"ffr{'_debug' if args.debug else ''}",
        destination=dlt.destinations.duckdb(f"duckdb/ffr{'_debug' if args.debug else ''}.duckdb"),
        dataset_name="charts",
    )

    source = ffr_source(song_id_filters=selected_ids)
    pipeline.run(source)

    # Close the async HTTP client
    asyncio.run(ffr_source.client.close())

    logger.info("Pipeline Trace: %s", pipeline.last_trace)


if __name__ == "__main__":
    run_pipeline()
