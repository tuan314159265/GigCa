"""Test 9.3: Golden Rule (missing data != 0).

For every objective, when readiness is insufficient_data:
- candidates must be empty
- status must be 'insufficient_data'
- confidence must be 'none'
- never silently default to 0 or a neutral score.
"""

from __future__ import annotations

import unittest

from engine.src.engine import run_driver_engine
from engine.src.mock_data import (
    create_default_driver_context,
    create_default_driver_preferences,
    create_mock_engine_input,
)


class TestGoldenRule(unittest.TestCase):
    def test_insufficient_objectives_never_fabricate_scores(self) -> None:
        mock_input = create_mock_engine_input()
        ctx = create_default_driver_context()
        prefs = create_default_driver_preferences()

        output = run_driver_engine(mock_input, ctx, prefs)

        # max_trip_value is insufficient
        trip_val = output.objectives["max_trip_value"]
        self.assertEqual(trip_val.status, "insufficient_data")
        self.assertEqual(trip_val.confidence, "none")
        self.assertEqual(trip_val.candidates, [])
        self.assertIsNotNone(trip_val.reason_for_insufficiency)

        # maintain_position is insufficient
        pos = output.objectives["maintain_position"]
        self.assertEqual(pos.status, "insufficient_data")
        self.assertEqual(pos.confidence, "none")
        self.assertEqual(pos.candidates, [])
        self.assertIsNotNone(pos.reason_for_insufficiency)


if __name__ == "__main__":
    unittest.main()
