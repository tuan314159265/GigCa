"""Tests for the community pool (k-anonymity + empirical-Bayes shrinkage) and the earnings-text importer."""

from __future__ import annotations

import random
import unittest

from engine.src.adapter import parse_trip_log
from engine.src.earnings_import import parse_earnings_text
from engine.src.ml.community import Contribution, pool, shrink_to_community

GAZ = {"Bến Thành": (10.7725, 106.698), "Tân Định": (10.789, 106.691)}


class TestCommunityPool(unittest.TestCase):
    def test_cells_below_k_are_suppressed_entirely(self) -> None:
        c = [Contribution(f"d{i}", (1, 1), 100.0 + i) for i in range(5)] + [Contribution(f"d{i}", (2, 2), 50.0) for i in range(4)]
        out = pool(c, k_min=5)
        self.assertEqual(set(out["cells"]), {(1, 1)})
        self.assertEqual(out["suppressed_cells"], 1)
        self.assertEqual(out["cells"][(1, 1)]["n_drivers"], 5)
        self.assertNotIn("values", out["cells"][(1, 1)])  # no per-driver values leave the pool

    def test_a_heavy_contributor_counts_once(self) -> None:
        c = [Contribution("big", (1, 1), 1000.0) for _ in range(500)] + [Contribution(f"d{i}", (1, 1), 100.0) for i in range(4)]
        # driver means: 1000, 100, 100, 100, 100 -> pooled mean 280, not ~1000
        self.assertAlmostEqual(pool(c, 5)["cells"][(1, 1)]["mean"], 280.0)

    def test_nan_is_never_pooled(self) -> None:
        c = [Contribution(f"d{i}", (1, 1), 10.0) for i in range(5)] + [Contribution("x", (1, 1), float("nan"))]
        self.assertEqual(pool(c, 5)["cells"][(1, 1)]["n_drivers"], 5)

    def test_little_own_data_leans_on_community_lots_of_data_trusts_self(self) -> None:
        few = shrink_to_community([140.0, 150.0], prior_mean=100.0, between_var=25.0 ** 2, own_noise_var=40.0 ** 2)
        many = shrink_to_community([140.0 + (i % 5) for i in range(400)], 100.0, 25.0 ** 2, 40.0 ** 2)
        self.assertLess(few["weight_own"], many["weight_own"])
        self.assertTrue(100.0 < few["estimate"] < 145.0)
        self.assertGreater(many["weight_own"], 0.95)
        self.assertEqual(shrink_to_community([], 100.0, 625.0)["estimate"], 100.0)

    def test_pooled_prior_beats_a_cold_start_driver_alone(self) -> None:
        """New driver, 4 trips in a zone: community-shrunk estimate is closer to the truth on average than the raw mean."""
        rng = random.Random(11)
        err_own = err_pool = 0.0
        for _ in range(300):
            comm_mu = 100.0
            truth = comm_mu + rng.gauss(0, 15)                       # this driver's real zone mean
            others = [Contribution(f"o{i}", (0, 0), comm_mu + rng.gauss(0, 15)) for i in range(8)]
            stats = pool(others, 5)["cells"][(0, 0)]
            own = [truth + rng.gauss(0, 40) for _ in range(4)]       # 4 noisy trips
            est = shrink_to_community(own, stats["mean"], stats["between_driver_var"], 40.0 ** 2)["estimate"]
            err_own += abs(sum(own) / 4 - truth)
            err_pool += abs(est - truth)
        self.assertLess(err_pool, err_own)


class TestEarningsImport(unittest.TestCase):
    TEXT = """Lịch sử chuyến ngày 06/10
14:05 · Bến Thành → Quận 3 · 4,2 km · 45.000đ · 18 phút
17:30 | Tân Định -> Phú Nhuận | 3.1km | 38k | 14 phút
Tổng cộng
09:10 · Chợ lạ → Quận 1 · 2 km · 30.000đ · 9 phút
10:00 · Bến Thành → Quận 5 · 6 km · 55.000đ
"""

    def setUp(self) -> None:
        self.res = parse_earnings_text(self.TEXT, "2026-10-06", GAZ)

    def test_complete_lines_become_trips_and_load_in_the_adapter(self) -> None:
        self.assertEqual(len(self.res.trips), 2)
        t = self.res.trips[0]
        self.assertEqual((t["started_at"], t["distance_km"], t["net_vnd"], t["duration_min"]),
                         ("2026-10-06T14:05:00+07:00", 4.2, 45000.0, 18.0))
        self.assertEqual((t["pickup_lat"], t["pickup_lng"]), GAZ["Bến Thành"])
        self.assertEqual(self.res.trips[1]["net_vnd"], 38000.0)  # "38k"
        trips, rejected = parse_trip_log(self.res.trips)
        self.assertEqual((len(trips), rejected), (2, 0))

    def test_nothing_is_invented_for_unknown_place_or_missing_field(self) -> None:
        by = {tuple(n["missing"]): n for n in self.res.needs_input}
        self.assertIn(("pickup_coordinates",), by)            # "Chợ lạ" is not in the gazetteer
        self.assertIn(("duration_min",), by)                  # the last line has no duration
        self.assertEqual(self.res.ignored_lines, 2)           # header + "Tổng cộng"

    def test_amount_is_always_flagged_for_confirmation(self) -> None:
        self.assertTrue(all(t["amount_to_confirm"] for t in self.res.trips))


if __name__ == "__main__":
    unittest.main()
