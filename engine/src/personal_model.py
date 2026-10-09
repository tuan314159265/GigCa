"""Personal model — learns zone economics from the DRIVER'S OWN data (v4).

Why: market-wide fare/booking figures are not verifiable from the driver's side (no API, "net" depends on commission,
bonus, surge and vehicle type, scales like demand_index belong to the platform). What the driver CAN verify is what they
see every day: the per-km tariff, their own trips and how long they stood waiting. So the model is built only from:

- the driver's trip log (pickup, net income before fuel, duration, optional distance);
- the driver's profile (tariff a + b·km, vehicle fuel use, fuel price, income goal) — typed in by the driver;
- the driver's wait spells (stretches of standing still, with how each one ended).

Money model (per pickup zone z):

    net fare per trip   = a + b·d̄_z                  (before fuel; a, b fitted from the log or typed in)
    income per trip     = a + (b − c)·d̄_z − c·r_z      (c = fuel VND/km, r_z = repositioning km, scorer-side)
    time per trip (h)   = d̄_z / v_z + r_z / v_rep + w_z / 60

Honesty rules (same spirit as the rest of the engine):
- nothing is invented: a zone needs `min_trips_per_zone` real trips (with a distance) / `min_spells_per_zone` spells,
  the whole log needs `min_trips_total` / `min_spells_total`; otherwise the model says "insufficient" and why;
- small samples are shrunk toward the driver's own average (k pseudo-observations) so a lucky 4-trip zone cannot win;
- waiting is a SURVIVAL quantity: a spell that ended because the driver went offline or moved is censored (the real
  wait was at least that long). A lunch break therefore no longer looks like a long wait;
- a trip distance that is only estimated from two coordinates (straight line x detour) is counted and reported;
- it describes THIS driver's past, not the market and not a probability of getting a ride;
- pure and deterministic: "now" comes from input.generated_at.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from engine.src.config import GEO_CFG, PERSONAL_CFG, POSITION_CFG, TIME_CFG
from engine.src.geo import haversine_m
from engine.src.timeutil import parse_local
from engine.src.types import AreaSample, DriverEconomics, DriverProfile, TripRecord, WaitSpell

SOURCE = "driver_trip_log"
_M_PER_DEG_LAT = 111_320.0


@dataclass(frozen=True)
class PersonalModelResult:
    areas: list[AreaSample] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    economics: DriverEconomics | None = None
    speed_kmh: float | None = None  # global trip speed learned from the log (None without a usable log)

    @property
    def usable(self) -> bool:
        return self.summary.get("status") in ("ok",)

    @property
    def has_trip_zones(self) -> bool:
        return any(a.trip_value for a in self.areas)

    @property
    def has_wait_zones(self) -> bool:
        return any(a.destination_distribution for a in self.areas)


# --------------------------------------------------------------------------- small statistics helpers
def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs)


def _sd(xs: list[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def _shrink(zone_value: float, n: int, prior: float, k: float) -> float:
    return (n * zone_value + k * prior) / (n + k)


def _tod_gap_min(a: datetime, b: datetime) -> float:
    """Circular distance between two times of day, in minutes."""
    d = abs((a.hour * 60 + a.minute) - (b.hour * 60 + b.minute))
    return min(d, 1440 - d)


def _cell_key(lat: float, lng: float, lat_ref: float, cell_m: float) -> tuple[int, int]:
    dlat = cell_m / _M_PER_DEG_LAT
    dlng = cell_m / (_M_PER_DEG_LAT * max(math.cos(math.radians(lat_ref)), 1e-6))
    return math.floor(lat / dlat), math.floor(lng / dlng)


def fit_tariff(points: list[tuple[float, float]]) -> dict[str, Any] | None:
    """Least squares net = a + b·km on (km, net_vnd) points. Needs a positive slope.

    If the free intercept comes out negative (impossible for a fare) the model is refitted through the origin (a = 0)
    and says so. Returns None when the data cannot support a fit."""
    n = len(points)
    if n < 3:
        return None
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    mx, my = _mean(xs), _mean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx <= 0:
        return None
    b = sum((x - mx) * (y - my) for x, y in points) / sxx
    a = my - b * mx
    method = "ols"
    if a < 0:
        sx2 = sum(x * x for x in xs)
        b, a, method = sum(x * y for x, y in points) / sx2, 0.0, "origin"
    if b <= 0:
        return None
    resid = [y - (a + b * x) for x, y in points]
    ss_res = sum(r * r for r in resid)
    ss_tot = sum((y - my) ** 2 for y in ys)
    return {
        "a": a, "b": b, "n": n, "method": method,
        "r2": None if ss_tot <= 0 else max(0.0, 1.0 - ss_res / ss_tot),
        "rmse_vnd": math.sqrt(ss_res / n),
    }


# --------------------------------------------------------------------------- survival (Kaplan–Meier)
def km_curve(obs: list[tuple[float, bool]]) -> list[tuple[float, float]]:
    """Kaplan–Meier survival steps [(t, S(t))] from (duration_min, ended_with_a_trip). Censored spells only
    shrink the risk set. At tied times events are counted before censorings (standard convention)."""
    ordered = sorted(obs, key=lambda o: (o[0], not o[1]))
    at_risk, s = len(ordered), 1.0
    steps: list[tuple[float, float]] = []
    i = 0
    while i < len(ordered):
        t = ordered[i][0]
        events = censored = 0
        j = i
        while j < len(ordered) and ordered[j][0] == t:
            if ordered[j][1]:
                events += 1
            else:
                censored += 1
            j += 1
        if events:
            s *= 1.0 - events / at_risk
            steps.append((t, s))
        at_risk -= events + censored
        i = j
    return steps


def surv_at(steps: list[tuple[float, float]], t: float) -> float:
    s = 1.0
    for u, v in steps:
        if u <= t:
            s = v
        else:
            break
    return s


def restricted_mean(steps: list[tuple[float, float]], horizon: float) -> float:
    """Expected wait inside [0, horizon] = ∫ S(t) dt. After the last observed step S is held constant."""
    area, prev, s = 0.0, 0.0, 1.0
    for u, v in steps:
        if u >= horizon:
            break
        area += s * (u - prev)
        prev, s = u, v
    return area + s * (horizon - prev)


def median_wait(steps: list[tuple[float, float]]) -> float | None:
    for u, v in steps:
        if v <= 0.5:
            return u
    return None  # the curve never fell to 50%: the typical wait is longer than anything observed


def _wait_stats(obs: list[tuple[float, bool]], thresholds: list[float], horizon: float) -> dict[str, Any]:
    steps = km_curve(obs)
    return {
        "p_le": {str(int(t) if float(t).is_integer() else t): 1.0 - surv_at(steps, t) for t in thresholds},
        "expected_wait_min": restricted_mean(steps, horizon),
        "median_wait_min": median_wait(steps),
        "events": sum(1 for _, e in obs if e),
    }


# --------------------------------------------------------------------------- the model
def _insufficient(reason: str, economics: DriverEconomics | None = None, **extra: Any) -> PersonalModelResult:
    return PersonalModelResult([], {"status": "insufficient", "reason": reason, "source": SOURCE, **extra}, economics)


def _trip_km(t: TripRecord, detour: float) -> tuple[float | None, bool]:
    """(km, estimated?) — the driver's own distance wins; otherwise straight line x detour between the coordinates."""
    if t.distance_km is not None:
        return t.distance_km, False
    if t.dropoff_lat is not None and t.dropoff_lng is not None:
        return haversine_m(t.pickup_lat, t.pickup_lng, t.dropoff_lat, t.dropoff_lng) / 1000.0 * detour, True
    return None, False


