"""Personal model — learns zone economics from the DRIVER'S OWN trip log (v3).

Why: market-wide fare/booking data is not available, so the two earning lenses used to be blocked on real data.
A driver's own log of completed trips is user-contributed data the product can legitimately collect. From it we derive,
per pickup zone (a fixed grid cell), exactly the fields the existing scorers already consume
(net_value_vnd, avg_duration_min, avg_next_wait_min, favorable_dropoff_pct) — plus the evidence behind them.

Honesty rules (same spirit as the rest of the engine):
- nothing is invented: a zone needs `min_trips_per_zone` real trips, the whole log needs `min_trips_total`;
  otherwise the model says "insufficient" and says why;
- small samples are shrunk toward the driver's own average (k pseudo-trips) so a lucky 4-trip zone cannot win;
- every estimate carries n and a ~80% interval (interval_z * standard error of the zone's mean net fare);
- it describes THIS driver's past, not the market and not a probability of getting a ride;
- pure and deterministic: "now" comes from input.generated_at.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from engine.src.config import PERSONAL_CFG, TIME_CFG
from engine.src.geo import haversine_m
from engine.src.timeutil import parse_local
from engine.src.types import AreaSample, TripRecord

SOURCE = "driver_trip_log"
_M_PER_DEG_LAT = 111_320.0


@dataclass(frozen=True)
class PersonalModelResult:
    areas: list[AreaSample] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)

    @property
    def usable(self) -> bool:
        return self.summary.get("status") in ("ok",)


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs)


def _sd(xs: list[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def _shrink(zone_mean: float, n: int, prior: float, k: float) -> float:
    return (n * zone_mean + k * prior) / (n + k)


def _tod_gap_min(a: datetime, b: datetime) -> float:
    """Circular distance between two times of day, in minutes."""
    d = abs((a.hour * 60 + a.minute) - (b.hour * 60 + b.minute))
    return min(d, 1440 - d)


def _cell_key(lat: float, lng: float, lat_ref: float, cell_m: float) -> tuple[int, int]:
    dlat = cell_m / _M_PER_DEG_LAT
    dlng = cell_m / (_M_PER_DEG_LAT * max(math.cos(math.radians(lat_ref)), 1e-6))
    return math.floor(lat / dlat), math.floor(lng / dlng)


def _insufficient(reason: str, **extra: Any) -> PersonalModelResult:
    return PersonalModelResult([], {"status": "insufficient", "reason": reason, "source": SOURCE, **extra})


def build_personal_model(
    trips: list[TripRecord],
    now_local: datetime | None,
    cfg: dict[str, Any] | None = None,
) -> PersonalModelResult:
    cfg = cfg or PERSONAL_CFG
    if not trips:
        return PersonalModelResult([], {"status": "no_log", "source": SOURCE})

    offset = int(TIME_CFG["local_utc_offset_minutes"])
    notes: list[str] = []
    parsed: list[tuple[datetime, TripRecord]] = []
    dropped = {"khong_doc_duoc_gio": 0, "tuong_lai": 0, "qua_cu": 0}
    max_age = timedelta(days=float(cfg["max_age_days"]))
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

    # Time-of-day filter around "now": a 10:00 trip says little about 22:00.
    window_min = float(cfg["daypart_window_h"]) * 60.0
    if now_local is None:
        notes.append("Không đọc được generated_at nên không lọc theo khung giờ trong ngày.")
        in_part = list(parsed)
    else:
        in_part = [(s, t) for s, t in parsed if _tod_gap_min(s, now_local) <= window_min]

    summary_base: dict[str, Any] = {
        "source": SOURCE,
        "trips_in_log": len(trips),
        "trips_valid_age": len(parsed),
        "trips_in_daypart": len(in_part),
        "daypart_window_h": float(cfg["daypart_window_h"]),
        "notes": notes,
    }
    if len(in_part) < int(cfg["min_trips_total"]):
        return _insufficient(
            f"Chỉ có {len(in_part)} chuyến trong khung ±{cfg['daypart_window_h']:g}h quanh giờ hiện tại "
            f"(cần ≥ {int(cfg['min_trips_total'])}) — chưa đủ để học thói quen của bạn.",
            **{k: v for k, v in summary_base.items() if k != "source"},
        )

    k = float(cfg["shrinkage_k"])
    z = float(cfg["interval_z"])
    min_zone = int(cfg["min_trips_per_zone"])
    lat_ref = _mean([t.pickup_lat for _, t in in_part])
    cell_m = float(cfg["zone_cell_m"])

    nets_all = [t.net_vnd for _, t in in_part]
    durs_all = [t.duration_min for _, t in in_part]
    p_net, p_dur = _mean(nets_all), _mean(durs_all)

    # --- follow-up pairs: consecutive trips of one session where the dropoff of the first is known ---
    pairs: list[dict[str, Any]] = []
    ordered = sorted(parsed, key=lambda p: (p[0], p[1].trip_id))
    gap_cap = float(cfg["session_gap_max_min"])
    for (s_a, a), (s_b, b) in zip(ordered, ordered[1:]):
        if a.dropoff_lat is None or a.dropoff_lng is None:
            continue
        end_a = s_a + timedelta(minutes=a.duration_min)
        if now_local is not None and _tod_gap_min(end_a, now_local) > window_min:
            continue
        gap = (s_b - end_a).total_seconds() / 60.0
        if gap < 0 or gap > gap_cap:
            continue  # overlap/duplicate, or a break between shifts — not "waiting"
        dist_km = haversine_m(a.dropoff_lat, a.dropoff_lng, b.pickup_lat, b.pickup_lng) / 1000.0
        pairs.append({
            "cell": _cell_key(a.dropoff_lat, a.dropoff_lng, lat_ref, cell_m),
            "gap": gap,
            "fav": gap <= float(cfg["follow_up_max_min"]) and dist_km <= float(cfg["follow_up_max_km"]),
            "pt": (a.dropoff_lat, a.dropoff_lng),
        })
    p_wait = _mean([p["gap"] for p in pairs]) if pairs else None
    p_fav = 100.0 * _mean([1.0 if p["fav"] else 0.0 for p in pairs]) if pairs else None

    # --- group by zone ---
    pick: dict[tuple[int, int], list[TripRecord]] = {}
    for _, t in in_part:
        pick.setdefault(_cell_key(t.pickup_lat, t.pickup_lng, lat_ref, cell_m), []).append(t)
    drop: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for p in pairs:
        drop.setdefault(p["cell"], []).append(p)

    areas: list[AreaSample] = []
    skipped_thin = 0
    for cell in sorted(set(pick) | set(drop)):
        ts, ps = pick.get(cell, []), drop.get(cell, [])
        has_trip = len(ts) >= min_zone
        has_pair = len(ps) >= min_zone
        if not has_trip and not has_pair:
            skipped_thin += 1
            continue
        pts = [(t.pickup_lat, t.pickup_lng) for t in ts] or [p["pt"] for p in ps]
        rep = {"latitude": round(_mean([p[0] for p in pts]), 6), "longitude": round(_mean([p[1] for p in pts]), 6)}
        area_id = f"zone_{cell[0]}_{cell[1]}"
        trip_value = None
        if has_trip:
            n = len(ts)
            nets = [t.net_vnd for t in ts]
            durs = [t.duration_min for t in ts]
            trip_value = {
                "net_value_vnd": round(_shrink(_mean(nets), n, p_net, k)),
                "avg_duration_min": round(_shrink(_mean(durs), n, p_dur, k), 1),
                "net_se_vnd": round(_sd(nets) / math.sqrt(n)),
                "interval_z": z,
                "evidence_n": n,
                "data_source": SOURCE,
            }
        dest = None
        if has_pair and p_wait is not None and p_fav is not None:
            m = len(ps)
            dest = {
                "favorable_dropoff_pct": round(_shrink(100.0 * _mean([1.0 if p["fav"] else 0.0 for p in ps]), m, p_fav, k), 1),
                "avg_next_wait_min": round(_shrink(_mean([p["gap"] for p in ps]), m, p_wait, k), 1),
                "evidence_n": m,
                "data_source": SOURCE,
            }
        if trip_value is None and dest is None:
            skipped_thin += 1
            continue
        areas.append(AreaSample(
            area_id=area_id,
            spatial_scope="driver_log_zone",
            representative_point=rep,
            area_name=f"Vùng đón ~{cell_m:g}m quanh ({rep['latitude']:.4f}, {rep['longitude']:.4f}) [nhật ký của bạn]",
            trip_value=trip_value,
            destination_distribution=dest,
        ))

    if not areas:
        return _insufficient(
            f"Không vùng nào có ≥ {min_zone} chuyến/cặp chuyến trong khung giờ này — nhật ký còn quá phân tán.",
            **{kk: v for kk, v in summary_base.items() if kk != "source"},
        )

    baseline = None
    if p_wait is not None:
        baseline = round(p_net / ((p_dur + p_wait) / 60.0))
    summary = {
        **summary_base,
        "status": "ok",
        "zones_built": len(areas),
        "zones_skipped_thin": skipped_thin,
        "follow_up_pairs": len(pairs),
        "personal_mean_net_vnd": round(p_net),
        "personal_mean_duration_min": round(p_dur, 1),
        "personal_mean_wait_min": None if p_wait is None else round(p_wait, 1),
        "baseline_yield_vnd_per_hour": baseline,
        "shrinkage_k": k,
        "interval_note": f"Khoảng ~80% (±{z:g}·sai số chuẩn) chỉ phản ánh dao động cước giữa các chuyến trong vùng.",
        "limits": [
            "Mô tả thói quen và kết quả QUÁ KHỨ của chính tài xế, không phải thị trường và không phải xác suất có cuốc.",
            "Vùng ít chuyến bị kéo về mức trung bình cá nhân (shrinkage) để tránh thắng nhờ may mắn.",
        ],
    }
    return PersonalModelResult(areas, summary)
