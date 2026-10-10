"""Tests for the personal model built from the DRIVER'S OWN data (trip log + tariff + wait spells), uncertainty
intervals, trade-off matrix, data roadmap and decision boundaries.

The logs below are TEST INPUTS built deterministically in engine/tests/fixtures (trips paid by the published tariff);
they pin behaviour and are never used as data.
"""

from __future__ import annotations

import copy
import unittest
from datetime import datetime, timedelta

from engine.src.adapter import load_engine_input_from_dict
from engine.src.engine import run_driver_engine
from engine.tests.fixtures import (
    TEST_PROFILE,
    TEST_ZONES,
    create_default_driver_context,
    create_default_driver_preferences,
    full_scenario_payload,
    make_log as _make_log,
    scenario_payload,
    tariff_net,
)

NOW = datetime(2026, 10, 6, 19, 35)  # generated_at used by `no_driver_payload` (local time, UTC+7)
PROFILE = dict(TEST_PROFILE)
ZONES = {"A": TEST_ZONES["ben_thanh"], "B": (10.7830, 106.6850, 3.5, 18.0, 9.0), "C": (10.8010, 106.6790, 7.0, 24.0, 12.0)}


def make_log(seed: int = 7, days: int = 12, per_day: int = 6, hour: int = 17, minute: int = 30,
             with_waits: bool = False):
    return _make_log(now=NOW, seed=seed, days=days, per_day=per_day, hour=hour, minute=minute, zones=ZONES,
                     with_waits=with_waits)


def no_driver_payload(log: list[dict] | None = None, spells: list[dict] | None = None, profile: bool = False) -> dict:
    """The test scenario WITHOUT driver-owned sections, re-dated to NOW."""
    p = scenario_payload(NOW)
    if log is not None:
        p["trip_log"] = log
    if spells is not None:
        p["wait_spells"] = spells
    if profile:
        p["driver_profile"] = dict(PROFILE)
    return p


def full_driver_payload(**kw) -> dict:
    log, spells = make_log(with_waits=True, **kw)
    return no_driver_payload(log, spells, profile=True)


CTX = dict(lat=10.7725, lng=106.698, idle_min=25, horizon_min=180)


def run(payload: dict, explain: bool = False, **ctx_kw):
    ctx = create_default_driver_context(**{**CTX, **ctx_kw})
    return run_driver_engine(load_engine_input_from_dict(payload), ctx, create_default_driver_preferences("medium"), explain=explain)


