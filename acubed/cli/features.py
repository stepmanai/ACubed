# cli/features.py

import time

from acubed.core.bootstrap import (
    ApplicationContext,
)
from acubed.features.executors.materialization import (
    FeatureExecutor,
)
from acubed.logging.factory import (
    get_logger,
)


def main():
    start_time = time.time()

    logger = get_logger()
    logger.info("=" * 80)
    logger.info("FEATURE MATERIALIZATION PIPELINE STARTED")
    logger.info("=" * 80)

    logger.info("Step 1/3: Initializing application context...")
    app = ApplicationContext()
    logger.info("✓ Environment detected: %s", app.runtime.environment)
    logger.info(
        "✓ Catalog: %s",
        app.storage.catalog if hasattr(app.storage, "catalog") else "N/A",
    )
    logger.info(
        "✓ Schema: %s",
        app.storage.schema if hasattr(app.storage, "schema") else "N/A",
    )

    logger.info("Step 2/3: Initializing feature executor...")
    executor = FeatureExecutor(
        context=app.runtime,
        storage=app.storage,
        tables=app.tables,
    )
    logger.info("✓ Feature executor initialized")

    logger.info("Step 3/3: Materializing feature layers...")
    logger.info("-" * 80)

    logger.info("Materializing SILVER layer (events)...")
    silver_start = time.time()
    executor.materialize_silver()
    silver_duration = time.time() - silver_start
    logger.info("✓ Silver layer materialized in %.2f seconds", silver_duration)

    logger.info("Materializing GOLD layer (features + targets)...")
    gold_start = time.time()
    executor.materialize_gold()
    gold_duration = time.time() - gold_start
    logger.info("✓ Gold layer materialized in %.2f seconds", gold_duration)
    logger.info("  - Gold features table created")
    logger.info("  - Gold targets table created")

    total_duration = time.time() - start_time
    logger.info("-" * 80)
    logger.info("=" * 80)
    logger.info("FEATURE MATERIALIZATION PIPELINE COMPLETED SUCCESSFULLY")
    logger.info(
        "Total execution time: %.2f seconds (%.2f minutes)",
        total_duration,
        total_duration / 60,
    )
    logger.info("  - Silver layer: %.2f seconds", silver_duration)
    logger.info("  - Gold layer: %.2f seconds", gold_duration)
    logger.info("=" * 80)


if __name__ == "__main__":
    main()
