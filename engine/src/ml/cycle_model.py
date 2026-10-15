"""Cycle-yield quantile model with split-conformal calibration (CQR).

A CYCLE = one completed wait (ended by a trip) + the paid trip that followed. Its realised yield is
    (net_vnd - c·km) / ((wait_min + duration_min) / 60)        [VND/hour, fuel of the paid leg included]
Gradient-boosted quantile regressors predict the 10th/50th/90th percentile of that yield from the context (hour, weekday,
rain, place). Conformalized Quantile Regression (Romano et al. 2019) then widens/narrows the band using a time-ordered
calibration slice so that, on exchangeable data, ~(1 - alpha) of future cycles fall inside it. `backtest_cycles`
checks that claim on a later, untouched slice and also reports the naive "mean ± z·sd" band for comparison.

Limits (stated, not hidden): only cycles whose wait ended with a trip are observed (a wait that ended by moving/offline
has no trip), so yields are slightly optimistic; the band describes ONE future cycle, not the long-run average.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import numpy as np
from sklearn.ensemble import GradientBoostingRegressor

from engine.src.config import ML_CFG, TIME_CFG
from engine.src.geo import haversine_m, valid_point
from engine.src.ml.wait_model import _context
from engine.src.timeutil import parse_local
from engine.src.types import TripRecord, WaitSpell

_MATCH_S = 300.0
_MATCH_M = 500.0


@dataclass(frozen=True)
class Cycle:
    start: datetime
    lat: float
    lng: float
    rain_mm: float | None
    km: float
    net_vnd: float
    wait_min: float
    duration_min: float
    yield_vnd_per_hour: float


def build_cycles(trips: list[TripRecord], spells: list[WaitSpell], fuel_vnd_per_km: float,
                 *, matching_report: dict[str, Any] | None = None) -> list[Cycle]:
    """Infer only mutually unique causal pairs from ONE driver's records.

    started_at remains pickup time. The schema has no trusted acceptance link, so
    no match is labeled confirmed. Unmatched records remain untouched in the log.
    Pickup travel time/fuel are still excluded from the legacy cycle target.
    """
    from collections import Counter
    trip_counts = Counter(t.trip_id for t in trips)
    spell_counts = Counter(w.spell_id for w in spells)
    off = int(TIME_CFG["local_utc_offset_minutes"])
    ended: dict[int, list[tuple[datetime, datetime, WaitSpell]]] = {}
    for w in spells:
        if w.ended_by != "trip" or spell_counts[w.spell_id] != 1:
            continue
        a, b = parse_local(w.start, off), parse_local(w.end, off)
        if a is None or b is None or b < a or valid_point({"latitude": w.lat, "longitude": w.lng}) is None:
            continue
        ended.setdefault(int(b.timestamp() // 60), []).append((a, b, w))
    cycles: list[Cycle] = []
    entries = []
    claims: Counter = Counter()
    for t in sorted(trips, key=lambda x: (x.started_at, x.trip_id)):
        s = parse_local(t.started_at, off)
        if (trip_counts[t.trip_id] != 1 or s is None or t.distance_km is None
                or not math.isfinite(t.distance_km) or t.distance_km <= 0
                or not math.isfinite(t.duration_min) or t.duration_min <= 0 or not math.isfinite(t.net_vnd)
                or valid_point({"latitude": t.pickup_lat, "longitude": t.pickup_lng}) is None):
            entries.append((t, s, [], "invalid_trip"))
            continue
        m = int(s.timestamp() // 60)
        candidates = []
        for mm in range(m - 5, m + 1):
            for a, b, w in ended.get(mm, []):
                gap = (s - b).total_seconds()
                if 0 <= gap <= _MATCH_S and haversine_m(w.lat, w.lng, t.pickup_lat, t.pickup_lng) <= _MATCH_M:
                    candidates.append((a, b, w))
                    claims[w.spell_id] += 1
        entries.append((t, s, candidates, None))
    rows = []
    for t, s, candidates, error in entries:
        if error or not candidates:
            rows.append({"trip_id": t.trip_id, "status": "invalid" if error else "unmatched",
                         "reason": error or "no_candidate_within_5min_500m"})
            continue
        if len(candidates) != 1 or claims[candidates[0][2].spell_id] != 1:
            rows.append({"trip_id": t.trip_id, "status": "ambiguous", "reason": "multiple_trips_or_waits",
                         "candidate_spell_ids": sorted(w.spell_id for _, _, w in candidates)})
            continue
        a, b, w = candidates[0]
        wait = (b - a).total_seconds() / 60.0
        hours = (wait + t.duration_min) / 60.0
        if hours <= 0:
            continue
        cycles.append(Cycle(a, t.pickup_lat, t.pickup_lng, w.rain_mm, t.distance_km, t.net_vnd, wait, t.duration_min,
                            (t.net_vnd - fuel_vnd_per_km * t.distance_km) / hours))
        rows.append({"trip_id": t.trip_id, "spell_id": w.spell_id, "status": "inferred",
                     "pickup_gap_min": (s-b).total_seconds()/60,
                     "straight_distance_m": haversine_m(w.lat, w.lng, t.pickup_lat, t.pickup_lng)})
    cycles.sort(key=lambda c: c.start)
    if matching_report is not None:
        counts = Counter(row["status"] for row in rows)
        matching_report.update({"policy": "mutually_unique_causal_5min_500m_v1", "max_gap_seconds": _MATCH_S,
                                "max_straight_distance_m": _MATCH_M, "trips": len(trips),
                                "counts": {k: counts[k] for k in ("confirmed", "inferred", "ambiguous", "unmatched", "invalid")},
                                "rows": rows,
                                "note": "Only inferred pairs; pickup travel time/fuel excluded. Selection favors nearby pickups."})
    return cycles


def _features(cs: list[Cycle], ref: tuple[float, float]) -> np.ndarray:
    return np.asarray([_context(c.start, c.lat, c.lng, c.rain_mm, ref) for c in cs], dtype=float)


def _qreg(q: float, seed: int, params: dict[str, Any] | None = None) -> GradientBoostingRegressor:
    options = dict(n_estimators=80, max_depth=2, learning_rate=0.06, subsample=0.8, min_samples_leaf=8)
    if params:
        options.update(params)
    return GradientBoostingRegressor(loss="quantile", alpha=q, random_state=seed, **options)


class CycleYieldModel:
    def __init__(self, alpha: float, seed: int, quantile_params: dict[str, dict[str, Any]] | None = None) -> None:
        self.alpha, self.seed = alpha, seed
        self.ref: tuple[float, float] = (0.0, 0.0)
        self.q_hat = 0.0
        self._lo = self._md = self._hi = None
        self.quantile_params = quantile_params or {}

    def fit(self, train: list[Cycle], calib: list[Cycle]) -> "CycleYieldModel":
        self.ref = (float(np.mean([c.lat for c in train])), float(np.mean([c.lng for c in train])))
        X, y = _features(train, self.ref), np.asarray([c.yield_vnd_per_hour for c in train])
        self._lo = _qreg(self.alpha / 2, self.seed, self.quantile_params.get('lower')).fit(X, y)
        self._md = _qreg(0.5, self.seed, self.quantile_params.get('median')).fit(X, y)
        self._hi = _qreg(1 - self.alpha / 2, self.seed, self.quantile_params.get('upper')).fit(X, y)
        Xc, yc = _features(calib, self.ref), np.asarray([c.yield_vnd_per_hour for c in calib])
        scores = np.maximum(self._lo.predict(Xc) - yc, yc - self._hi.predict(Xc))
        n = len(scores)
        level = min(1.0, math.ceil((n + 1) * (1 - self.alpha)) / n)
        self.q_hat = float(np.quantile(scores, level, method="higher"))
        return self

    def predict_many(self, X: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        lo, md, hi = self._lo.predict(X), self._md.predict(X), self._hi.predict(X)
        lo, hi = lo - self.q_hat, hi + self.q_hat
        return np.minimum(lo, md), md, np.maximum(hi, md)

    def predict(self, dt: datetime, lat: float, lng: float, rain: float | None) -> dict[str, int]:
        X = np.asarray([_context(dt, lat, lng, rain, self.ref)], dtype=float)
        lo, md, hi = self.predict_many(X)
        return {"low": int(round(lo[0])), "median": int(round(md[0])), "high": int(round(hi[0]))}


def _split(cycles: list[Cycle], cfg: dict[str, Any]) -> tuple[list[Cycle], list[Cycle], list[Cycle]]:
    n = len(cycles)
    n_test, n_cal = int(n * float(cfg["test_fraction"])), int(n * float(cfg["calibration_fraction"]))
    return cycles[: n - n_cal - n_test], cycles[n - n_cal - n_test: n - n_test], cycles[n - n_test:]


def backtest_cycles(cycles: list[Cycle], cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = cfg or ML_CFG
    if len(cycles) < int(cfg["min_cycles"]):
        return {"status": "insufficient", "n_cycles": len(cycles), "reason": f"cần ≥ {int(cfg['min_cycles'])} chu kỳ chuyến (hiện {len(cycles)})"}
    alpha, seed = float(cfg["conformal_alpha"]), int(cfg["random_state"])
    train, cal, test = _split(cycles, cfg)
    m = CycleYieldModel(alpha, seed).fit(train, cal)
    X, y = _features(test, m.ref), np.asarray([c.yield_vnd_per_hour for c in test])
    lo, md, hi = m.predict_many(X)
    ytr = np.asarray([c.yield_vnd_per_hour for c in train])
    z = 1.2816 if abs(alpha - 0.2) < 1e-9 else float(__import__("scipy.stats", fromlist=["norm"]).norm.ppf(1 - alpha / 2))
    nlo, nhi = ytr.mean() - z * ytr.std(ddof=1), ytr.mean() + z * ytr.std(ddof=1)
    cover = float(np.mean((y >= lo) & (y <= hi)))
    naive_cover = float(np.mean((y >= nlo) & (y <= nhi)))
    nominal = 1.0 - alpha
    return {
        "status": "ok", "n_cycles": len(cycles), "n_train": len(train), "n_calibration": len(cal), "n_test": len(test),
        "nominal_coverage": nominal,
        "coverage_conformal": round(cover, 3), "mean_width_conformal_vnd": int(round(float(np.mean(hi - lo)))),
        "coverage_naive": round(naive_cover, 3), "mean_width_naive_vnd": int(round(float(nhi - nlo))),
        "mae_median_model_vnd": int(round(float(np.mean(np.abs(y - md))))),
        "mae_train_mean_vnd": int(round(float(np.mean(np.abs(y - ytr.mean()))))),
        # only UNDER-coverage is a failure (the band would overpromise); None = too few test cycles to judge
        "calibrated": None if len(test) < 30 else bool(cover >= nominal - 0.10),
        "note": "khoảng cho MỘT chu kỳ (chờ + chuyến) kế tiếp, không phải năng suất trung bình dài hạn",
    }


def fit_cycle_model(cycles: list[Cycle], cfg: dict[str, Any] | None = None) -> CycleYieldModel | None:
    cfg = cfg or ML_CFG
    if len(cycles) < int(cfg["min_cycles"]):
        return None
    n_cal = max(15, int(len(cycles) * float(cfg["calibration_fraction"])))
    return CycleYieldModel(float(cfg["conformal_alpha"]), int(cfg["random_state"])).fit(cycles[:-n_cal], cycles[-n_cal:])
