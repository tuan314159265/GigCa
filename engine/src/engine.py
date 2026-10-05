"""Core entry point for the GigCa Decision Engine.

Implements Sections 2, 3, and 8 of engine/spec.md:
- Pure, deterministic function: same input -> same output (the clock is input.generated_at, never the system time).
- 4 independent objective blocks, never combined into a single overallScore.
- Strict data readiness enforcement: missing data != 0.

v2 additions: time-anchored weather, driver-position-aware ranking, robustness analysis, input validation,
data-driven assumptions and a rule-based ordering of the four directions (an ordering, not a score).
"""

from __future__ import annotations

from datetime import datetime

from engine.src.config import TIME_CFG, WEATHER_CFG
from engine.src.geo import haversine_m, valid_point
from engine.src.priority import build_priority
from engine.src.readiness_gate import resolve_readiness
from engine.src.scorers.maintain_position import score_maintain_position
from engine.src.scorers.max_trip_value import score_max_trip_value
from engine.src.scorers.rest_spot import score_rest_spot
from engine.src.scorers.safety_comfort import score_safety_comfort
from engine.src.timeutil import parse_local
from engine.src.types import (
    DriverContext,
    DriverPreferences,
    DriverRecommendationOutput,
    EngineInput,
    ObjectiveKey,
    ObjectiveResult,
    RoutingSample,
    WeatherHour,
)
from engine.src.uncertainty import build_assumptions, get_final_note
from engine.src.validation import validate_context, validate_input, validate_preferences


def select_weather(input_data: EngineInput, ctx: DriverContext) -> tuple[list[WeatherHour], list[str]]:
    """Choose the forecast to evaluate, and say where it came from.

    1. A snapshot-level forecast (input.weather_hourly) is an explicit declaration by the data layer -> used as is.
    2. Otherwise the nearest area sample that has a forecast AND lies within weather.area_scope_km of the driver.
    3. Otherwise nothing: a forecast measured far away is not evidence about the driver's location.
    """
    if input_data.weather_hourly:
        return input_data.weather_hourly, ["Dự báo lấy ở cấp snapshot; phạm vi địa lý của dự báo không được ghi rõ."]

    scope_km = float(WEATHER_CFG["area_scope_km"])
    best: tuple[float, str, list[WeatherHour]] | None = None
    nearest_far: tuple[float, str] | None = None
    for area in input_data.areas:
        if not area.weather_hourly:
            continue
        pt = valid_point(area.representative_point)
        if pt is None:
            continue
        d_km = haversine_m(ctx.current_lat, ctx.current_lng, pt[0], pt[1]) / 1000.0
        if d_km <= scope_km:
            if best is None or (d_km, area.area_id) < (best[0], best[1]):
                best = (d_km, area.area_id, area.weather_hourly)
        elif nearest_far is None or (d_km, area.area_id) < nearest_far:
            nearest_far = (d_km, area.area_id)
    if best is not None:
        d_km, area_id, hours = best
        return hours, [f"Dự báo lấy tại điểm mẫu {area_id}, cách bạn ~{d_km:.1f}km (trong phạm vi {scope_km:g}km)."]
    if nearest_far is not None:
        d_km, area_id = nearest_far
        return [], [
            f"Dự báo gần nhất ở điểm mẫu {area_id} cách bạn ~{d_km:.1f}km, vượt phạm vi {scope_km:g}km nên không dùng."
        ]
    return [], []


def run_driver_engine(
    input_data: EngineInput,
    ctx: DriverContext,
    prefs: DriverPreferences,
) -> DriverRecommendationOutput:
    """Execute the Decision Engine against normalized input and driver context.

    Returns DriverRecommendationOutput with 4 strictly independent objective blocks plus an ordering
    (`direction_priority`) that says which lens to look at first — it never picks the action for the driver.
    """
    validate_context(ctx)
    validate_preferences(prefs)
    warnings = validate_input(input_data)

    offset = int(TIME_CFG["local_utc_offset_minutes"])
    now_local: datetime | None = parse_local(input_data.generated_at, offset)
    weather_hours, weather_notes = select_weather(input_data, ctx)

    objectives: dict[ObjectiveKey, ObjectiveResult] = {}

    # 1. max_trip_value (Section 5.1)
    mode_trip = resolve_readiness("max_trip_value", input_data.data_status, input_data.objective_readiness)
    objectives["max_trip_value"] = score_max_trip_value(mode=mode_trip, areas=input_data.areas, driver_ctx=ctx)

    # 2. maintain_position (Section 5.2)
    mode_pos = resolve_readiness("maintain_position", input_data.data_status, input_data.objective_readiness)
    objectives["maintain_position"] = score_maintain_position(mode=mode_pos, areas=input_data.areas, driver_ctx=ctx)

    # 3. rest_spot (Section 5.3) — routing samples are filtered by origin inside the scorer
    mode_rest = resolve_readiness("rest_spot", input_data.data_status, input_data.objective_readiness)
    all_routing_samples: list[RoutingSample] = []
    for area in input_data.areas:
        all_routing_samples.extend(area.routing_samples)
    objectives["rest_spot"] = score_rest_spot(
        mode=mode_rest,
        poi_candidates=input_data.poi_candidates,
        routing_samples=all_routing_samples,
        driver_ctx=ctx,
        driver_prefs=prefs,
        areas=input_data.areas,
        now_local=now_local,
    )

    # 4. safety_comfort (Section 5.4)
    mode_safety = resolve_readiness("safety_comfort", input_data.data_status, input_data.objective_readiness)
    objectives["safety_comfort"] = score_safety_comfort(
        mode=mode_safety,
        weather_hourly=weather_hours,
        driver_ctx=ctx,
        driver_prefs=prefs,
        data_status=input_data.data_status,
        traffic_edges=input_data.traffic,
        areas=input_data.areas,
        now_local=now_local,
        weather_notes=weather_notes,
    )

    extra = list(weather_notes)
    if now_local is None:
        extra.append("Không đọc được generated_at nên không neo được thời điểm hiện tại; kiểm tra giờ mở cửa và cửa sổ mưa bị hạn chế.")
    assumptions = build_assumptions(input_data, prefs, extra)

    return DriverRecommendationOutput(
        generated_at=input_data.generated_at or "",
        objectives=objectives,
        assumptions_used=assumptions,
        final_note=get_final_note(),
        synthesized_action=None,
        direction_priority=build_priority(objectives, ctx, prefs),
        data_quality_warnings=warnings,
    )
