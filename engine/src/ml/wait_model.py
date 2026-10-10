"""Context-aware wait-time model (discrete-time survival / logistic hazard) with an honest gate against the baseline.

A wait spell is cut into `wait_bin_min`-minute bins ("person-period" rows). In each bin the spell either ENDS WITH A TRIP
(label 1) or survives (label 0). Spells that ended because the driver went offline or moved are CENSORED: they only
contribute the bins they fully survived, so a lunch break is no longer mistaken for a long wait. A logistic regression
learns the hazard per bin from the bin index and the context (hour of day, weekend, rain, place and place x hour):

    S(t) = prod_{bins up to t} (1 - h)        P(wait <= t) = 1 - S(t)        E[wait | horizon] = integral of S over [0, H]

Why not per-cell Kaplan-Meier alone: one model shares strength across zones/hours and predicts for hours and places the
driver has little history in. Why a gate: `backtest_wait` cuts the history by TIME (older = train, newer = test) and
compares held-out censored log-likelihood against (a) the per-cell Kaplan-Meier baseline the engine uses today and (b) the
same model WITHOUT context. The model is used only if it beats the baseline AND context helps; otherwise the baseline stays.
Deterministic: no randomness in the fit (lbfgs), all splits by time.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from engine.src.config import ML_CFG, PERSONAL_CFG, POSITION_CFG, TIME_CFG
from engine.src.personal_model import _cell_key, _shrink, km_curve, surv_at
from engine.src.timeutil import parse_local
from engine.src.types import WaitSpell

FAMILY = "logistic"
_MIN_EVENTS = 10
_KM_PER_DEG = 111.32
_C = 0.5  # L2 strength of the logistic hazard (proposed, not tuned on real data)


def _context(dt: datetime, lat: float, lng: float, rain: float | None, ref: tuple[float, float]) -> list[float]:
    """Context features: hour harmonics, rain (unknown = 0, i.e. 'dry'), weekend, position in km relative to `ref`."""
    h = dt.hour + dt.minute / 60.0
    harm = []
    for k in (1, 2, 3):
        harm += [math.sin(2 * math.pi * k * h / 24.0), math.cos(2 * math.pi * k * h / 24.0)]
    r = 0.0 if rain is None else min(max(float(rain), 0.0), 8.0)
    dy = (lat - ref[0]) * _KM_PER_DEG
    dx = (lng - ref[1]) * _KM_PER_DEG * math.cos(math.radians(ref[0]))
    return harm + [r / 8.0, 1.0 if r > 0.2 else 0.0, 1.0 if dt.weekday() >= 5 else 0.0, dx, dy]


def _with_interactions(ctx: list[float]) -> list[float]:
    """place x time-of-day interactions (a zone can be busy at night while another is dead): dx, dy times the first two harmonics."""
    s1, c1, s2, c2 = ctx[0], ctx[1], ctx[2], ctx[3]
    dx, dy = ctx[-2], ctx[-1]
    return ctx + [dx * s1, dx * c1, dy * s1, dy * c1, dx * s2, dx * c2, dy * s2, dy * c2]


@dataclass(frozen=True)
class _Obs:
    start: datetime
    duration_min: float
    event: bool
    lat: float
    lng: float
    rain_mm: float | None


def _observations(spells: list[WaitSpell]) -> list[_Obs]:
    off = int(TIME_CFG["local_utc_offset_minutes"])
    out: list[_Obs] = []
    for w in spells:
        a, b = parse_local(w.start, off), parse_local(w.end, off)
        if a is None or b is None or b < a:
            continue
        out.append(_Obs(a, (b - a).total_seconds() / 60.0, w.ended_by == "trip", w.lat, w.lng, getattr(w, "rain_mm", None)))
    out.sort(key=lambda o: o.start)
    return out


def _bins(cfg: dict[str, Any]) -> tuple[float, int]:
    b = float(cfg["wait_bin_min"])
    return b, int(round(float(PERSONAL_CFG["wait_horizon_min"]) / b))


def _fully_observed_bins(o: _Obs, b: float, nb: int) -> tuple[int, int | None]:
    """(number of bins the spell SURVIVED, 1-based bin of the trip or None)."""
    if o.event:
        j = max(int(math.ceil(o.duration_min / b - 1e-9)), 1)
        return (min(j - 1, nb), j) if j <= nb else (nb, None)
    return min(int(math.floor(o.duration_min / b + 1e-9)), nb), None


class WaitHazardModel:
    family = FAMILY

    def __init__(self, cfg: dict[str, Any], use_context: bool = True) -> None:
        self.cfg, self.use_context = cfg, use_context
        self.b, self.nb = _bins(cfg)
        self.ref: tuple[float, float] = (0.0, 0.0)
        self._scaler = StandardScaler()
        self._clf = LogisticRegression(C=_C, max_iter=2000)

    def _row(self, ctx: list[float] | None, k: int) -> list[float]:
        onehot = [1.0 if i == k else 0.0 for i in range(self.nb)]
        return onehot + ([] if ctx is None else ctx)

    def _ctx(self, o: _Obs) -> list[float] | None:
        return _with_interactions(_context(o.start, o.lat, o.lng, o.rain_mm, self.ref)) if self.use_context else None

    def fit(self, obs: list[_Obs]) -> "WaitHazardModel":
        self.ref = (float(np.mean([o.lat for o in obs])), float(np.mean([o.lng for o in obs])))
        X, y = [], []
        for o in obs:
            surv, j = _fully_observed_bins(o, self.b, self.nb)
            ctx = self._ctx(o)
            for k in range(surv):
                X.append(self._row(ctx, k)); y.append(0)
            if j is not None:
                X.append(self._row(ctx, j - 1)); y.append(1)
        Xa = np.asarray(X, dtype=float)
        if self.use_context:  # scale only the context columns (bin indicators stay 0/1)
            Xa[:, self.nb:] = self._scaler.fit_transform(Xa[:, self.nb:])
        self._clf.fit(Xa, np.asarray(y))
        return self

    def hazards(self, obs: list[_Obs]) -> np.ndarray:
        """Per-bin hazards, shape (n, nb)."""
        rows = []
        for o in obs:
            ctx = self._ctx(o)
            rows += [self._row(ctx, k) for k in range(self.nb)]
        Xa = np.asarray(rows, dtype=float)
        if self.use_context:
            Xa[:, self.nb:] = self._scaler.transform(Xa[:, self.nb:])
        return self._clf.predict_proba(Xa)[:, 1].reshape(len(obs), self.nb)

    def predict(self, dt: datetime, lat: float, lng: float, rain: float | None, thresholds: list[float]) -> dict[str, Any]:
        h = self.hazards([_Obs(dt, 0.0, False, lat, lng, rain)])[0]
        return _summarise(h, self.b, thresholds)


def _surv_bounds(h: np.ndarray) -> np.ndarray:
    """S at the bin boundaries 0..nb."""
    return np.concatenate([[1.0], np.cumprod(1.0 - h)])


def _summarise(h: np.ndarray, b: float, thresholds: list[float]) -> dict[str, Any]:
    S = _surv_bounds(h)
    grid = np.arange(len(S)) * b

    def s_at(t: float) -> float:
        return float(np.interp(t, grid, S))

    median = None  # None = the curve never fell to 50% inside the horizon
    for i in range(len(S) - 1):
        if S[i + 1] <= 0.5:
            frac = (S[i] - 0.5) / max(S[i] - S[i + 1], 1e-12)
            median = float(grid[i] + frac * b)
            break
    return {
        "p_le": {str(int(t) if float(t).is_integer() else t): float(1.0 - s_at(float(t))) for t in thresholds},
        "expected_wait_min": float(np.sum(b * (S[:-1] + S[1:]) / 2.0)),
        "median_wait_min": None if median is None else round(median, 1),
    }


def fit_wait_model(spells: list[WaitSpell], cfg: dict[str, Any] | None = None) -> WaitHazardModel | None:
    """Fit on the whole history. None when there are too few spells or no spell that ended with a trip."""
    cfg = cfg or ML_CFG
    obs = _observations(spells)
    if len(obs) < int(cfg["min_spells"]) or sum(1 for o in obs if o.event) < _MIN_EVENTS:
        return None
    return WaitHazardModel(cfg).fit(obs)


# --------------------------------------------------------------------------- backtest
def _nll(h: np.ndarray, obs: list[_Obs], b: float, nb: int) -> float:
    """Mean negative censored log-likelihood per spell for per-bin hazards h (n, nb)."""
    h = np.clip(h, 1e-6, 1 - 1e-6)
    tot = 0.0
    for i, o in enumerate(obs):
        surv, j = _fully_observed_bins(o, b, nb)
        tot -= float(np.sum(np.log(1.0 - h[i, :surv])))
        if j is not None:
            tot -= float(np.log(h[i, j - 1]))
    return tot / len(obs)


def _baseline_hazards(train: list[_Obs], test: list[_Obs], b: float, nb: int) -> np.ndarray:
    """The engine's current approach in hazard form: per ~600 m cell Kaplan-Meier, hazards shrunk toward the global ones."""
    cell_m, k, min_n = float(PERSONAL_CFG["zone_cell_m"]), float(PERSONAL_CFG["shrinkage_k"]), int(PERSONAL_CFG["min_spells_per_zone"])
    lat_ref = float(np.mean([o.lat for o in train]))

    def hz(group: list[_Obs]) -> np.ndarray:
        steps = km_curve([(o.duration_min, o.event) for o in group])
        s = np.array([surv_at(steps, i * b) for i in range(nb + 1)])
        return np.clip(1.0 - s[1:] / np.maximum(s[:-1], 1e-9), 0.0, 1.0)

    g = hz(train)
    cells: dict[tuple[int, int], list[_Obs]] = {}
    for o in train:
        cells.setdefault(_cell_key(o.lat, o.lng, lat_ref, cell_m), []).append(o)
    cell_h = {c: (hz(v), len(v)) for c, v in cells.items() if len(v) >= min_n}
    out = np.zeros((len(test), nb))
    for i, o in enumerate(test):
        hit = cell_h.get(_cell_key(o.lat, o.lng, lat_ref, cell_m))
        out[i] = g if hit is None else (hit[1] * hit[0] + k * g) / (hit[1] + k)
    return out


