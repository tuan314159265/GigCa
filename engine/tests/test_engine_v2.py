"""Tests for the v2 upgrade of the Decision Engine.

Every test pins a behaviour that the previous, naive engine got wrong: fabricated defaults, ignoring the driver's
position/time, auto-verifying POIs, borrowing routing measured from elsewhere, and reporting missing data as good news.
"""

from __future__ import annotations

import copy
import json
import unittest
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from engine.src import config as cfgmod
from engine.src.adapter import load_engine_input_from_dict, load_engine_input_from_file
from engine.src.engine import run_driver_engine
from engine.src.mock_data import (
    create_default_driver_context,
    create_default_driver_preferences,
    create_mock_engine_input,
)
from engine.src.robustness import analyze_top1
from engine.src.timeutil import is_open_at
from engine.src.types import DriverContext, DriverPreferences, WeatherHour
from engine.src.weather import analyze_weather

ROOT = Path(__file__).resolve().parents[2]
FULL_FIXTURE = ROOT / "data" / "fixtures" / "hcmc_full_simulated_snapshot.json"
DEMO_SNAPSHOT = ROOT / "data" / "samples" / "engine_input" / "hcmc_demo_snapshot.json"

HANG_XANH = (10.801, 106.711)


def full_payload() -> dict:
    with open(FULL_FIXTURE, "r", encoding="utf-8") as f:
        return json.load(f)


def load_full(mutate=None):
    payload = full_payload()
    if mutate:
        mutate(payload)
    return load_engine_input_from_dict(payload)


def ctx(**kw) -> DriverContext:
    kw.setdefault("idle_min", 25)
    kw.setdefault("horizon_min", 180)
    return create_default_driver_context(**kw)


def prefs(level: str = "medium", weights=None) -> DriverPreferences:
    p = create_default_driver_preferences(rain_tolerance=level)
    return replace(p, goal_weights=weights) if weights else p


class TestWeatherAnchoring(unittest.TestCase):
    def test_window_starts_at_current_time_not_at_first_list_item(self) -> None:
        """Anchor the rain window to generated_at, independent of shared sample edits."""
        hours = [WeatherHour(f"2026-09-27T{hour:02}:00", 3.0, 90.0) for hour in range(24)]
        inp = replace(
            create_mock_engine_input(weather_hourly=hours),
            generated_at="2026-09-27T17:20:00+07:00",
        )
        out = run_driver_engine(inp, ctx(idle_min=15), prefs())
        flags = out.objectives["safety_comfort"].rain_flags or []
        self.assertTrue(flags)
        self.assertEqual(flags[0].window, "17:00–18:00")
        self.assertEqual(flags[0].minutes_from_now, 0)
        self.assertTrue(all(f.window >= "17:00" for f in flags))

    def test_forecast_not_covering_horizon_is_unknown_not_good_weather(self) -> None:
        past = [WeatherHour(f"2026-09-27T0{h}:00", 0.0, 5.0) for h in range(1, 6)]
        out = run_driver_engine(create_mock_engine_input(weather_hourly=past), ctx(), prefs())
        res = out.objectives["safety_comfort"]
        self.assertEqual(res.weather_action_signal, "KHONG_DU_DU_BAO")
        self.assertNotEqual(res.weather_action_signal, "THOI_TIET_THUAN_LOI")
        self.assertEqual(res.status, "insufficient_data")
        self.assertIsNone(res.plan)

    def test_preceding_vs_following_hour_convention(self) -> None:
        hours = [WeatherHour("2026-09-27T15:00", 3.0, 90.0)]
        now = datetime(2026, 9, 27, 14, 0)
        base = dict(cfgmod.WEATHER_CFG)
        prec = analyze_weather(hours, now, 120, 55.0, 2.0, {**base, "slot_convention": "preceding_hour"}, 420)
        foll = analyze_weather(hours, now, 120, 55.0, 2.0, {**base, "slot_convention": "following_hour"}, 420)
        self.assertEqual(prec.flags[0].window, "14:00–15:00")
        self.assertEqual(prec.signal, "TRU_MUA_NGAY")
        self.assertEqual(foll.flags[0].window, "15:00–16:00")
        self.assertEqual(foll.signal, "DI_CHUYEN_TRUOC_KHI_MUA")
        self.assertEqual(foll.safe_window_min, 60)

    def test_invalid_values_are_treated_as_missing(self) -> None:
        hours = [WeatherHour("2026-09-27T15:00", -1.0, 140.0)]
        res = analyze_weather(hours, datetime(2026, 9, 27, 14, 0), 60, 55.0, 2.0, dict(cfgmod.WEATHER_CFG), 420)
        self.assertEqual(res.signal, "KHONG_DU_DU_BAO")
        self.assertTrue(any("ngoài miền hợp lệ" in w for w in res.warnings))

    def test_area_forecast_only_used_within_scope(self) -> None:
        base = load_full()
        hours = base.weather_hourly
        area0 = replace(base.areas[0], weather_hourly=hours)
        inp = replace(base, weather_hourly=[], areas=[area0] + base.areas[1:])
        near = run_driver_engine(inp, ctx(), prefs()).objectives["safety_comfort"]
        far = run_driver_engine(inp, ctx(lat=10.95, lng=106.95), prefs())
        self.assertNotEqual(near.weather_action_signal, "KHONG_DU_DU_BAO")
        self.assertEqual(far.objectives["safety_comfort"].weather_action_signal, "KHONG_DU_DU_BAO")
        self.assertTrue(any("vượt phạm vi" in a for a in far.assumptions_used))


