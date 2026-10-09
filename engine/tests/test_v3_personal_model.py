"""Tests for the personal model built from the DRIVER'S OWN data (trip log + tariff + wait spells), uncertainty
intervals, trade-off matrix, data roadmap and decision boundaries.

The logs below are SYNTHETIC TEST FIXTURES generated deterministically; they only exist to pin behaviour.
"""

from __future__ import annotations

import copy
import json
import random
import unittest
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

from engine.src.adapter import load_engine_input_from_dict
from engine.src.engine import run_driver_engine
from engine.src.mock_data import create_default_driver_context, create_default_driver_preferences

ROOT = Path(__file__).resolve().parents[2]
FULL = ROOT / "data" / "fixtures" / "hcmc_full_simulated_snapshot.json"
NOW = datetime(2026, 10, 6, 19, 35)  # generated_at used by `no_driver_payload` (local time, UTC+7)
A_FARE, B_FARE = 12000, 4800  # the tariff the synthetic driver "really" has
PROFILE = {"fare_base_vnd": A_FARE, "fare_per_km_vnd": B_FARE, "fuel_l_per_100km": 2.2, "fuel_price_vnd_per_l": 24000,
           "target_vnd_per_hour": 90000}
# zone: (lat, lng, mean trip km, mean speed km/h, mean wait min)
ZONES = {"A": (10.7725, 106.6980, 4.5, 20.0, 6.0), "B": (10.7830, 106.6850, 3.5, 18.0, 9.0), "C": (10.8010, 106.6790, 7.0, 24.0, 12.0)}


def make_log(seed: int = 7, days: int = 12, per_day: int = 6, hour: int = 17, minute: int = 30,
             with_waits: bool = False) -> list[dict] | tuple[list[dict], list[dict]]:
    """Trips whose net = A + B·km (+ noise); with_waits=True also returns the wait spells that preceded each trip."""
    rng = random.Random(seed)
    log: list[dict] = []
    spells: list[dict] = []
    for day in range(days):
        cur = (NOW - timedelta(days=days - day)).replace(hour=hour, minute=minute, second=0, microsecond=0)
        for i in range(per_day):
            la, lo, mean_km, speed, mean_wait = ZONES[rng.choice(sorted(ZONES))]
            wait = rng.expovariate(1.0 / mean_wait)
            la, lo = la + rng.uniform(-0.001, 0.001), lo + rng.uniform(-0.001, 0.001)
            spells.append({"spell_id": f"w{day}_{i}", "start": cur.isoformat(), "end": (cur + timedelta(minutes=wait)).isoformat(),
                           "lat": la, "lng": lo, "ended_by": "trip"})
            cur += timedelta(minutes=wait)
            km = mean_km * rng.uniform(0.8, 1.2)
            d = km / speed * 60.0
            log.append({
                "trip_id": f"t{day}_{i}", "started_at": cur.isoformat(),
                "pickup_lat": la, "pickup_lng": lo,
                "net_vnd": A_FARE + B_FARE * km + rng.uniform(-1500, 1500), "duration_min": d, "distance_km": km,
            })
            cur += timedelta(minutes=d)
    return (log, spells) if with_waits else log


def no_driver_payload(log: list[dict] | None = None, spells: list[dict] | None = None, profile: bool = False) -> dict:
    """The simulated fixture WITHOUT its driver-owned sections (no market data exists in it any more), re-dated to NOW."""
    p = json.load(open(FULL, encoding="utf-8"))
    for key in ("trip_log", "wait_spells", "driver_profile"):
        p.pop(key, None)
    p["generated_at"] = NOW.isoformat() + "+07:00"
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
                        "pickup_lat": 10.7600, "pickup_lng": 106.7200, "net_vnd": A_FARE + B_FARE * 20, "duration_min": 40,
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
                             "pickup_lat": ZONES["C"][0], "pickup_lng": ZONES["C"][1], "net_vnd": A_FARE + B_FARE * 20, "duration_min": 50,
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
        self.full = json.load(open(FULL, encoding="utf-8"))  # simulated driver data: tariff + 72 trips + 97 wait spells

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