def _c_index(risk: np.ndarray, obs: list[_Obs]) -> float:
    """Harrell's C: among comparable pairs (i ended by a trip before j's observed time), share where risk_i > risk_j."""
    t = np.array([o.duration_min for o in obs])
    e = np.array([o.event for o in obs])
    num = den = 0.0
    for i in np.flatnonzero(e):
        later = t > t[i]
        den += float(later.sum())
        num += float((risk[i] > risk[later]).sum()) + 0.5 * float((risk[i] == risk[later]).sum())
    return float("nan") if den == 0 else num / den


def _expected(h: np.ndarray, b: float) -> np.ndarray:
    S = np.concatenate([np.ones((len(h), 1)), np.cumprod(1.0 - h, axis=1)], axis=1)
    return np.sum(b * (S[:, :-1] + S[:, 1:]) / 2.0, axis=1)


def _calibration(p: np.ndarray, test: list[_Obs], t: float, groups: int = 3) -> list[dict[str, Any]]:
    order = np.argsort(p, kind="stable")
    rows = []
    for chunk in np.array_split(order, groups):
        sub = [test[i] for i in chunk]
        steps = km_curve([(o.duration_min, o.event) for o in sub])
        rows.append({"n": int(len(chunk)), "predicted_pct": round(100.0 * float(np.mean(p[chunk])), 1),
                     "observed_pct": round(100.0 * (1.0 - surv_at(steps, t)), 1)})
    return rows