class TestPersonalModel(unittest.TestCase):
    def test_without_log_money_lenses_stay_blocked_and_nothing_is_invented(self) -> None:
        out = run(no_driver_payload())
        self.assertIsNone(out.personal_model)
        self.assertEqual(out.objectives["max_trip_value"].status, "insufficient_data")
        self.assertEqual(out.objectives["maintain_position"].status, "insufficient_data")

    def test_log_unlocks_both_earning_lenses_as_partial_low_confidence(self) -> None:
        out = run(full_driver_payload())
        self.assertEqual(out.personal_model["status"], "ok")
        self.assertCountEqual(out.personal_model["used_for"], ["max_trip_value", "maintain_position"])
        for key in ("max_trip_value", "maintain_position"):
            res = out.objectives[key]
            self.assertEqual((res.status, res.confidence), ("partial", "low"))
            self.assertTrue(all(c.data_source == "driver_trip_log" and c.evidence_n >= 4 for c in res.candidates))
            self.assertIn("nhật ký", res.caveat)

    def test_every_yield_carries_n_and_an_ordered_interval(self) -> None:
        out = run(full_driver_payload())
        for c in out.objectives["max_trip_value"].candidates:
            self.assertLessEqual(c.yield_low_vnd_per_hour, c.yield_vnd_per_hour)
            self.assertLessEqual(c.yield_vnd_per_hour, c.yield_high_vnd_per_hour)
            self.assertIn("chuyến thật", c.explanation)

    def test_too_few_trips_is_reported_not_guessed(self) -> None:
        out = run(no_driver_payload(make_log(days=2, per_day=3), profile=True))
        self.assertEqual(out.personal_model["status"], "insufficient")
        self.assertEqual(out.personal_model["used_for"], [])
        self.assertEqual(out.objectives["max_trip_value"].status, "insufficient_data")
        item = next(r for r in out.data_roadmap if r["objective"] == "max_trip_value")
        self.assertIn("/20", item["fastest_unlock"])

    def test_trips_outside_current_daypart_are_not_used(self) -> None:
        out = run(no_driver_payload(make_log(hour=3), profile=True))  # a 03:00 shift says nothing about 19:35
        self.assertEqual(out.personal_model["status"], "insufficient")
        self.assertEqual(out.personal_model["trips_in_daypart"], 0)

    def test_incomplete_trips_are_rejected_and_reported_never_defaulted(self) -> None:
        log = make_log() + [
            {"trip_id": "x1", "started_at": NOW.isoformat(), "pickup_lat": 10.77, "pickup_lng": 106.69},  # no net/duration
            {"trip_id": "x2", "started_at": NOW.isoformat(), "pickup_lat": 10.77, "pickup_lng": 106.69, "net_vnd": -5, "duration_min": 10},
        ]
        out = run(no_driver_payload(log, profile=True))
        self.assertTrue(any("Bỏ 2 chuyến" in a for a in out.assumptions_used))
        self.assertEqual(out.personal_model["trips_in_log"], 72)

    def test_small_zone_is_shrunk_toward_personal_mean(self) -> None:
        log = make_log()
        # 4 spectacular trips (20 km) in a brand-new zone: raw mean 20 km, but only n=4
        for i in range(4):
            log.append({"trip_id": f"lucky{i}", "started_at": (NOW - timedelta(days=1, minutes=10 * i)).replace(hour=18).isoformat(),
                        "pickup_lat": 10.7600, "pickup_lng": 106.7200, "net_vnd": tariff_net(20, 40), "duration_min": 40,
                        "distance_km": 20})
        out = run(no_driver_payload(log, profile=True), lat=10.76, lng=106.72)
        lucky = next(c for c in out.objectives["max_trip_value"].candidates if c.avg_trip_distance_km > 9)
        self.assertLess(lucky.avg_trip_distance_km, 20)  # pulled back
        self.assertGreater(lucky.avg_trip_distance_km, out.personal_model["personal_mean_trip_km"])  # but still above average
        self.assertEqual(lucky.evidence_n, 4)

    def test_more_good_trips_in_a_zone_raises_its_estimate(self) -> None:
        # With a wait term, longer well-paid trips amortise the wait, so more of them in a zone raises that zone's yield.
        log, spells = make_log(with_waits=True)
        base = run(no_driver_payload(log, spells, profile=True), lat=10.8010, lng=106.6790).objectives["max_trip_value"]
        more_log = list(log)
        for i in range(20):  # 20 long, well-paid trips (20 km) from the zone the driver stands in
            more_log.append({"trip_id": f"extra{i}", "started_at": (NOW - timedelta(days=1 + i % 5, minutes=7 * i)).replace(hour=18).isoformat(),
                             "pickup_lat": ZONES["C"][0], "pickup_lng": ZONES["C"][1], "net_vnd": tariff_net(20, 50), "duration_min": 50,
                             "distance_km": 20})
        more = run(no_driver_payload(more_log, spells, profile=True), lat=10.8010, lng=106.6790).objectives["max_trip_value"]
        pick = lambda r: next(c for c in r.candidates if c.reposition_km == 0.0)  # the zone the driver stands in
        self.assertGreater(pick(more).avg_trip_distance_km, pick(base).avg_trip_distance_km)
        self.assertGreater(pick(more).yield_vnd_per_hour, pick(base).yield_vnd_per_hour)

    def test_market_fields_are_stripped_and_never_ranked(self) -> None:
        payload = full_driver_payload()
        payload["areas"][0]["trip_value"] = {"gross_fare_vnd": 95000, "net_value_vnd": 999999, "avg_duration_min": 24, "demand_index": 4.8}
        payload["areas"][0]["destination_distribution"] = {"favorable_dropoff_pct": 99.0, "avg_next_wait_min": 1}
        out = run(payload)
        self.assertTrue(any("Bỏ 6 trường thị trường" in a for a in out.assumptions_used))
        self.assertCountEqual(out.personal_model["used_for"], ["max_trip_value", "maintain_position"])
        cands = out.objectives["max_trip_value"].candidates
        self.assertTrue(cands and all(c.data_source == "driver_trip_log" for c in cands))
        self.assertTrue(all(c.expected_net_value_vnd < 100000 for c in cands))  # the injected 999,999 never entered

    def test_deterministic(self) -> None:
        payload = full_driver_payload()
        self.assertEqual(run(copy.deepcopy(payload), explain=True), run(copy.deepcopy(payload), explain=True))