class TestNoFabrication(unittest.TestCase):
    def test_no_invented_corridors_when_traffic_missing(self) -> None:
        out = run_driver_engine(create_mock_engine_input(), ctx(), prefs())
        res = out.objectives["safety_comfort"]
        self.assertIsNone(res.safe_corridors)
        assert res.plan is not None
        text = " ".join([res.plan.summary, res.plan.target_location] + [s.instruction for s in res.plan.steps])
        for invented in ("Pasteur", "Võ Văn Kiệt", "Lê Duẩn - Pasteur"):
            self.assertNotIn(invented, text)
        self.assertIsNone(res.plan.key_metrics["traffic_speed_kmh"])

    def test_no_surge_or_unsupported_claims_in_plans(self) -> None:
        out = run_driver_engine(load_full(), ctx(), prefs())
        for res in out.objectives.values():
            if res.plan:
                blob = " ".join([res.plan.summary, res.plan.trade_offs] + [s.instruction + s.expected_outcome for s in res.plan.steps])
                self.assertNotIn("surge", blob.lower())
                self.assertNotIn("6500", blob)

    def test_trip_value_missing_field_excludes_area_without_default(self) -> None:
        def mut(p):
            del p["areas"][0]["trip_value"]["avg_duration_min"]
        out = run_driver_engine(load_full(mut), ctx(), prefs())
        res = out.objectives["max_trip_value"]
        ids = [c.area_id for c in res.candidates]
        self.assertNotIn("area_ben_thanh_q1", ids)
        reasons = {e["id"]: e["reason"] for e in res.excluded or []}
        self.assertIn("avg_duration_min", reasons["area_ben_thanh_q1"])
        self.assertTrue(ids)  # the other areas are still evaluated

    def test_position_missing_wait_excludes_area_without_default(self) -> None:
        def mut(p):
            del p["areas"][0]["destination_distribution"]["avg_next_wait_min"]
        out = run_driver_engine(load_full(mut), ctx(), prefs())
        res = out.objectives["maintain_position"]
        self.assertNotIn("area_ben_thanh_q1", [c.area_id for c in res.candidates])
        self.assertTrue(any(e["id"] == "area_ben_thanh_q1" and "avg_next_wait_min" in e["reason"] for e in res.excluded or []))

    def test_adapter_does_not_inject_mock_pois_or_zero_coordinates(self) -> None:
        inp = load_engine_input_from_file(DEMO_SNAPSHOT)
        self.assertEqual(inp.poi_candidates, [])
        payload = full_payload()
        payload["pois"][0].pop("latitude")
        inp2 = load_engine_input_from_dict(payload)
        self.assertEqual(len(inp2.poi_candidates), len(payload["pois"]) - 1)
        self.assertIn("thiếu tọa độ", inp2.data_status_reasons["adapter"])


