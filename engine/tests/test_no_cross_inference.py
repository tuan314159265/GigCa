"""Test 9.4: No cross-inference.

When data_status.traffic == 'missing', safety_comfort must NOT contain any
numeric traffic congestion score — it may only contain a string traffic_note.
"""

from __future__ import annotations

import unittest

from engine.src.engine import run_driver_engine
from engine.src.mock_data import (
    create_default_driver_context,
    create_default_driver_preferences,
    create_mock_engine_input,
)


class TestNoCrossInference(unittest.TestCase):
    def test_missing_traffic_has_no_numeric_traffic_score(self) -> None:
        mock_input = create_mock_engine_input(data_status={"traffic": "missing"})
        ctx = create_default_driver_context()
        prefs = create_default_driver_preferences()

        output = run_driver_engine(mock_input, ctx, prefs)
        safety_res = output.objectives["safety_comfort"]

        # traffic_note must be string
        self.assertIsInstance(safety_res.traffic_note, str)
        self.assertIn("Chưa có dữ liệu giao thông", safety_res.traffic_note or "")

        # verify that no candidates or numeric traffic fields exist
        for candidate in safety_res.candidates:
            self.assertFalse(hasattr(candidate, "traffic_speed"))
            self.assertFalse(hasattr(candidate, "traffic_score"))


if __name__ == "__main__":
    unittest.main()
