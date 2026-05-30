# # cli/inference.py

# from acubed.features.adapters.charts import (
#     chart_to_stepfile,
# )
# from acubed.features.executors.runtime import (
#     build_features,
# )

# stepfile = chart_to_stepfile(request.chart)

# features = build_features(
#     chart_id=-1,
#     stepfile=stepfile,
# )

# prediction = model.predict(
#     [
#         [
#             features.note_count,
#             features.duration_ms,
#             features.notes_per_second,
#             features.peak_nps,
#             features.jack_density,
#             features.stream_density,
#         ]
#     ]
# )
