from operator import itemgetter
from typing import Any

import numpy as np


class FFRChartPreprocessor:
    def __init__(self, decimal_precision: int = 3):
        self.decimal_precision = decimal_precision
        self.encoding_array = np.array([1000, 100, 10, 1])

    def preprocess(self, chart_data: dict[str, Any]) -> dict[str, Any]:
        chart = self._zero_framer_preprocessing(chart_data["chart"])
        chart = self._map_encodings(chart)
        chart = self._aggregate_steps(chart)

        min_time = chart[:, 0].min()
        scale = 1 / 1000.0
        formatted_chart = [
            {
                "time": round((time - min_time) * scale, self.decimal_precision),
                "step": f"{int(step):04d}",
            }
            for time, step in chart
        ]

        info = chart_data["info"]
        return {
            "_id": info["id"],
            "name": info["name"],
            "difficulty": info["difficulty"],
            "chart": formatted_chart,
        }

    def _aggregate_steps(self, chart: np.ndarray) -> np.ndarray:
        time_diffs = np.diff(chart[:, 0], prepend=np.inf)
        unique_mask = time_diffs != 0
        times = chart[unique_mask, 0]

        cumulative = np.cumsum(unique_mask) - 1
        aggregated_steps = np.zeros(cumulative[-1] + 1, dtype=int)
        np.add.at(aggregated_steps, cumulative, chart[:, 1].astype(int))

        return np.column_stack((times, aggregated_steps))

    def _map_encodings(self, chart: np.ndarray) -> np.ndarray:
        directions = chart[:, 0].astype(int)
        encoded = self.encoding_array[directions]
        chart[:, 0] = encoded
        return chart[:, ::-1].astype(float)

    def _zero_framer_preprocessing(self, chart: list[list[int]]) -> np.ndarray:
        chart.sort(key=itemgetter(0, 1))
        arr = np.array(chart, dtype=int)

        key_cols = arr[:, [0, 1, 3]]
        _, idx = np.unique(key_cols, axis=0, return_index=True)
        duplicate_mask = np.ones(len(arr), dtype=bool)
        duplicate_mask[idx] = False
        arr[duplicate_mask, 3] += 33

        return arr[:, 1::2]
