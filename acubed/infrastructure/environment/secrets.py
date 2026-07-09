"""Environment-specific secret loading."""

from __future__ import annotations

import os
from collections.abc import Mapping
from functools import lru_cache
from logging import getLogger
from pathlib import Path
from typing import Any

from acubed.infrastructure.environment.types import (
    Environment,
)

_LOGGER = getLogger("acubed")


def get_required_secrets(
    environment: Environment,
    required_secrets: Mapping[str, str],
) -> dict[str, str]:
    secrets = {}

    if not required_secrets:
        return secrets

    dbutils = None if environment == Environment.LOCAL else _get_dbutils()
    dotenv_values = (
        _dotenv_values() if environment == Environment.LOCAL else {}
    )

    for secret_name, secret_ref in required_secrets.items():
        value = os.getenv(secret_ref) or dotenv_values.get(secret_ref)

        if value is None and dbutils is not None:
            value = _get_databricks_secret(dbutils, secret_ref)

        if value is None:
            if dbutils is None:
                searched = ", ".join(
                    str(path) for path in _dotenv_search_paths()
                )
                hint = (
                    "dbutils is not available (not running in Databricks). "
                    f"Searched .env files: {searched or 'none'}"
                )
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


@lru_cache(maxsize=1)
def _dotenv_values() -> dict[str, str]:
    values: dict[str, str] = {}
    for path in reversed(_dotenv_search_paths()):
        values.update(_parse_dotenv(path))
    return values


@lru_cache(maxsize=1)
def _dotenv_search_paths() -> tuple[Path, ...]:
    roots = (Path.cwd(), Path(__file__).resolve())
    seen_dirs: set[Path] = set()
    paths: list[Path] = []

    for root in roots:
        for directory in (
            root.parent if root.is_file() else root,
            *root.parents,
        ):
            try:
                directory = directory.resolve()
            except OSError:
                continue
            if directory in seen_dirs:
                continue
            seen_dirs.add(directory)

            dotenv_path = directory / ".env"
            if dotenv_path.is_file():
                paths.append(dotenv_path)

    return tuple(paths)


def _parse_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return values

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()

        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue

        values[key] = _clean_dotenv_value(value.strip())

    return values


def _clean_dotenv_value(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]

    if " #" in value:
        value = value.split(" #", 1)[0].rstrip()

    return value


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
        patterns = [(scope, key)]
    else:
        patterns = []

        # Pattern 1: Extract game from prefix and transform remaining parts
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

    for scope, key in patterns:
        try:
            value = dbutils.secrets.get(scope=scope, key=key)
            if value:
                _LOGGER.debug(
                    "Found secret at scope='%s', key='%s'",
                    scope,
                    key,
                )
                return value
        except Exception as e:
            # Log but continue trying other patterns
            _LOGGER.debug(
                "Tried scope='%s', key='%s' - %s: %s",
                scope,
                key,
                type(e).__name__,
                e,
            )
            continue

    return None
