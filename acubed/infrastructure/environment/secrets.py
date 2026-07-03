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
            if dbutils is None:
                hint = "dbutils is not available (not running in Databricks)"
            else:
                scope = os.getenv("ACUBED_DATABRICKS_SECRET_SCOPE", "acubed")
                key = secret_ref.lower().replace("_", "-")
                hint = f"Tried Databricks secret scope='{scope}', key='{key}'"

            raise ValueError(
                f"Required secret '{secret_name}' was not found. Set "
                f"{secret_ref} as an environment variable or configure it in "
                f"Databricks secrets. Debug: {hint}"
            )

        secrets[secret_name] = value

    return secrets


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
    # If secret_ref contains a slash, treat it as scope/key
    if "/" in secret_ref:
        scope, key = secret_ref.split("/", 1)
        patterns = [(scope, key)]
    else:
        # Try multiple patterns to find the secret
        patterns = []

        # Pattern 1: Extract game scope from prefix and transform remaining parts
        # (e.g., FFR_API_KEY -> ffr/api-key, OSU_CLIENT_ID -> osu/client-id)
        if "_" in secret_ref:
            parts = secret_ref.split("_", 1)  # Split only on first underscore
            if len(parts) == 2:
                game_scope = parts[0].lower()
                remaining_key = parts[1].lower().replace("_", "-")
                patterns.append((game_scope, remaining_key))

        # Pattern 2: Default scope with transformed key
        # (e.g., acubed/ffr-api-key, acubed/osu-client-id)
        default_scope = os.getenv("ACUBED_DATABRICKS_SECRET_SCOPE", "acubed")
        transformed_key = secret_ref.lower().replace("_", "-")
        patterns.append((default_scope, transformed_key))

        # Pattern 3: Game scope with full transformed key
        # (e.g., ffr/ffr-api-key, osu/osu-client-id)
        if "_" in secret_ref:
            game_scope = secret_ref.split("_")[0].lower()
            patterns.append((game_scope, transformed_key))

    # Try each pattern until one works
    for scope, key in patterns:
        try:
            value = dbutils.secrets.get(scope=scope, key=key)
            if value:
                print(f"Found secret at scope='{scope}', key='{key}'")
                return value
        except Exception as e:
            # Log but continue trying other patterns
            print(
                f"Tried scope='{scope}', key='{key}' - {type(e).__name__}: {e}"
            )
            continue

    return None