def resolve_economics(
    km_net: list[tuple[float, float]],
    profile: DriverProfile | None,
    cfg: dict[str, Any],
    notes: list[str],
) -> tuple[DriverEconomics | None, dict[str, Any] | None]:
    """Pick the tariff (fitted from the log when it can support one, else the driver's own typed tariff) and the fuel
    cost (driver inputs, else the config fallback — labelled). Returns (economics or None, fit details or None)."""
    fit = None
    if len(km_net) >= int(cfg["min_trips_total"]) and _sd([p[0] for p in km_net]) >= float(cfg["fit_min_distance_sd_km"]):
        fit = fit_tariff(km_net)
        if fit is None:
            notes.append("Không fit được biểu cước a + b·km từ nhật ký (độ dốc không dương hoặc dữ liệu quá ít biến thiên).")
    elif km_net:
        notes.append(
            f"Chưa fit biểu cước từ nhật ký: cần ≥ {int(cfg['min_trips_total'])} chuyến có cự ly và độ lệch chuẩn cự ly "
            f"≥ {float(cfg['fit_min_distance_sd_km']):g}km (hiện {len(km_net)} chuyến)."
        )
    typed = profile is not None and profile.fare_base_vnd is not None and profile.fare_per_km_vnd is not None
    if fit is not None:
        a, b, source = fit["a"], fit["b"], "fitted_from_log"
        if typed and profile.fare_per_km_vnd and abs(b - profile.fare_per_km_vnd) / profile.fare_per_km_vnd > 0.2:
            notes.append(
                f"Đơn giá/km fit từ nhật ký (~{b:,.0f}đ) lệch hơn 20% so với biểu cước bạn nhập ({profile.fare_per_km_vnd:,.0f}đ) — "
                "engine dùng số fit từ nhật ký; hãy kiểm tra lại biểu cước đã nhập hoặc cách ghi cước."
            )
    elif typed:
        a, b, source = float(profile.fare_base_vnd), float(profile.fare_per_km_vnd), "driver_input"
    else:
        return None, None
    c = profile.fuel_cost_vnd_per_km if profile is not None else None
    fuel_source = "driver_input"
    if c is None:
        c, fuel_source = float(GEO_CFG["reposition_cost_vnd_per_km"]), "config_default"
        notes.append(
            f"Chưa có mức tiêu hao xăng (lít/100km) và giá xăng của bạn nên dùng {c:g}đ/km theo cấu hình (giả định đề xuất tạm)."
        )
    target = profile.target_vnd_per_hour if profile is not None else None
    return DriverEconomics(a, b, float(c), source, fuel_source, target), fit


