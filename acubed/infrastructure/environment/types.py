"""Runtime environment types."""

import enum

try:
    from enum import StrEnum
except ImportError:

    class StrEnum(enum.StrEnum):
        pass


class Environment(StrEnum):
    LOCAL = "local"
    DATABRICKS = "databricks"
    DATABRICKS_SERVERLESS = "databricks_serverless"


def is_databricks_environment(environment: Environment) -> bool:
    return environment in {
        Environment.DATABRICKS,
        Environment.DATABRICKS_SERVERLESS,
    }
