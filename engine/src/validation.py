"""Input validation: hard errors for the caller's context, soft warnings for data problems.

Bad DATA never crashes the engine and never becomes a silent 0 — it is excluded and reported in
DriverRecommendationOutput.data_quality_warnings. Bad CONTEXT (impossible coordinates, negative horizon) is a
caller bug and raises ValueError.
"""

from __future__ import annotations

from engine.src.geo import valid_point
from engine.src.types import DriverContext, DriverPreferences, EngineInput

_OBJECTIVES = ("max_trip_value", "maintain_position", "rest_spot", "safety_comfort")


def validate_context(ctx: DriverContext) -> None:
    if not (-90.0 <= ctx.current_lat <= 90.0 and -180.0 <= ctx.current_lng <= 180.0):
        raise ValueError(f"Tọa độ tài xế không hợp lệ: ({ctx.current_lat}, {ctx.current_lng})")
    if ctx.idle_duration_min < 0:
        raise ValueError("idle_duration_min phải >= 0")
    if ctx.horizon_min <= 0:
        raise ValueError("horizon_min phải > 0")
    if ctx.max_reposition_km < 0:
        raise ValueError("max_reposition_km phải >= 0")


def validate_preferences(prefs: DriverPreferences) -> None:
    if prefs.rain_tolerance_level not in ("low", "medium", "high"):
        raise ValueError(f"rain_tolerance_level không hợp lệ: {prefs.rain_tolerance_level!r}")
    if prefs.goal_weights is not None:
        for key, w in prefs.goal_weights.items():
            if key not in _OBJECTIVES:
                raise ValueError(f"goal_weights có hướng không tồn tại: {key!r}")
            if w is None or w < 0:
                raise ValueError(f"goal_weights[{key!r}] phải >= 0")


def validate_input(data: EngineInput) -> list[str]:
    """Deterministic list of data-quality warnings (sorted)."""
    w: list[str] = []
    ids = [a.area_id for a in data.areas]
    dup = sorted({i for i in ids if ids.count(i) > 1})
    if dup:
        w.append(f"Trùng area_id: {', '.join(dup)}")
    for a in data.areas:
        if valid_point(a.representative_point) is None:
            w.append(f"Khu vực {a.area_id}: tọa độ đại diện thiếu/không hợp lệ — bị loại khỏi phép tính cần vị trí")
        for r in a.routing_samples:
            if (r.route_distance_m is not None and r.route_distance_m < 0) or (
                r.route_duration_s is not None and r.route_duration_s < 0
            ):
                w.append(f"Khu vực {a.area_id}: mẫu routing {r.destination_id} có giá trị âm")
    pids = [p.poi_id for p in data.poi_candidates]
    dup_p = sorted({i for i in pids if pids.count(i) > 1})
    if dup_p:
        w.append(f"Trùng poi_id: {', '.join(dup_p)}")
    for e in data.traffic:
        if (e.current_speed_kmh is not None and e.current_speed_kmh < 0) or (
            e.free_flow_speed_kmh is not None and e.free_flow_speed_kmh < 0
        ):
            w.append(f"Đoạn giao thông {e.edge_id}: tốc độ âm — không dùng")

    st = data.data_status
    any_weather = bool(data.weather_hourly) or any(a.weather_hourly for a in data.areas)
    if st.get("weather") == "available" and not any_weather:
        w.append("data_status.weather = available nhưng không có dự báo nào trong input")
    if st.get("traffic") == "available" and not data.traffic:
        w.append("data_status.traffic = available nhưng không có đoạn giao thông nào trong input")
    if st.get("poi") == "available" and not data.poi_candidates:
        w.append("data_status.poi = available nhưng không có POI nào trong input")
    return sorted(set(w))
