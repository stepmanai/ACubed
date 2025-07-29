import asyncio
import os
import subprocess

from dotenv import load_dotenv

from acubed.connector import FFRDatabaseConnector


def sort_jsonl_by_id(jsonl_path: str) -> None:
    shell_command = (
        f"uv run paste <(jq -c '.' {jsonl_path}) <(jq '._id' {jsonl_path}) "
        f"| sort -t $'\\t' -k2,2n | cut -f1 | sponge {jsonl_path}"
    )
    subprocess.run(shell_command, shell=True, executable="/bin/bash", check=True)  # noqa: S602


if __name__ == "__main__":
    load_dotenv()  # Load .env file

    LOCAL_DATASET_PATH = "datasets/ffr/charts"
    JSONL_FILE_PATH = os.path.join(LOCAL_DATASET_PATH, "charts.jsonl")

    config = {"username": os.getenv("FFR_USERNAME"), "password": os.getenv("FFR_PASSWORD")}

    connector = FFRDatabaseConnector(config)
    asyncio.run(connector.run(JSONL_FILE_PATH))
    sort_jsonl_by_id(JSONL_FILE_PATH)
