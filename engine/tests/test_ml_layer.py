"""Tests for the ML layer (v5): wait-model gate, conformal cycle band, bandit posterior, Vietnamese intake and the
number guard.

There is NO simulator and NO claim of real-world accuracy here: the inputs are TEST INPUTS built in the test files
(waits that do not depend on context, the deterministic test driver log). The tests pin the MECHANICS — the gate refuses
a model without evidence, probabilities are valid, results are deterministic, too little data is reported — not how well
a model would do on real drivers (that can only be measured on real logs, through the same backtest gate).
"""

from __future__ import annotations

import copy
import json
import random
import unittest
from datetime import datetime, timedelta

from engine.src.adapter import parse_trip_log, parse_wait_spells
from engine.src.explain_check import grounded_explanation, numbers_in, verify_numbers
from engine.src.intake import apply_to_payload, llm_extract, parse_intake_vi, validate_extraction
from engine.src.ml.bandit import posterior_table
from engine.src.ml.cycle_model import backtest_cycles, build_cycles, fit_cycle_model
from engine.src.ml.wait_model import backtest_wait, fit_wait_model
from engine.src.types import WaitSpell
from engine.tests.fixtures import TEST_PROFILE, full_scenario_payload, make_log
from engine.tests.test_v3_personal_model import no_driver_payload, run

FUEL_VND_PER_KM = TEST_PROFILE["fuel_l_per_100km"] * TEST_PROFILE["fuel_price_vnd_per_l"] / 100.0
_LOG, _SPELLS = make_log(days=14, per_day=6, with_waits=True)
TRIPS, _ = parse_trip_log(_LOG)
LOG_SPELLS, _ = parse_wait_spells(_SPELLS)


