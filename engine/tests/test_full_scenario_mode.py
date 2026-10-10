"""Full-scenario test: when every feed has (hand-set TEST) inputs, the market-independent lenses run in FULL mode with
MEDIUM confidence; the two earning lenses run on the driver's own log and stay PARTIAL/LOW."""

from __future__ import annotations

import unittest

from engine.src.adapter import load_engine_input_from_dict
from engine.src.engine import run_driver_engine
from engine.tests.fixtures import (
    create_default_driver_context,
    create_default_driver_preferences,
    full_scenario_payload,
)


class TestFullScenarioMode(unittest.TestCase):
    def test_all_objectives_available_with_medium_confidence(self) -> None:
        engine_input = load_engine_input_from_dict(full_scenario_payload())
        ctx = create_default_driver_context(idle_min=25, horizon_min=180)
        prefs = create_default_driver_preferences(rain_tolerance="medium")

        output = run_driver_engine(engine_input, ctx, prefs)

        # 1. max_trip_value — fed only by the driver's own log/tariff (no market data), so PARTIAL with LOW confidence
        trip_val = output.objectives["max_trip_value"]
        self.assertEqual(trip_val.status, "partial")
        self.assertEqual(trip_val.confidence, "low")
        self.assertGreater(len(trip_val.candidates), 0)
        self.assertIsNotNone(trip_val.plan)
        self.assertEqual(trip_val.plan.plan_id, "max_trip_value")
        self.assertGreater(len(trip_val.plan.steps), 0)
        self.assertIsNotNone(trip_val.plan.trade_offs)

        # 2. maintain_position — survival wait times from the driver's own wait spells, same honesty rule
        pos = output.objectives["maintain_position"]
        self.assertEqual(pos.status, "partial")
        self.assertEqual(pos.confidence, "low")
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
