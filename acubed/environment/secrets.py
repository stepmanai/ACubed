# environment/secrets.py

import os

from acubed.models.environment import (
    Environment,
)


def get_api_key(
    environment: Environment,
) -> str:

    if environment == Environment.LOCAL:
        api_key = os.getenv("FFR_API_KEY")

        if not api_key:
            raise ValueError("FFR_API_KEY environment variable not found")

        return api_key

    from pyspark.dbutils import (
        DBUtils,
    )
    from pyspark.sql import (
        SparkSession,
    )

    spark = SparkSession.builder.getOrCreate()

    dbutils = DBUtils(spark)

    return dbutils.secrets.get(
        scope="ffr",
        key="api-key",
    )
