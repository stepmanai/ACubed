# infrastructure/environment/detection.py
import os

from acubed.infrastructure.environment.types import Environment


def detect_environment() -> Environment:

    runtime_version = os.environ.get(
        "DATABRICKS_RUNTIME_VERSION",
        "",
    )

    if not runtime_version:
        return Environment.LOCAL

    if runtime_version.startswith("client."):
        return Environment.DATABRICKS_SERVERLESS

    return Environment.DATABRICKS
