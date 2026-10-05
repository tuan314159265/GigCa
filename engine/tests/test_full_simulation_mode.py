"""Test Full Simulation Mode.

Verifies that when full simulated data is provided for all feeds,
the engine activates FULL mode across all 4 objectives with MEDIUM confidence.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from engine.src.adapter import load_engine_input_from_file
from engine.src.engine import run_driver_engine
from engine.src.mock_data import (
    create_default_driver_context,
    create_default_driver_preferences,
)

ROOT = Path(__file__).resolve().parents[2]
FULL_SIM_PATH = ROOT / "data" / "fixtures" / "hcmc_full_simulated_snapshot.json"


class TestFullSimulationMode(unittest.TestCase):
    def test_all_objectives_available_with_medium_confidence(self) -> None:
        self.assertTrue(FULL_SIM_PATH.exists(), f"Missing fixture at {FULL_SIM_PATH}")

        engine_input = load_engine_input_from_file(FULL_SIM_PATH)
        ctx = create_default_driver_context(idle_min=25, horizon_min=180)
        prefs = create_default_driver_preferences(rain_tolerance="medium")

        output = run_driver_engine(engine_input, ctx, prefs)

        # 1. max_trip_value
        trip_val = output.objectives["max_trip_value"]
        self.assertEqual(trip_val.status, "available")
        self.assertEqual(trip_val.confidence, "medium")
        self.assertGreater(len(trip_val.candidates), 0)
        self.assertIsNotNone(trip_val.plan)
        self.assertEqual(trip_val.plan.plan_id, "max_trip_value")
        self.assertGreater(len(trip_val.plan.steps), 0)
        self.assertIsNotNone(trip_val.plan.trade_offs)

        # 2. maintain_position
        pos = output.objectives["maintain_position"]
        self.assertEqual(pos.status, "available")
        self.assertEqual(pos.confidence, "medium")
        self.assertGreater(len(pos.candidates), 0)
        self.assertIsNotNone(pos.plan)
        self.assertEqual(pos.plan.plan_id, "maintain_position")
        self.assertGreater(len(pos.plan.steps), 0)

        # 3. rest_spot
        rest = output.objectives["rest_spot"]
        self.assertEqual(rest.status, "available")
        self.assertEqual(rest.confidence, "medium")
        self.assertGreater(len(rest.candidates), 0)
        self.assertTrue(rest.candidates[0].verified)
        self.assertIsNotNone(rest.plan)
        self.assertEqual(rest.plan.plan_id, "rest_spot")
        self.assertGreater(len(rest.plan.steps), 0)

        # 4. safety_comfort
        safety = output.objectives["safety_comfort"]
        self.assertEqual(safety.status, "available")
        self.assertEqual(safety.confidence, "medium")
        self.assertIn("Giao thông", safety.traffic_note or "")
        self.assertIsNotNone(safety.plan)
        self.assertEqual(safety.plan.plan_id, "safety_comfort")
        self.assertGreater(len(safety.plan.steps), 0)


if __name__ == "__main__":
    unittest.main()
