"""Glue between the ML models and the engine: gate, predict for the driver's current context, summarise.

Order of play (all on the driver's OWN data):
 1. wait model  — backtest on a time-ordered hold-out; if it beats the baseline it overwrites the per-zone wait numbers
                  (P(wait <= t), expected wait) for the current hour/rain; otherwise the baseline stays and we say why.
 2. cycle yield — conformal 80% band for the next wait+trip cycle per zone (only shown when not under-covering).
 3. bandit      — p_best / explore flags per zone from realised cycle yields.
Fits are cached by the content of the driver's log: the counterfactual scans call the engine dozens of times.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Any

from engine.src.config import ML_CFG, PERSONAL_CFG, POSITION_CFG, TIME_CFG
from engine.src.geo import haversine_m, valid_point
from engine.src.ml.bandit import posterior_table
from engine.src.ml.cycle_model import backtest_cycles, build_cycles, fit_cycle_model
from engine.src.ml.wait_model import backtest_wait, fit_wait_model
from engine.src.personal_model import PersonalModelResult
from engine.src.timeutil import parse_local
from engine.src.types import AreaSample, EngineInput

_CACHE: dict[Any, Any] = {}
_CACHE_MAX = 8


def _cached(key: Any, fn):
    if key in _CACHE:
        return _CACHE[key]
    if len(_CACHE) >= _CACHE_MAX:
        _CACHE.pop(next(iter(_CACHE)))
    _CACHE[key] = fn()
    return _CACHE[key]


def _rain_now(inp: EngineInput, now_local: datetime | None) -> float | None:
    """Rain (mm) of the forecast hour that contains `now`; None when the snapshot has no such hour (never assumed)."""
    if now_local is None:
        return None
    off = int(TIME_CFG["local_utc_offset_minutes"])
    hours = list(inp.weather_hourly)
    for a in inp.areas:
        hours += list(a.weather_hourly)
    for h in hours:
        t = parse_local(h.valid_time, off)
        if t is not None and t.date() == now_local.date() and t.hour == now_local.hour and h.precipitation_mm is not None:
            return float(h.precipitation_mm)
    return None


def _nearest_area(areas: list[AreaSample], lat: float, lng: float, max_m: float) -> str | None:
    best, best_d = None, max_m
    for a in areas:
        pt = valid_point(a.representative_point)
        if pt is None:
            continue
        d = haversine_m(lat, lng, pt[0], pt[1])
        if d <= best_d:
            best, best_d = a.area_id, d
    return best


def build_ml_insights(
    inp: EngineInput, pm: PersonalModelResult, now_local: datetime | None,
) -> tuple[PersonalModelResult, dict[str, Any] | None]:
    """Returns (personal model possibly with ML wait numbers, ml_insights dict or None when there is nothing to model)."""
    cfg = ML_CFG
    if not cfg["enabled"] or not (inp.wait_spells or inp.trip_log):
        return pm, None
    notes: list[str] = []
    info: dict[str, Any] = {"status": "ok", "notes": notes}
    spells, trips = inp.wait_spells, inp.trip_log
    skey = tuple((w.start, w.end, w.lat, w.lng, w.ended_by, w.rain_mm) for w in spells)
    areas = list(pm.areas)
    rain = _rain_now(inp, now_local)
    info["rain_mm_forecast_now"] = rain
    thresholds = [float(t) for t in POSITION_CFG["wait_thresholds_min"]]

    # ---- 1. wait model, gated by the backtest ----
    bt = _cached(("bt_wait", skey), lambda: backtest_wait(spells, cfg))
    wm: dict[str, Any] = {"backtest": bt, "used": False}
    if bt.get("passes") and now_local is not None and any(a.destination_distribution for a in areas):
        model = _cached(("fit_wait", skey), lambda: fit_wait_model(spells, cfg))
        if model is not None:
            new_areas = []
            n_over = 0
            for a in areas:
                dd, pt = a.destination_distribution, valid_point(a.representative_point)
                if not dd or pt is None:
                    new_areas.append(a)
                    continue
                pr = model.predict(now_local, pt[0], pt[1], rain, thresholds)
                new_dd = {
                    **dd,
                    "p_wait_le_pct": {k: round(100.0 * v, 1) for k, v in pr["p_le"].items()},
                    "expected_wait_min": round(pr["expected_wait_min"], 1),
                    "median_wait_min": pr["median_wait_min"],
                    "model": f"hazard_ml:{model.family}",
                }
                new_areas.append(replace(a, destination_distribution=new_dd))
                n_over += 1
            areas = new_areas
            wm.update({"used": True, "family": model.family, "zones_updated": n_over})
            if rain is None:
                notes.append("Không có dự báo mưa cho giờ hiện tại nên mô hình chờ coi như không mưa.")
    elif bt.get("status") == "ok" and not bt.get("passes"):
        why = ("chưa thắng baseline thống kê" if not bt.get("beats_baseline")
               else "chỉ thắng nhờ làm mượt, chưa có bằng chứng ngữ cảnh giờ/mưa/vị trí giúp thêm")
        notes.append(f"Mô hình ML thời gian chờ {why} trên tập kiểm tra theo thời gian, nên vẫn dùng baseline.")
    elif bt.get("status") != "ok":
        notes.append(f"Chưa dùng ML cho thời gian chờ: {bt.get('reason', 'không đủ dữ liệu')}.")
    info["wait_model"] = wm

    # ---- 2 + 3. cycle yield band and bandit (need the tariff's fuel cost) ----
    econ = pm.economics
    if econ is not None and trips:
        ckey = (skey, tuple((t.started_at, t.pickup_lat, t.pickup_lng, t.net_vnd, t.duration_min, t.distance_km) for t in trips),
                round(econ.fuel_cost_vnd_per_km, 3))
        cycles = _cached(("cycles", ckey), lambda: build_cycles(trips, spells, econ.fuel_cost_vnd_per_km))
        bc = _cached(("bt_cycle", ckey), lambda: backtest_cycles(cycles, cfg))
        cy: dict[str, Any] = {"backtest": bc, "zones": []}
        if bc.get("status") == "ok" and bc.get("calibrated") is not False and now_local is not None:
            cm = _cached(("fit_cycle", ckey), lambda: fit_cycle_model(cycles, cfg))
            if cm is not None:
                for a in areas:
                    pt = valid_point(a.representative_point)
                    if a.trip_value and pt is not None:
                        cy["zones"].append({"area_id": a.area_id, **cm.predict(now_local, pt[0], pt[1], rain)})
        elif bc.get("status") == "ok":
            notes.append("Khoảng conformal của năng suất chu kỳ phủ thấp hơn mức danh nghĩa trên tập kiểm tra nên không hiển thị.")
        info["cycle_yield"] = cy

        rewards: dict[str, list[float]] = {}
        cell = float(PERSONAL_CFG["zone_cell_m"])
        for c in cycles:
            aid = _nearest_area(areas, c.lat, c.lng, cell)
            if aid is not None:
                rewards.setdefault(aid, []).append(c.yield_vnd_per_hour)
        if len(rewards) >= 2:
            tab = posterior_table(rewards, float(cfg["bandit_prior_k"]), int(cfg["bandit_draws"]), int(cfg["random_state"]),
                                  float(cfg["explore_p_best"]), int(cfg["explore_max_n"]))
            info["bandit"] = {"zones": tab, "explore": sorted(k for k, v in tab.items() if v["explore"]),
                              "note": "p_best = xác suất vùng có năng suất trung bình cao nhất theo lịch sử của chính bạn; "
                                      "'explore' = ít dữ liệu nhưng còn cơ hội đáng kể — nên thử vài lần"}
    return replace(pm, areas=areas), info