class TestDriverPositionAwareness(unittest.TestCase):
    def test_area_outside_reposition_radius_is_excluded_with_reason(self) -> None:
        out = run_driver_engine(load_full(), ctx(), prefs())
        res = out.objectives["max_trip_value"]
        self.assertNotIn("area_hang_xanh_bt", [c.area_id for c in res.candidates])
        reason = {e["id"]: e["reason"] for e in res.excluded or []}["area_hang_xanh_bt"]
        self.assertIn("ngoài bán kính", reason)

    def test_moving_the_driver_changes_the_result(self) -> None:
        inp = load_full()
        here = run_driver_engine(inp, ctx(), prefs()).objectives["max_trip_value"]
        there = run_driver_engine(inp, ctx(lat=HANG_XANH[0], lng=HANG_XANH[1]), prefs()).objectives["max_trip_value"]
        cand = {c.area_id: c for c in there.candidates}
        self.assertIn("area_hang_xanh_bt", cand)
        self.assertEqual(cand["area_hang_xanh_bt"].reposition_km, 0.0)
        self.assertNotEqual([c.area_id for c in here.candidates], [c.area_id for c in there.candidates])

    def test_yield_is_net_of_reposition_cost_and_traceable(self) -> None:
        res = run_driver_engine(load_full(), ctx(), prefs()).objectives["max_trip_value"]
        for c in res.candidates:
            self.assertIn(f"{c.expected_net_value_vnd:,.0f}đ", c.explanation or "")
            self.assertIn(f"{c.yield_vnd_per_hour:,.0f}đ/giờ", c.explanation or "")
            self.assertIn("KHÔNG phải routing", c.explanation or "")
            hours = (c.estimated_duration_min + (c.reposition_min or 0) + (c.wait_min or 0)) / 60
            expected = (c.expected_net_value_vnd - (c.reposition_cost_vnd or 0)) / hours
            self.assertAlmostEqual(c.yield_vnd_per_hour, expected, delta=expected * 0.01)
        ranks = [c.rank for c in res.candidates]
        self.assertEqual(ranks, sorted(ranks))
        yields = [c.yield_vnd_per_hour for c in res.candidates]
        self.assertEqual(yields, sorted(yields, reverse=True))


class TestRestSpotIntegrity(unittest.TestCase):
    def test_full_mode_does_not_auto_verify_pois(self) -> None:
        def mut(p):
            for poi in p["pois"]:
                poi["verified"] = False
                poi["parking_allowed"] = False
        out = run_driver_engine(load_full(mut), ctx(), prefs())
        res = out.objectives["rest_spot"]
        self.assertTrue(res.candidates)
        for c in res.candidates:
            self.assertFalse(c.verified)
            self.assertFalse(c.parking_allowed)
        self.assertEqual(res.status, "partial")
        self.assertEqual(res.confidence, "low")
        assert res.plan is not None
        self.assertIn("CHƯA", res.plan.steps[1].instruction)

    def test_verified_pois_rank_above_unverified(self) -> None:
        def mut(p):
            p["pois"][0]["verified"] = False  # highlands: closest, but unverified
        res = run_driver_engine(load_full(mut), ctx(), prefs()).objectives["rest_spot"]
        self.assertNotEqual(res.candidates[0].poi_id, "poi_highlands_01")
        self.assertTrue(res.candidates[0].verified)

    def test_routing_measured_from_far_away_is_not_the_drivers_distance(self) -> None:
        def mut(p):
            for a in p["areas"]:
                a["representative_point"]["latitude"] += 0.05  # ~5.5 km away from the driver
        res = run_driver_engine(load_full(mut), ctx(), prefs()).objectives["rest_spot"]
        self.assertEqual(res.status, "insufficient_data")
        self.assertEqual(res.candidates, [])
        self.assertTrue(any("xuất phát cách bạn" in e["reason"] for e in res.excluded or []))

    def test_closed_pois_are_excluded_at_arrival_time(self) -> None:
        def mut(p):
            for poi in p["pois"]:
                poi["opening_hours"] = "07:00 - 09:00"
        res = run_driver_engine(load_full(mut), ctx(), prefs()).objectives["rest_spot"]
        self.assertEqual(res.candidates, [])
        self.assertTrue(any("đóng cửa" in e["reason"] for e in res.excluded or []))

    def test_open_pois_report_arrival_time_and_fit(self) -> None:
        res = run_driver_engine(load_full(), ctx(), prefs()).objectives["rest_spot"]
        for c in res.candidates:
            self.assertTrue(c.is_open)
            self.assertIsNotNone(c.arrival_time)
            self.assertTrue(0.0 <= (c.fit_score or 0) <= 1.0)

    def test_rest_duration_follows_idle_config(self) -> None:
        short = run_driver_engine(load_full(), ctx(idle_min=10), prefs()).objectives["rest_spot"]
        long_ = run_driver_engine(load_full(), ctx(idle_min=50), prefs()).objectives["rest_spot"]
        assert short.plan and long_.plan
        self.assertEqual(short.plan.key_metrics["recommended_rest_min"], 15)
        self.assertEqual(long_.plan.key_metrics["recommended_rest_min"], 30)

    def test_opening_hours_parser(self) -> None:
        at = lambda h, m: datetime(2026, 9, 27, h, m)  # noqa: E731
        self.assertTrue(is_open_at("24/7", at(3, 0)))
        self.assertTrue(is_open_at("07:00 - 23:00", at(12, 0)))
        self.assertFalse(is_open_at("07:00 - 23:00", at(23, 30)))
        self.assertTrue(is_open_at("22:00-02:00", at(23, 30)))
        self.assertTrue(is_open_at("22:00-02:00", at(1, 0)))
        self.assertFalse(is_open_at("22:00-02:00", at(3, 0)))
        self.assertTrue(is_open_at("06:00-11:00, 13:00-22:00", at(14, 0)))
        self.assertIsNone(is_open_at("Mo-Fr 08:00-17:00", at(10, 0)))  # never guess
        self.assertIsNone(is_open_at(None, at(10, 0)))
        self.assertIsNone(is_open_at("07:00 - 23:00", None))


