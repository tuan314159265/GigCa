from __future__ import annotations

import math
import unittest

from engine.src.config import TRAFFIC_CFG
from engine.src.traffic import analyze_traffic, calculate_congestion_index
from engine.src.types import TrafficEdge


class TestCongestionIndex(unittest.TestCase):
    def test_index_is_continuous_and_clamped(self) -> None:
        self.assertAlmostEqual(calculate_congestion_index(16, 26), 10 / 26)
        self.assertEqual(calculate_congestion_index(30, 25), 0.0)
        self.assertEqual(calculate_congestion_index(0, 25), 1.0)

    def test_missing_and_invalid_speeds_are_unknown(self) -> None:
        for current, free_flow in (
            (None, 30), (10, None), (-1, 30), (10, 0),
            (math.inf, 30), (10, math.nan),
        ):
            with self.subTest(current=current, free_flow=free_flow):
                self.assertIsNone(calculate_congestion_index(current, free_flow))

    def test_analysis_length_weights_mean_and_ranks_segments(self) -> None:
        analysis = analyze_traffic(
            [
                TrafficEdge("edge_clear_1", length_m=300, current_speed_kmh=9, free_flow_speed_kmh=10),
                TrafficEdge("edge_slow_2", length_m=100, current_speed_kmh=5, free_flow_speed_kmh=10),
            ],
            "partial",
            None,
            TRAFFIC_CFG,
            420,
        )

        self.assertAlmostEqual(analysis.mean_congestion_index, 0.2)
        self.assertEqual(analysis.congestion_index_aggregation, "length_weighted")
        self.assertEqual(
            [item["edge_id"] for item in analysis.details],
            ["edge_slow_2", "edge_clear_1"],
        )

    def test_analysis_reports_unweighted_fallback(self) -> None:
        analysis = analyze_traffic(
            [TrafficEdge("edge_a", current_speed_kmh=5, free_flow_speed_kmh=10)],
            "available",
            None,
            TRAFFIC_CFG,
            420,
        )

        self.assertAlmostEqual(analysis.mean_congestion_index, 0.5)
        self.assertEqual(analysis.congestion_index_aggregation, "segment_mean")


if __name__ == "__main__":
    unittest.main()
