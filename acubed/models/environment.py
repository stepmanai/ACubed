# models/environment.py

from enum import StrEnum


class Environment(StrEnum):
    LOCAL = "local"
    DATABRICKS = "databricks"
    DATABRICKS_SERVERLESS = (
        "databricks_serverless"
    )