class TestTrafficAnalysis(unittest.TestCase):
    def test_stale_edges_are_not_used(self) -> None:
        def mut(p):
            for e in p["traffic"]:
                e["observed_at"] = "2026-09-27T10:00:00+07:00"
        res = run_driver_engine(load_full(mut), ctx(), prefs()).objectives["safety_comfort"]
        self.assertIsNone(res.safe_corridors)
        self.assertIn("không đoạn nào dùng được", res.traffic_note or "")
        self.assertEqual(res.status, "partial")

    def test_classification_uses_ratio_to_free_flow(self) -> None:
        def mut(p):
            p["traffic"][0].update(current_speed_kmh=12.0, free_flow_speed_kmh=35.0, congestion_level="thong_thoang")
        res = run_driver_engine(load_full(mut), ctx(), prefs()).objectives["safety_comfort"]
        self.assertTrue(any("Le Duan" in z for z in res.avoid_zones or []))
        self.assertFalse(any("Le Duan" in z for z in res.safe_corridors or []))


class TestRobustness(unittest.TestCase):
    def test_close_race_is_flagged_as_contested(self) -> None:
        rb = analyze_top1(["a", "b"], lambda i, p: {"a": 100.0, "b": 99.9}[i] * p["k"], {"k": 1.0}, cfgmod.ROBUSTNESS_CFG)
        assert rb
        self.assertTrue(rb["contested"])

    def test_sensitive_ranking_reports_flips(self) -> None:
        # a wins only while x is high; a 20% dip in x lets b win
        score = lambda i, p: (p["x"] * 10 if i == "a" else 9.5)  # noqa: E731
        rb = analyze_top1(["a", "b"], score, {"x": 1.0}, cfgmod.ROBUSTNESS_CFG)
        assert rb
        self.assertFalse(rb["stable"])
        self.assertEqual(rb["flips_to"], {"b": 1})

    def test_clear_winner_is_stable(self) -> None:
        rb = analyze_top1(["a", "b"], lambda i, p: {"a": 100.0, "b": 50.0}[i] * p["k"], {"k": 1.0}, cfgmod.ROBUSTNESS_CFG)
        assert rb
        self.assertTrue(rb["stable"])
        self.assertFalse(rb["contested"])
        self.assertAlmostEqual(rb["margin_pct"], 50.0)

    def test_engine_reports_robustness_on_ranked_objectives(self) -> None:
        out = run_driver_engine(load_full(), ctx(), prefs())
        for key in ("max_trip_value", "maintain_position", "rest_spot"):
            self.assertIsNotNone(out.objectives[key].robustness, key)


