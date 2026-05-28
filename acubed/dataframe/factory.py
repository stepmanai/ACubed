# dataframe/factory.py

import pandas as pd


def build_dataframe_factory(
    environment,
):
    if environment in {
        "local",
        "test",
    }:
        return pd.DataFrame

    if environment in {
        "databricks",
        "databricks-serverless",
    }:
        from pyspark.sql import (
            SparkSession,
        )

        spark = SparkSession.builder.appName("acubed").getOrCreate()

        return spark.createDataFrame

    raise ValueError(f"Unsupported environment: {environment}")
