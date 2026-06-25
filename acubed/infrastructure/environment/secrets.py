"""Environment-specific secret loading."""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

from acubed.infrastructure.environment.types import (
    Environment,
)


def get_required_secrets(
    environment: Environment,
    required_secrets: Mapping[str, str],
) -> dict[str, str]:
    secrets = {}

    if not required_secrets:
        return secrets

    dbutils = None if environment == Environment.LOCAL else _get_dbutils()

    for secret_name, secret_ref in required_secrets.items():
        value = os.getenv(secret_ref)

        if value is None and dbutils is not None:
            value = _get_databricks_secret(dbutils, secret_ref)

        if value is None:
            raise ValueError(
                f"Required secret '{secret_name}' was not found. Set "
                f"{secret_ref} as an environment variable or configure it in "
                "Databricks secrets."
            )

        secrets[secret_name] = value

    return secrets


def get_api_key(environment: Environment) -> str:
    return get_required_secrets(
        environment,
        {"key": "FFR_API_KEY"},
    )["key"]


def _get_dbutils() -> Any | None:
    try:
        import IPython

        shell = IPython.get_ipython()
        if shell is not None:
            dbutils = shell.user_ns.get("dbutils")
            if dbutils is not None:
                return dbutils
    except ImportError:
        pass

    try:
        from pyspark.dbutils import DBUtils
        from pyspark.sql import SparkSession

        return DBUtils(SparkSession.builder.getOrCreate())
    except ImportError:
        return None


def _get_databricks_secret(dbutils: Any, secret_ref: str) -> str | None:
    if "/" in secret_ref:
        scope, key = secret_ref.split("/", 1)
    else:
        scope = os.getenv("ACUBED_DATABRICKS_SECRET_SCOPE", "acubed")
        key = secret_ref.lower().replace("_", "-")

    try:
        return dbutils.secrets.get(scope=scope, key=key)
    except Exception:
        return None
