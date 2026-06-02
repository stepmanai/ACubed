import subprocess
import sys

from acubed.models.environment import (
    Environment,
)


def bootstrap_runtime(
    environment: Environment,
) -> None:

    if environment != Environment.DATABRICKS_SERVERLESS:
        return

    try:
        import narwhals  # noqa: F401

    except ImportError:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "-q", "narwhals"]
        )