def build_personal_model(
    trips: list[TripRecord],
    now_local: datetime | None,
    cfg: dict[str, Any] | None = None,
    profile: DriverProfile | None = None,
    spells: list[WaitSpell] | None = None,
) -> PersonalModelResult:
    cfg = cfg or PERSONAL_CFG
    spells = spells or []
    if not trips and not spells:
        # Tier 0: nothing logged. The driver's typed tariff may still support a what-if table (see whatif.py).
        econ, _ = resolve_economics([], profile, cfg, [])
        return PersonalModelResult([], {"status": "no_log", "source": SOURCE}, econ)

    offset = int(TIME_CFG["local_utc_offset_minutes"])
    notes: list[str] = []
    max_age = timedelta(days=float(cfg["max_age_days"]))
    window_min = float(cfg["daypart_window_h"]) * 60.0

    # ---- trips: parse, age/future filter, daypart filter ----
    dropped = {"khong_doc_duoc_gio": 0, "tuong_lai": 0, "qua_cu": 0}
    parsed: list[tuple[datetime, TripRecord]] = []
    for t in trips:
        start = parse_local(t.started_at, offset)
        if start is None:
            dropped["khong_doc_duoc_gio"] += 1
            continue
        if now_local is not None:
            if start > now_local:
                dropped["tuong_lai"] += 1
                continue
            if now_local - start > max_age:
                dropped["qua_cu"] += 1
                continue
        parsed.append((start, t))
    parsed.sort(key=lambda p: (p[0], p[1].trip_id))
    if any(dropped.values()):
        notes.append(
            "Loại khỏi mô hình: "
            + ", ".join(f"{v} chuyến {k.replace('_', ' ')}" for k, v in dropped.items() if v)
            + f" (nhật ký chỉ dùng chuyến trong {cfg['max_age_days']:g} ngày gần nhất, không ở tương lai)."
        )
    if now_local is None:
        notes.append("Không đọc được generated_at nên không lọc theo khung giờ trong ngày.")
        in_part = list(parsed)
    else:
        in_part = [(s, t) for s, t in parsed if _tod_gap_min(s, now_local) <= window_min]

    # ---- wait spells: same filters; a spell with end < start or unreadable time is rejected and counted ----
    sp_drop = {"khong_doc_duoc_gio": 0, "tuong_lai": 0, "qua_cu": 0}
    sp_parsed: list[tuple[datetime, float, WaitSpell]] = []
    for w in spells:
        a, b = parse_local(w.start, offset), parse_local(w.end, offset)
        if a is None or b is None or b < a:
            sp_drop["khong_doc_duoc_gio"] += 1
            continue
        if now_local is not None:
            if a > now_local:
                sp_drop["tuong_lai"] += 1
                continue
            if now_local - a > max_age:
                sp_drop["qua_cu"] += 1
                continue
        sp_parsed.append((a, (b - a).total_seconds() / 60.0, w))
    if any(sp_drop.values()):
        notes.append(
            "Loại khỏi mô hình: "
            + ", ".join(f"{v} đợt chờ {k.replace('_', ' ')}" for k, v in sp_drop.items() if v) + "."
        )
    sp_in_part = [(a, d, w) for a, d, w in sp_parsed if now_local is None or _tod_gap_min(a, now_local) <= window_min]

    summary_base: dict[str, Any] = {
        "source": SOURCE,
        "trips_in_log": len(trips),
        "trips_valid_age": len(parsed),
        "trips_in_daypart": len(in_part),
        "wait_spells_in_log": len(spells),
        "wait_spells_in_daypart": len(sp_in_part),
        "daypart_window_h": float(cfg["daypart_window_h"]),
        "notes": notes,
    }

    k = float(cfg["shrinkage_k"])
    z = float(cfg["interval_z"])
    min_zone = int(cfg["min_trips_per_zone"])
    min_total = int(cfg["min_trips_total"])
    cell_m = float(cfg["zone_cell_m"])
    detour = float(GEO_CFG["detour_factor"])
    horizon = float(cfg["wait_horizon_min"])
    thresholds = [float(t) for t in POSITION_CFG["wait_thresholds_min"]]

    # ---- trip side: distances, tariff, speed ----
    trip_ok = len(in_part) >= min_total
    km_est = 0
    rows: list[tuple[datetime, TripRecord, float]] = []  # (start, trip, km) for trips with a usable distance
    reported_rows: list[tuple[datetime, TripRecord, float]] = []  # the subset whose distance the driver actually reported
    for s, t in in_part:
        km, est = _trip_km(t, detour)
        if km is None or km <= 0:
            continue
        km_est += 1 if est else 0
        rows.append((s, t, km))
        if not est:
            reported_rows.append((s, t, km))
    if not trip_ok:
        notes.append(
            f"Chỉ có {len(in_part)} chuyến trong khung ±{cfg['daypart_window_h']:g}h quanh giờ hiện tại "
            f"(cần ≥ {min_total}) — chưa đủ để học thói quen của bạn."
        )
    elif len(rows) < len(in_part):
        notes.append(
            f"{len(in_part) - len(rows)}/{len(in_part)} chuyến không có cự ly (không có distance_km và không có điểm trả) "
            "nên không dùng để học cự ly/tốc độ/biểu cước."
        )
    if km_est:
        notes.append(
            f"{km_est}/{len(rows)} chuyến dùng cự ly ƯỚC TÍNH từ tọa độ đón–trả (đường chim bay x{detour:g}), không phải cự ly thật."
        )

    # The tariff is fitted on REPORTED distances when there are enough of them: a distance estimated from two coordinates
    # carries error in the regressor and would drag the slope down.
    fit_rows = reported_rows if len(reported_rows) >= min_total else rows
    econ, fit = resolve_economics([(km, t.net_vnd) for _, t, km in fit_rows] if trip_ok else [], profile, cfg, notes)

    # ---- wait side: global Kaplan–Meier ----
    min_sp_total = int(cfg["min_spells_total"])
    min_sp_zone = int(cfg["min_spells_per_zone"])
    min_events = int(cfg["min_wait_events_per_zone"])
    wait_ok = len(sp_in_part) >= min_sp_total
    g_obs = [(d, w.ended_by == "trip") for _, d, w in sp_in_part]
    g_wait = _wait_stats(g_obs, thresholds, horizon) if wait_ok and any(e for _, e in g_obs) else None
    if sp_in_part and not wait_ok:
        notes.append(f"Chỉ có {len(sp_in_part)} đợt chờ trong khung giờ (cần ≥ {min_sp_total}) — chưa tính thời gian chờ.")
    elif wait_ok and g_wait is None:
        notes.append("Không đợt chờ nào kết thúc bằng có cuốc — chỉ biết 'chờ ít nhất bấy lâu', chưa ước tính được thời gian chờ.")

    lens_trip = trip_ok and econ is not None and len(rows) >= min_zone
    if not lens_trip and trip_ok and econ is None:
        notes.append("Chưa có biểu cước a + b·km (nhật ký chưa đủ để fit và bạn chưa nhập biểu cước) nên chưa xếp hạng vùng theo thu nhập.")
    if not lens_trip and g_wait is None:
        extra = {kk: v for kk, v in summary_base.items() if kk != "source"}
        return _insufficient(
            "Chưa đủ dữ liệu của chính bạn để học thu nhập theo vùng hoặc thời gian chờ (xem ghi chú).",
            econ, **extra,
        )

    # ---- global trip aggregates ----
    p_km = p_net = p_dur = p_speed = None
    if rows:
        p_km = _mean([km for _, _, km in rows])
        p_net = _mean([t.net_vnd for _, t, _ in rows])
        p_dur = _mean([t.duration_min for _, t, _ in rows])
        p_speed = sum(km for _, _, km in rows) / (sum(t.duration_min for _, t, _ in rows) / 60.0)

    # ---- zones ----
    pts = [(t.pickup_lat, t.pickup_lng) for _, t in in_part] + [(w.lat, w.lng) for _, _, w in sp_in_part]
    lat_ref = _mean([p[0] for p in pts])
    cells_trip: dict[tuple[int, int], list[tuple[TripRecord, float]]] = {}
    if lens_trip:
        for _, t, km in rows:
            cells_trip.setdefault(_cell_key(t.pickup_lat, t.pickup_lng, lat_ref, cell_m), []).append((t, km))
    cells_wait: dict[tuple[int, int], list[tuple[float, bool]]] = {}
    if g_wait is not None:
        for _, d, w in sp_in_part:
            cells_wait.setdefault(_cell_key(w.lat, w.lng, lat_ref, cell_m), []).append((d, w.ended_by == "trip"))
    cell_pts: dict[tuple[int, int], list[tuple[float, float]]] = {}
    for la, lo in pts:
        cell_pts.setdefault(_cell_key(la, lo, lat_ref, cell_m), []).append((la, lo))

    areas: list[AreaSample] = []
    skipped_thin = 0
    for cell in sorted(set(cells_trip) | set(cells_wait)):
        ts, ws = cells_trip.get(cell, []), cells_wait.get(cell, [])
        trip_value = None
        if len(ts) >= min_zone and econ is not None:
            n = len(ts)
            kms = [km for _, km in ts]
            v_zone = sum(kms) / (sum(t.duration_min for t, _ in ts) / 60.0)
            trip_value = {
                "avg_trip_distance_km": round(_shrink(_mean(kms), n, p_km, k), 3),
                "avg_speed_kmh": round(_shrink(v_zone, n, p_speed, k), 2),
                "km_se": round(_sd(kms) / math.sqrt(n), 4),
                "interval_z": z,
                "evidence_n": n,
                "data_source": SOURCE,
            }
            if g_wait is not None:
                # A zone with too few wait spells of its own is priced with the driver's OVERALL expected wait (labelled by the
                # scorer) instead of dropping the wait term for every area, which would make yields incomparable.
                trip_value["fallback_wait_min"] = round(g_wait["expected_wait_min"], 1)
        dest = None
        if g_wait is not None and len(ws) >= min_sp_zone and sum(1 for _, e in ws if e) >= min_events:
            m = len(ws)
            zs = _wait_stats(ws, thresholds, horizon)
            dest = {
                "p_wait_le_pct": {kk: round(100.0 * _shrink(v, m, g_wait["p_le"][kk], k), 1) for kk, v in zs["p_le"].items()},
                "expected_wait_min": round(_shrink(zs["expected_wait_min"], m, g_wait["expected_wait_min"], k), 1),
                "median_wait_min": zs["median_wait_min"],  # raw zone median (None = never reached 50% in the observed range)
                "wait_se_min": round(_sd([d for d, _ in ws]) / math.sqrt(m), 3),  # crude: ignores censoring
                "evidence_n": m,
                "events_n": zs["events"],
                "data_source": SOURCE,
            }
        if trip_value is None and dest is None:
            skipped_thin += 1
            continue
        zp = cell_pts[cell]
        rep = {"latitude": round(_mean([p[0] for p in zp]), 6), "longitude": round(_mean([p[1] for p in zp]), 6)}
        areas.append(AreaSample(
            area_id=f"zone_{cell[0]}_{cell[1]}",
            spatial_scope="driver_log_zone",
            representative_point=rep,
            area_name=f"Vùng ~{cell_m:g}m quanh ({rep['latitude']:.4f}, {rep['longitude']:.4f}) [nhật ký của bạn]",
            trip_value=trip_value,
            destination_distribution=dest,
        ))

    if not areas:
        extra = {kk: v for kk, v in summary_base.items() if kk != "source"}
        return _insufficient(
            f"Không vùng nào có ≥ {min_zone} chuyến (hoặc ≥ {min_sp_zone} đợt chờ) trong khung giờ này — nhật ký còn quá phân tán.",
            econ, **extra,
        )

    g_expected_wait = None if g_wait is None else g_wait["expected_wait_min"]
    baseline = None
    if econ is not None and p_km is not None and p_speed is not None and g_expected_wait is not None:
        net_after_fuel = econ.fare_base_vnd + (econ.fare_per_km_vnd - econ.fuel_cost_vnd_per_km) * p_km
        baseline = round(net_after_fuel / (p_km / p_speed + g_expected_wait / 60.0))
    summary = {
        **summary_base,
        "status": "ok",
        "zones_built": len(areas),
        "zones_with_trip_stats": sum(1 for a in areas if a.trip_value),
        "zones_with_wait_stats": sum(1 for a in areas if a.destination_distribution),
        "zones_skipped_thin": skipped_thin,
        "tariff": None if econ is None else {
            "source": econ.tariff_source,
            "fare_base_vnd": round(econ.fare_base_vnd),
            "fare_per_km_vnd": round(econ.fare_per_km_vnd),
            "fit": None if fit is None else {
                "method": fit["method"], "n": fit["n"],
                "r2": None if fit["r2"] is None else round(fit["r2"], 3), "rmse_vnd": round(fit["rmse_vnd"]),
            },
        },
        "fuel_cost_vnd_per_km": None if econ is None else round(econ.fuel_cost_vnd_per_km),
        "fuel_source": None if econ is None else econ.fuel_source,
        "trip_km_estimated_from_coordinates": km_est,
        "wait_spells_censored": sum(1 for _, e in g_obs if not e),
        "personal_mean_net_vnd": None if p_net is None else round(p_net),
        "personal_mean_trip_km": None if p_km is None else round(p_km, 2),
        "personal_mean_duration_min": None if p_dur is None else round(p_dur, 1),
        "personal_speed_kmh": None if p_speed is None else round(p_speed, 1),
        "personal_expected_wait_min": None if g_expected_wait is None else round(g_expected_wait, 1),
        "baseline_yield_vnd_per_hour": baseline,
        "shrinkage_k": k,
        "interval_note": (
            f"Khoảng ~80% (P10–P90, ±{z:g}·sai số chuẩn) chỉ phản ánh dao động của cự ly cuốc và thời gian chờ trung bình của vùng "
            "(xấp xỉ, bỏ qua kiểm duyệt); không gồm sai số biểu cước hay tốc độ."
        ),
        "limits": [
            "Mô tả thói quen và kết quả QUÁ KHỨ của chính tài xế, không phải thị trường và không phải xác suất có cuốc.",
            "Vùng ít chuyến/ít đợt chờ bị kéo về mức trung bình cá nhân (shrinkage) để tránh thắng nhờ may mắn.",
            "Thời gian chờ chỉ đáng tin khi các đợt chờ được ghi bằng GPS/nút bấm; đợt kết thúc vì offline hoặc đổi chỗ được coi là bị kiểm duyệt.",
            "Đợt 'đổi chỗ' thường xảy ra khi chờ lâu, nên kiểm duyệt không hoàn toàn ngẫu nhiên: thời gian chờ dài có thể bị đánh giá thấp.",
        ],
    }
    return PersonalModelResult(areas, summary, econ, p_speed)