def null_spells(seed: int, n: int = 300) -> list[WaitSpell]:
    """Waits that do NOT depend on hour, rain or place: nothing for a context model to find."""
    rng = random.Random(seed)
    out = []
    for i in range(n):
        w = rng.expovariate(1 / 9)
        ended = "trip" if w < 25 else "moved"
        w = min(w, 25)
        st = datetime(2026, 9, 1, rng.randint(7, 22), rng.randint(0, 59)) + timedelta(days=i // 10)
        out.append(WaitSpell(f"s{i}", st.isoformat() + "+07:00", (st + timedelta(minutes=w)).isoformat() + "+07:00",
                             10.77 + rng.uniform(-0.001, 0.001), 106.69 + rng.uniform(-0.001, 0.001), ended))
    return out


SPELLS = null_spells(11)


class TestWaitModel(unittest.TestCase):
    def test_backtest_reports_against_the_baseline_by_time(self) -> None:
        bt = backtest_wait(SPELLS)
        self.assertEqual(bt["status"], "ok")
        for key in ("passes", "beats_baseline", "context_helps", "split_at"):
            self.assertIn(key, bt)

    def test_probabilities_are_valid_and_monotone(self) -> None:
        m = fit_wait_model(SPELLS)
        self.assertIsNotNone(m)
        p = m.predict(datetime(2026, 10, 7, 12, 0), 10.77, 106.69, None, [10, 20])
        self.assertTrue(0 <= p["p_le"]["10"] <= p["p_le"]["20"] <= 1)
        self.assertGreaterEqual(p["expected_wait_min"], 0)

    def test_gate_keeps_baseline_when_there_is_no_context_signal(self) -> None:
        # waits independent of hour/rain/place: the context ablation must NOT show a gain
        helps = [backtest_wait(null_spells(s))["context_helps"] for s in (1, 3, 4)]
        self.assertFalse(any(helps))
        self.assertFalse(any(backtest_wait(null_spells(s))["passes"] for s in (1, 3, 4)))

    def test_too_few_spells_is_reported_not_modelled(self) -> None:
        bt = backtest_wait(SPELLS[:30])
        self.assertEqual(bt["status"], "insufficient")
        self.assertFalse(bt["passes"])
        self.assertIsNone(fit_wait_model(SPELLS[:30]))

    def test_censored_spells_are_not_counted_as_long_waits(self) -> None:
        # every spell ends offline: no event is ever observed, so nothing can be learned (not "waits are very long")
        off = [WaitSpell(s.spell_id, s.start, s.end, s.lat, s.lng, "offline") for s in SPELLS]
        self.assertIsNone(fit_wait_model(off))

    def test_deterministic(self) -> None:
        self.assertEqual(backtest_wait(SPELLS), backtest_wait(SPELLS))


class TestCycleBand(unittest.TestCase):
    def test_cycles_pair_each_trip_with_its_wait(self) -> None:
        cycles = build_cycles(TRIPS, LOG_SPELLS, FUEL_VND_PER_KM)
        self.assertEqual(len(cycles), len(TRIPS))
        self.assertTrue(all(c.wait_min >= 0 and c.km > 0 for c in cycles))

    def test_band_is_ordered_and_needs_enough_cycles(self) -> None:
        cycles = build_cycles(TRIPS, LOG_SPELLS, FUEL_VND_PER_KM)
        m = fit_cycle_model(cycles)
        self.assertIsNotNone(m)
        p = m.predict(datetime(2026, 9, 27, 13, 0), 10.7725, 106.698, 0.0)
        self.assertLessEqual(p["low"], p["median"])
        self.assertLessEqual(p["median"], p["high"])
        self.assertIsNone(fit_cycle_model(cycles[:20]))
        self.assertEqual(backtest_cycles(cycles[:20])["status"], "insufficient")


class TestBandit(unittest.TestCase):
    def test_low_evidence_zone_with_a_real_chance_is_flagged_explore(self) -> None:
        rng = random.Random(3)
        rewards = {
            "known_good": [rng.gauss(100_000, 30_000) for _ in range(120)],
            "new_zone": [rng.gauss(108_000, 30_000) for _ in range(4)],
            "known_bad": [rng.gauss(80_000, 30_000) for _ in range(120)],
        }
        tab = posterior_table(rewards, 5.0, 4000, 7)
        self.assertAlmostEqual(sum(v["p_best"] for v in tab.values()), 1.0, places=2)
        self.assertTrue(tab["new_zone"]["explore"])
        self.assertFalse(tab["known_bad"]["explore"])
        self.assertEqual(tab, posterior_table(rewards, 5.0, 4000, 7))  # fixed seed -> deterministic


class TestEngineIntegration(unittest.TestCase):
    def test_ml_block_reports_the_gate_and_is_consistent_with_its_use(self) -> None:
        out = run(full_scenario_payload(), lat=10.7725, lng=106.698)
        ml = out.ml_insights
        self.assertIsNotNone(ml)
        wm = ml["wait_model"]
        self.assertIn("backtest", wm)
        if wm["used"]:  # a model may only replace the baseline when it passed the backtest gate
            self.assertTrue(wm["backtest"]["passes"])
            self.assertTrue(any("MÔ HÌNH ML" in a for a in out.assumptions_used))
        else:
            self.assertFalse(any("MÔ HÌNH ML" in a for a in out.assumptions_used))

    def test_no_data_means_no_ml_block(self) -> None:
        self.assertIsNone(run(no_driver_payload()).ml_insights)

    def test_baseline_is_kept_when_gate_fails(self) -> None:
        p = full_scenario_payload()
        p["wait_spells"] = p["wait_spells"][:40]  # too few spells to backtest
        out = run(p, lat=10.7725, lng=106.698)
        self.assertFalse(out.ml_insights["wait_model"]["used"])

    def test_output_is_deterministic(self) -> None:
        p = full_scenario_payload()
        self.assertEqual(run(copy.deepcopy(p), lat=10.7725, lng=106.698), run(copy.deepcopy(p), lat=10.7725, lng=106.698))


class TestIntake(unittest.TestCase):
    TEXT = ("Cước mở cửa 12k, 4.800đ/km, xe ăn 2,2 lít/100km, giá xăng 24.000. Tôi muốn kiếm 100k/giờ, "
            "mưa là nghỉ, không đi quá 3km.")

    def test_parses_published_tariff_sentence(self) -> None:
        r = parse_intake_vi("2 km đầu: 12.500 đồng, mỗi km tiếp theo: 4.300 đồng, cộng 350 đồng/phút. Tài xế nhận 75%.")
        self.assertEqual(r.profile, {"fare_base_km": 2.0, "fare_base_vnd": 12500.0, "fare_per_km_vnd": 4300.0,
                                     "fare_per_min_vnd": 350.0, "driver_share": 0.75})
        self.assertEqual(r.unparsed, [])
        self.assertEqual(validate_extraction("nhận 75%", {"driver_share": 0.75}).profile, {"driver_share": 0.75})

    def test_parses_profile_preferences_and_context(self) -> None:
        r = parse_intake_vi(self.TEXT)
        self.assertEqual(r.profile, {"fare_per_km_vnd": 4800.0, "fare_base_vnd": 12000.0, "fuel_l_per_100km": 2.2,
                                     "fuel_price_vnd_per_l": 24000.0, "target_vnd_per_hour": 100000.0})
        self.assertEqual(r.preferences, {"rain_tolerance_level": "low"})
        self.assertEqual(r.context, {"max_reposition_km": 3.0})
        self.assertTrue(r.needs_confirmation)

    def test_out_of_range_is_rejected_not_clamped(self) -> None:
        r = parse_intake_vi("tôi muốn 5k/giờ")
        self.assertEqual(r.profile, {})
        self.assertEqual(r.rejected[0]["field"], "target_vnd_per_hour")

    def test_unexplained_numbers_are_reported(self) -> None:
        r = parse_intake_vi("Tôi muốn 100k/giờ. Thứ bảy tôi chạy 7 tiếng.")
        self.assertEqual(r.profile, {"target_vnd_per_hour": 100000.0})
        self.assertTrue(any("7 tiếng" in u for u in r.unparsed))

    def test_llm_numbers_must_occur_in_the_text(self) -> None:
        text = "muốn 100k/giờ"
        r = llm_extract(text, lambda _p: json.dumps({"target_vnd_per_hour": 100000, "fare_per_km_vnd": 9000, "bogus": 1}))
        self.assertEqual(r.profile, {"target_vnd_per_hour": 100000.0})
        self.assertEqual({x["field"] for x in r.rejected}, {"fare_per_km_vnd", "bogus"})
        self.assertEqual(llm_extract(text, lambda _p: "not json").profile, {"target_vnd_per_hour": 100000.0})  # falls back to rules
        self.assertEqual(validate_extraction(text, {"rain_tolerance_level": "high"}).preferences, {"rain_tolerance_level": "high"})

    def test_apply_merges_into_driver_profile_only(self) -> None:
        out = apply_to_payload({"driver_profile": {"fare_base_vnd": 1000}}, parse_intake_vi("4800đ/km"))
        self.assertEqual(out["driver_profile"], {"fare_base_vnd": 1000, "fare_per_km_vnd": 4800.0})


class TestNumberGuard(unittest.TestCase):
    def setUp(self) -> None:
        self.out = run(full_scenario_payload(), lat=10.7725, lng=106.698)
        self.y = self.out.objectives["max_trip_value"].plan.key_metrics["yield_vnd_per_hour"]

    def test_number_extraction_handles_vietnamese_and_english_formats(self) -> None:
        self.assertEqual(numbers_in("74,314đ/giờ, 4.6km, 87% lúc 17:30, 74.314đ"), [74314.0, 4.6, 87.0, 74314.0])
        self.assertEqual(numbers_in("khoảng 74 nghìn và 2k"), [74000.0, 2000.0])

    def test_grounded_text_passes_and_invented_figures_are_caught(self) -> None:
        self.assertEqual(verify_numbers(f"Khoảng {self.y:,}đ mỗi giờ", self.out), [])
        self.assertEqual(verify_numbers(f"Khoảng {self.y + 50_000:,}đ mỗi giờ", self.out), [self.y + 50_000.0])
        rounded = f"khoảng {round(self.y / 1000)} nghìn đồng mỗi giờ"  # rounding to the unit the text states is fine
        self.assertEqual(verify_numbers(rounded, self.out), [])

    def test_llm_text_with_invented_number_falls_back_to_template(self) -> None:
        bad = grounded_explanation(self.out, lambda _p: "Bạn sẽ kiếm được 999.999đ mỗi giờ.")
        self.assertEqual(bad["source"], "template")
        self.assertIn(999999.0, bad["unsupported_numbers"])
        good = grounded_explanation(self.out, lambda _p: f"Nên chạy khu này, khoảng {self.y:,}đ/giờ.")
        self.assertEqual(good["source"], "llm")
        self.assertEqual(grounded_explanation(self.out)["source"], "template")

        def boom(_p: str) -> str:
            raise RuntimeError("down")
        self.assertEqual(grounded_explanation(self.out, boom)["source"], "template")


if __name__ == "__main__":
    unittest.main()
