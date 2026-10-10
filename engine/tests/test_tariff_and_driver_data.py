"""Tariff model (published price list + driver share), what-if table, share check, strict parsing of the driver's own
data, the CSV importer, and a guard that no simulated data is reachable from the product path."""

from __future__ import annotations

import unittest
from pathlib import Path

from data.driver_log_import import attach_driver_log, build_driver_log
from engine.src.adapter import load_engine_input_from_dict, parse_driver_profile, parse_trip_log, parse_wait_spells
from engine.src.config import TARIFF_CFG
from engine.src.engine import run_driver_engine
from engine.src.personal_model import resolve_economics
from engine.src.types import DriverProfile
from engine.src.whatif import break_even_km, build_what_if
from engine.tests.fixtures import create_default_driver_context, create_default_driver_preferences, scenario_payload
from engine.tests.test_v3_personal_model import NOW, make_log, no_driver_payload

ROOT = Path(__file__).resolve().parents[2]


class TestPublishedTariff(unittest.TestCase):
    def setUp(self) -> None:
        self.econ = resolve_economics(None, [])

    def test_config_holds_the_published_tariff(self) -> None:
        e = self.econ
        self.assertEqual((e.fare_base_vnd, e.fare_base_km, e.fare_per_km_vnd, e.fare_per_min_vnd, e.driver_share),
                         (12500, 2.0, 4300, 350, 0.75))
        self.assertEqual(e.tariff_source, "published_tariff")
        self.assertEqual(e.share_source, "config")

    def test_fares_by_hand(self) -> None:
        e = self.econ
        self.assertEqual(e.gross_fare_vnd(1.5, 10.0), 12500)  # inside the first 2 km: no km or minute charge
        self.assertEqual(e.gross_fare_vnd(2.0, 0.0), 12500)
        self.assertEqual(e.gross_fare_vnd(5.0, 9.0), 12500 + 3 * 4300 + 9 * 350)
        # 5 km at 20 km/h: 3 km after the base -> 9 moving minutes billed
        self.assertAlmostEqual(e.net_fare_vnd(5.0, 20.0), 0.75 * (12500 + 3 * 4300 + 9 * 350))
        self.assertAlmostEqual(e.net_per_extra_km(20.0), 0.75 * (4300 + 350 * 3))

    def test_driver_values_override_field_by_field_and_are_labelled(self) -> None:
        notes: list[str] = []
        e = resolve_economics(DriverProfile(fare_per_km_vnd=5000, driver_share=0.6), notes)
        self.assertEqual((e.fare_base_vnd, e.fare_per_km_vnd, e.driver_share), (12500, 5000, 0.6))
        self.assertEqual((e.tariff_source, e.share_source), ("mixed", "driver_input"))
        self.assertTrue(any("Biểu cước trộn" in n for n in notes))
        self.assertIsNone(resolve_economics(None, [], {**TARIFF_CFG, "fare_base_vnd": None}))


class TestWhatIf(unittest.TestCase):
    def test_available_without_any_driver_data_and_labelled(self) -> None:
        out = run_driver_engine(load_engine_input_from_dict(no_driver_payload()),
                                create_default_driver_context(), create_default_driver_preferences())
        wi = out.what_if
        self.assertIsNotNone(wi)
        self.assertEqual(wi["tariff"]["source"], "published_tariff")
        self.assertEqual(wi["speed_source"], "assumed_config")
        two_km = next(r for r in wi["rows"] if r["trip_km"] == 2)
        self.assertEqual(two_km["customer_fare_vnd"], 12500)
        self.assertEqual(two_km["net_before_fuel_vnd"], round(12500 * 0.75))
        self.assertIn("yield_at_low_share_vnd_per_hour", two_km)  # sensitivity to the assumed share
        self.assertLess(two_km["yield_at_low_share_vnd_per_hour"], two_km["yield_vnd_per_hour"])
        self.assertTrue(any("12,500đ" in a and "75%" in a for a in out.assumptions_used))
        self.assertEqual(out.data_tier["tier"], 0)

    def test_break_even_and_min_fare_follow_the_goal(self) -> None:
        econ = resolve_economics(DriverProfile(fuel_l_per_100km=2.2, fuel_price_vnd_per_l=24000, target_vnd_per_hour=60000), [])
        wi = build_what_if(econ)
        for r in wi["rows"]:
            self.assertAlmostEqual(r["min_customer_fare_for_target_vnd"], r["min_fare_for_target_vnd"] / 0.75, delta=1)
            self.assertEqual(r["tariff_meets_target"], r["yield_vnd_per_hour"] >= 60000)
        be = {b["wait_min"]: b["min_trip_km"] for b in wi["break_even_trip_km"]}
        if be[5] is not None and be[10] is not None:
            self.assertLessEqual(be[5], be[10])  # waiting longer needs a longer trip to reach the same goal
        unreachable = resolve_economics(DriverProfile(target_vnd_per_hour=500000), [])
        self.assertIsNone(break_even_km(unreachable, 20.0, 22.0))


