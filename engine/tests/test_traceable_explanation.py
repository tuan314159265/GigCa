"""Test 9.6: Traceable explanations.

Explanations must contain exact numbers tracing back to input data and routing samples.
"""

from __future__ import annotations

import re
import unittest

from engine.src.engine import run_driver_engine
from engine.src.mock_data import (
    create_default_driver_context,
    create_default_driver_preferences,
    create_mock_engine_input,
)


class TestTraceableExplanation(unittest.TestCase):
    def test_rest_spot_explanation_numbers_match_route(self) -> None:
        mock_input = create_mock_engine_input()
        ctx = create_default_driver_context()
        prefs = create_default_driver_preferences()

        output = run_driver_engine(mock_input, ctx, prefs)
        candidates = output.objectives["rest_spot"].candidates

        self.assertGreater(len(candidates), 0)
        for c in candidates:
            self.assertIsNotNone(c.explanation)
            explanation = c.explanation or ""

            # Check that distance in explanation matches candidate.distance_m
            expected_dist = round(c.distance_m)
            self.assertIn(
                f"{expected_dist}m",
                explanation,
                f"Explanation '{explanation}' must trace back to distance {expected_dist}m",
            )

            # Check that duration in explanation matches candidate.duration_s
            expected_min = max(1, round(c.duration_s / 60))
            self.assertIn(
                f"~{expected_min} phút",
                explanation,
                f"Explanation '{explanation}' must trace back to duration ~{expected_min} phút",
            )


if __name__ == "__main__":
    unittest.main()