class TestTradeoffRoadmapBoundaries(unittest.TestCase):
    def setUp(self) -> None:
        self.full = full_scenario_payload()  # TEST scenario + test driver log (72 trips, 72 wait spells)

    def test_rest_cost_is_reference_yield_times_rest_minutes(self) -> None:
        out = run(self.full)
        tm = out.tradeoff_matrix
        rest = next(r for r in tm["rows"] if r["objective"] == "rest_spot")
        self.assertEqual(rest["income_forgone_vnd"], round(tm["reference_yield_vnd_per_hour"] * rest["rest_min"] / 60.0))

    def test_no_reference_yield_means_none_not_zero(self) -> None:
        out = run(no_driver_payload())  # no fare data, no log
        rows = {r["objective"]: r for r in out.tradeoff_matrix["rows"]}
        self.assertIsNone(out.tradeoff_matrix["reference_yield_vnd_per_hour"])
        self.assertFalse(rows["max_trip_value"]["available"])
        self.assertTrue(all(r.get("income_forgone_vnd") is None for r in rows.values()))

    def test_roadmap_names_blocking_datasets_and_skips_fully_backed_lenses(self) -> None:
        real = run(no_driver_payload())
        blocked = {r["objective"]: r for r in real.data_roadmap}
        self.assertIn("max_trip_value", blocked)
        self.assertIn("trip_value", [d["dataset"] for d in blocked["max_trip_value"]["limiting_datasets"]])
        self.assertEqual(blocked["max_trip_value"]["data_tier"]["tier"], 0)
        full = run(self.full)  # rest_spot and safety_comfort are fully backed; only the two earning lenses (own data) remain listed
        self.assertCountEqual([r["objective"] for r in full.data_roadmap], ["max_trip_value", "maintain_position"])

    def test_boundaries_only_when_asked_and_find_the_idle_flip(self) -> None:
        self.assertIsNone(run(self.full).decision_boundaries)
        out = run(self.full, explain=True)
        db = out.decision_boundaries
        self.assertEqual(db["idle"]["if_waiting_longer"]["first_direction"], "rest_spot")
        self.assertGreaterEqual(db["idle"]["if_waiting_longer"]["at_idle_min"], 45)
        # claim is verifiable: re-running at that idle time really changes the first direction
        again = run(self.full, idle_min=db["idle"]["if_waiting_longer"]["at_idle_min"])
        first = next(r["objective"] for r in again.direction_priority if r["rankable"])
        self.assertEqual(first, "rest_spot")
        self.assertTrue(db["summary"])

    def test_position_scan_shows_target_depends_on_where_you_are(self) -> None:
        db = run(self.full, explain=True).decision_boundaries
        targets = {p["trip_target"] for p in db["position"]}
        self.assertGreater(len(targets), 1)


if __name__ == "__main__":
    unittest.main()