def backtest_wait(spells: list[WaitSpell], cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    """Time-ordered hold-out: fit on the older (1 - holdout) share, score the newest share. Returns the evidence and the gate."""
    cfg = cfg or ML_CFG
    obs = _observations(spells)
    n_hold = int(len(obs) * float(cfg["holdout_fraction"]))
    if len(obs) < int(cfg["min_spells"]) or n_hold < int(cfg["min_holdout_spells"]):
        return {"status": "insufficient", "passes": False, "n_spells": len(obs),
                "reason": f"cần ≥ {int(cfg['min_spells'])} đợt chờ (hiện {len(obs)}) và ≥ {int(cfg['min_holdout_spells'])} đợt cho tập kiểm tra"}
    train, test = obs[: len(obs) - n_hold], obs[len(obs) - n_hold:]
    if sum(1 for o in train if o.event) < _MIN_EVENTS or sum(1 for o in test if o.event) < 3:
        return {"status": "insufficient", "passes": False, "n_spells": len(obs),
                "reason": "quá ít đợt chờ kết thúc bằng có cuốc (đợt offline/đổi chỗ chỉ cho biết 'chờ ít nhất bấy lâu')"}
    b, nb = _bins(cfg)
    full = WaitHazardModel(cfg).fit(train)
    plain = WaitHazardModel(cfg, use_context=False).fit(train)
    h_model, h_plain, h_base = full.hazards(test), plain.hazards(test), _baseline_hazards(train, test, b, nb)
    nll_m, nll_p, nll_b = _nll(h_model, test, b, nb), _nll(h_plain, test, b, nb), _nll(h_base, test, b, nb)
    gain, ctx_gain, min_gain = nll_b - nll_m, nll_p - nll_m, float(cfg["min_gain_nll"])
    beats, helps = bool(gain >= min_gain), bool(ctx_gain >= min_gain)
    t_cal = float(POSITION_CFG["wait_thresholds_min"][0])
    p_model = np.array([_summarise(h, b, [t_cal])["p_le"][str(int(t_cal))] for h in h_model])
    p_base = np.array([_summarise(h, b, [t_cal])["p_le"][str(int(t_cal))] for h in h_base])
    return {
        "status": "ok", "family": FAMILY, "n_spells": len(obs), "n_train": len(train), "n_test": len(test),
        "split_at": test[0].start.isoformat(timespec="minutes"),
        "nll_model": round(nll_m, 4), "nll_baseline": round(nll_b, 4), "nll_no_context": round(nll_p, 4),
        "nll_gain": round(gain, 4), "context_gain": round(ctx_gain, 4),
        "c_index_model": round(_c_index(-_expected(h_model, b), test), 4),
        "c_index_baseline": round(_c_index(-_expected(h_base, b), test), 4),
        "beats_baseline": beats, "context_helps": helps, "passes": beats and helps,
        "gate": (f"dùng ML khi log-likelihood trên tập kiểm tra tốt hơn baseline ≥ {min_gain:g} VÀ ngữ cảnh (giờ/mưa/vị trí) "
                 f"cải thiện thêm ≥ {min_gain:g} so với mô hình không ngữ cảnh"),
        "calibration_t_min": t_cal,
        "calibration_model": _calibration(p_model, test, t_cal),
        "calibration_baseline": _calibration(p_base, test, t_cal),
    }
