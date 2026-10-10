"""Test Strategic Direction Plans and Advisor Reasoning.

Verifies that the engine generates complete, sequential operational action plans
for each of the 4 independent objectives, preserving driver autonomy.
"""

from __future__ import annotations

import unittest

from engine.src.advisor import consult_driver_advisor
from engine.src.engine import run_driver_engine
from engine.tests.fixtures import (
    create_default_driver_context,
    create_default_driver_preferences,
    create_mock_engine_input,
)
from engine.src.types import WeatherHour


class TestStrategicDirectionPlans(unittest.TestCase):
    def test_safety_plan_approaching_rain(self) -> None:
        mock_input = create_mock_engine_input()
        ctx = create_default_driver_context(idle_min=25, horizon_min=180)
        prefs = create_default_driver_preferences(rain_tolerance="medium")

        output = run_driver_engine(mock_input, ctx, prefs)
        self.assertIsNone(output.synthesized_action)  # No single forced decision

        safety_res = output.objectives["safety_comfort"]
        self.assertIsNotNone(safety_res.plan)
        plan = safety_res.plan
        assert plan is not None

        self.assertEqual(plan.plan_id, "safety_comfort")
        self.assertIn("Cửa sổ thời tiết còn an toàn", plan.summary)
        self.assertEqual(len(plan.steps), 4)
        self.assertIn("Chỉ nhận cuốc ngắn", plan.steps[0].action)
        self.assertIn("Chuẩn bị sẵn sàng áo mưa", plan.steps[1].action)
        self.assertIsNotNone(plan.trade_offs)
        self.assertIsNotNone(plan.contingency_fallback)

    def test_safety_plan_immediate_heavy_rain(self) -> None:
        # The hour that is happening NOW (snapshot at 14:00) exceeds tolerance heavily.
        # Open-Meteo hourly values describe the PRECEDING hour (docs/06_DATA_CATALOG), so the entry stamped 15:00
        # covers 14:00-15:00, i.e. the current hour; an entry stamped 14:00 would describe 13:00-14:00 (already past).
        heavy_rain_weather = [
            WeatherHour(valid_time="2026-09-27T15:00", precipitation_mm=4.5, precipitation_probability_pct=95.0),
        ]
        mock_input = create_mock_engine_input(weather_hourly=heavy_rain_weather)
        ctx = create_default_driver_context(idle_min=10, horizon_min=60)
        prefs = create_default_driver_preferences(rain_tolerance="medium")

        output = run_driver_engine(mock_input, ctx, prefs)
        safety_res = output.objectives["safety_comfort"]
        self.assertIsNotNone(safety_res.plan)
        plan = safety_res.plan
        assert plan is not None

        self.assertIn("Mưa lớn đang diễn ra", plan.summary)
        self.assertIn("Tấp xe vào lề có mái che", plan.steps[0].action)
        self.assertEqual(plan.key_metrics["weather_action_signal"], "TRU_MUA_NGAY")

    def test_rest_spot_direction_plan(self) -> None:
        mock_input = create_mock_engine_input()
        ctx = create_default_driver_context(idle_min=25, horizon_min=180)
        prefs = create_default_driver_preferences(rain_tolerance="medium")

        output = run_driver_engine(mock_input, ctx, prefs)
        rest_res = output.objectives["rest_spot"]
        self.assertIsNotNone(rest_res.plan)
        plan = rest_res.plan
        assert plan is not None

        self.assertEqual(plan.plan_id, "rest_spot")
        self.assertEqual(len(plan.steps), 4)
        self.assertIn("Tạm dừng ứng dụng", plan.steps[0].action)
        self.assertIn("Di chuyển theo lộ trình", plan.steps[1].action)
        self.assertIn("Nghỉ ngơi", plan.steps[2].action)
        self.assertIn("Bật lại ứng dụng", plan.steps[3].action)
        self.assertEqual(plan.key_metrics["recommended_rest_min"], 25)

    def test_advisor_compares_plans_without_forcing_decision(self) -> None:
        mock_input = create_mock_engine_input()
        ctx = create_default_driver_context(idle_min=25, horizon_min=180)
        prefs = create_default_driver_preferences(rain_tolerance="medium")

        output = run_driver_engine(mock_input, ctx, prefs)
        advisor = consult_driver_advisor(output)

        self.assertIn("situation_assessment", advisor)
        self.assertIn("plans_overview", advisor)
        self.assertIn("decision_guide", advisor)
        self.assertIn("contingency_plan", advisor)
        self.assertIn("action_steps", advisor)
        self.assertEqual(advisor["advisor_mode"], "deterministic_expert_system")
        self.assertIn("Tài xế toàn quyền lựa chọn", advisor["summary"])


if __name__ == "__main__":
    unittest.main()