class TestShareCheck(unittest.TestCase):
    def test_log_paid_at_half_the_tariff_is_flagged(self) -> None:
        log = make_log()
        for t in log:
            t["net_vnd"] = t["net_vnd"] * 0.5 / 0.75  # this driver really keeps ~50%, not 75%
        out = run_driver_engine(load_engine_input_from_dict(no_driver_payload(log, profile=True)),
                                create_default_driver_context(lat=10.7725, lng=106.698), create_default_driver_preferences())
        check = out.personal_model["tariff"]["share_check"]
        self.assertTrue(check["flagged"])
        self.assertAlmostEqual(check["median_observed_share"], 0.5, delta=0.05)
        self.assertTrue(any("Tỷ lệ thực nhận quan sát" in a for a in out.assumptions_used))

    def test_log_matching_the_tariff_is_not_flagged(self) -> None:
        out = run_driver_engine(load_engine_input_from_dict(no_driver_payload(make_log(), profile=True)),
                                create_default_driver_context(lat=10.7725, lng=106.698), create_default_driver_preferences())
        self.assertFalse(out.personal_model["tariff"]["share_check"]["flagged"])


class TestStrictDriverData(unittest.TestCase):
    def test_trip_without_required_field_is_rejected_and_counted(self) -> None:
        good = {"trip_id": "a", "started_at": "2026-10-01T10:00:00+07:00", "pickup_lat": 10.77, "pickup_lng": 106.70,
                "net_vnd": 30000, "duration_min": 15}
        rows = [good, {**good, "trip_id": None}, {**good, "trip_id": "b", "duration_min": 0},
                {**good, "trip_id": "c", "started_at": "hôm qua"}, {**good, "trip_id": "d", "distance_km": -3}]
        rep: dict[str, int] = {}
        trips, rejected = parse_trip_log(rows, rep)
        self.assertEqual([t.trip_id for t in trips], ["a", "d"])
        self.assertEqual(rejected, 3)
        self.assertIsNone(trips[1].distance_km)  # impossible optional value dropped, trip kept, and counted
        self.assertEqual(rep["cu_ly_bo_qua"], 1)

    def test_wait_spell_rules(self) -> None:
        ok = {"spell_id": "w1", "start": "2026-10-01T10:00:00+07:00", "end": "2026-10-01T10:12:00+07:00",
              "lat": 10.77, "lng": 106.70, "ended_by": "moved", "rain_mm": -1}
        spells, rejected = parse_wait_spells([ok, {**ok, "spell_id": "w2", "end": "2026-10-01T09:00:00+07:00"},
                                              {**ok, "spell_id": "w3", "ended_by": "lunch"}, {**ok, "spell_id": ""}])
        self.assertEqual([s.spell_id for s in spells], ["w1"])
        self.assertEqual(rejected, 3)
        self.assertIsNone(spells[0].rain_mm)

    def test_share_must_be_a_fraction(self) -> None:
        prof, bad = parse_driver_profile({"driver_share": 75, "fare_per_min_vnd": 350})
        self.assertIsNone(prof.driver_share)
        self.assertEqual(bad, ["driver_share"])
        self.assertEqual(prof.fare_per_min_vnd, 350)


class TestCsvImport(unittest.TestCase):
    def test_rows_are_validated_with_reasons(self) -> None:
        trips = [
            {"trip_id": "t1", "started_at": "2026-10-12 17:42", "pickup_lat": "10.7725", "pickup_lng": "106.698",
             "net_vnd": "21.412", "duration_min": "14", "distance_km": "5"},
            {"trip_id": "t2", "started_at": "2026-10-12 18:10", "pickup_lat": "10.7725", "pickup_lng": "106.698",
             "net_vnd": "", "duration_min": "10"},
            {"trip_id": "t1", "started_at": "2026-10-12 18:30", "pickup_lat": "10.77", "pickup_lng": "106.69",
             "net_vnd": "20000", "duration_min": "9"},
        ]
        waits = [{"spell_id": "w1", "start": "2026-10-12 17:30", "end": "2026-10-12 17:41", "lat": "10.7725",
                  "lng": "106.698", "ended_by": "trip"}]
        log = build_driver_log(trips, waits, {"target_vnd_per_hour": "90.000", "driver_share": "0,75"},
                               driver_pseudonym="D01", consent_reference="test", collected_via="test")
        rep = log["import_report"]
        self.assertEqual(rep["trips"]["accepted"], 1)
        self.assertEqual(log["trip_log"][0]["net_vnd"], 21412)
        self.assertTrue(log["trip_log"][0]["started_at"].endswith("+07:00"))
        reasons = " | ".join(x["reason"] for x in rep["trips"]["rejected"])
        self.assertIn("net_vnd", reasons)
        self.assertIn("trùng", reasons)
        self.assertEqual(log["driver_profile"], {"target_vnd_per_hour": 90000, "driver_share": 0.75})
        merged = attach_driver_log(scenario_payload(NOW), log)
        self.assertEqual(len(merged["trip_log"]), 1)

    def test_only_real_logs_can_be_attached(self) -> None:
        log = build_driver_log([], [], None, driver_pseudonym="D01", consent_reference="x", collected_via="x")
        log["provenance"]["kind"] = "simulated"
        with self.assertRaises(ValueError):
            attach_driver_log({}, log)


class TestNoSimulatedDataInProductPath(unittest.TestCase):
    def test_no_simulator_or_simulated_fixture_left(self) -> None:
        self.assertFalse((ROOT / "engine" / "src" / "ml" / "simulate.py").exists())
        self.assertFalse((ROOT / "engine" / "src" / "mock_data.py").exists())
        self.assertEqual(list((ROOT / "data" / "fixtures").glob("*.json")), [])

    def test_product_code_never_imports_test_inputs(self) -> None:
        offenders = []
        for folder in ("engine/src", "data", "scripts", "web"):
            for path in (ROOT / folder).rglob("*.py"):
                text = path.read_text(encoding="utf-8")
                if "engine.tests" in text or "mock_data" in text or "unit_test_scenario" in text:
                    offenders.append(str(path.relative_to(ROOT)))
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