class TestDirectionPriority(unittest.TestCase):
    def _order(self, out):
        return [r["objective"] for r in out.direction_priority or []]

    def test_imminent_rain_puts_safety_first(self) -> None:
        heavy = [WeatherHour("2026-09-27T15:00", 4.5, 95.0)]
        out = run_driver_engine(create_mock_engine_input(weather_hourly=heavy), ctx(idle_min=10, horizon_min=60), prefs())
        self.assertEqual(self._order(out)[0], "safety_comfort")
        self.assertEqual(out.direction_priority[0]["tier"], 0)

    def test_long_idle_puts_rest_before_earning(self) -> None:
        out = run_driver_engine(load_full(), ctx(idle_min=50), prefs())
        order = self._order(out)
        self.assertEqual(order[0], "rest_spot")
        self.assertLess(order.index("rest_spot"), order.index("max_trip_value"))

    def test_rain_ahead_outranks_earning_but_not_urgent_rest(self) -> None:
        out = run_driver_engine(load_full(), ctx(idle_min=10), prefs())
        order = self._order(out)
        self.assertLess(order.index("safety_comfort"), order.index("max_trip_value"))

    def test_goal_weights_reorder_earning_lenses(self) -> None:
        base = self._order(run_driver_engine(load_full(), ctx(idle_min=10), prefs()))
        weighted = self._order(run_driver_engine(
            load_full(), ctx(idle_min=10), prefs(weights={"maintain_position": 3.0, "max_trip_value": 1.0})
        ))
        self.assertLess(base.index("max_trip_value"), base.index("maintain_position"))
        self.assertLess(weighted.index("maintain_position"), weighted.index("max_trip_value"))

    def test_insufficient_lenses_are_not_ranked_and_go_last(self) -> None:
        out = run_driver_engine(create_mock_engine_input(), ctx(), prefs())
        rows = out.direction_priority or []
        unranked = [r for r in rows if not r["rankable"]]
        self.assertTrue(unranked)
        self.assertTrue(all(r["rank"] is None for r in unranked))
        self.assertTrue(all(not r["rankable"] for r in rows[len(rows) - len(unranked):]))

    def test_no_overall_score_anywhere(self) -> None:
        out = run_driver_engine(load_full(), ctx(), prefs())
        for row in out.direction_priority or []:
            self.assertNotIn("score", " ".join(row.keys()))
        self.assertFalse(hasattr(out, "overall_score"))


class TestValidationAndConfig(unittest.TestCase):
    def test_invalid_context_raises(self) -> None:
        inp = create_mock_engine_input()
        with self.assertRaises(ValueError):
            run_driver_engine(inp, DriverContext(current_lat=123.0, current_lng=106.7), prefs())
        with self.assertRaises(ValueError):
            run_driver_engine(inp, DriverContext(current_lat=10.7, current_lng=106.7, horizon_min=0), prefs())

    def test_negative_goal_weight_raises(self) -> None:
        with self.assertRaises(ValueError):
            run_driver_engine(create_mock_engine_input(), ctx(), prefs(weights={"rest_spot": -1.0}))

    def test_data_quality_warnings_surface_problems(self) -> None:
        def mut(p):
            p["areas"][0]["representative_point"] = {"latitude": 999, "longitude": 0}
            p["pois"].append(copy.deepcopy(p["pois"][0]))
        out = run_driver_engine(load_full(mut), ctx(), prefs())
        joined = " | ".join(out.data_quality_warnings)
        self.assertIn("tọa độ đại diện", joined)
        self.assertIn("Trùng poi_id", joined)

    def test_config_json_has_no_unknown_keys_and_is_coherent(self) -> None:
        with open(cfgmod.CONFIG_FILE, "r", encoding="utf-8") as f:
            override = json.load(f)
        self.assertEqual(cfgmod._unknown_keys(cfgmod.DEFAULTS, override), [])
        self.assertEqual(cfgmod.validate_config(cfgmod.ENGINE_CONFIG), [])

    def test_incoherent_config_is_rejected(self) -> None:
        bad = cfgmod._deep_merge(cfgmod.DEFAULTS, {"rain_tolerance_thresholds": {"low": {"prob_pct": 90.0, "mm": 0.5}}})
        self.assertTrue(any("low.prob_pct" in p for p in cfgmod.validate_config(bad)))
        bad2 = cfgmod._deep_merge(cfgmod.DEFAULTS, {"geo": {"detour_factor": 0.5}})
        self.assertTrue(cfgmod.validate_config(bad2))


class TestAssumptionsAndDeterminism(unittest.TestCase):
    def test_assumptions_reflect_the_data_actually_used(self) -> None:
        out = run_driver_engine(load_full(), ctx(), prefs())
        blob = " ".join(out.assumptions_used)
        self.assertIn("demo/mô phỏng", blob)
        self.assertNotIn("Chưa tích hợp dữ liệu giao thông", blob)  # traffic IS available in this snapshot
        mock = " ".join(run_driver_engine(create_mock_engine_input(), ctx(), prefs()).assumptions_used)
        self.assertIn("Giao thông: trạng thái 'missing'", mock)

    def test_full_pipeline_is_deterministic(self) -> None:
        a = run_driver_engine(load_full(), ctx(), prefs())
        b = run_driver_engine(load_full(), ctx(), prefs())
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
