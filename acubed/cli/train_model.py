# # cli/train_model.py

# from acubed.config.tables import (
#     build_table_config,
# )
# from acubed.features.executors.materialization import (
#     FeatureExecutor,
# )

# tables = build_table_config(
#     game=Game.FFR,
#     catalog="acubed",
# )

# executor = FeatureExecutor(
#     storage=storage,
#     tables=tables,
# )

# executor.materialize()

# train_df = storage.read_table(tables.gold_features)
