"""Core entry point for the GigCa Decision Engine.

Implements Sections 2, 3, and 8 of engine/spec.md:
- Pure, deterministic function: same input -> same output (the clock is input.generated_at, never the system time).
- 4 independent objective blocks, never combined into a single overallScore.
- Strict data readiness enforcement: missing data != 0.

v2 additions: time-anchored weather, driver-position-aware ranking, robustness analysis, input validation,
data-driven assumptions and a rule-based ordering of the four directions (an ordering, not a score).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from engine.src.config import TIME_CFG, WEATHER_CFG
from engine.src.geo import haversine_m, valid_point
from engine.src.personal_model import build_personal_model
from engine.src.roadmap import build_data_roadmap
from engine.src.tradeoff import build_tradeoff_matrix
from engine.src.priority import build_priority
from engine.src.ml.insights import build_ml_insights
from engine.src.readiness_gate import data_tier, resolve_readiness
from engine.src.scorers.maintain_position import score_maintain_position
from engine.src.scorers.max_trip_value import score_max_trip_value
from engine.src.scorers.rest_spot import score_rest_spot
from engine.src.scorers.safety_comfort import score_safety_comfort
from engine.src.timeutil import parse_local
from engine.src.whatif import build_what_if
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
    explain: bool = False,
) -> DriverRecommendationOutput:
    """Execute the Decision Engine against normalized input and driver context.

    `explain=True` additionally computes `decision_boundaries` (re-runs the engine with one input changed at a time).

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

    # v4: the two earning lenses are fed ONLY by the driver's own data (trip log, tariff, wait spells). The adapter has
    # already removed platform-defined market fields, so there is no market source left to mix with.
    pm = build_personal_model(
        input_data.trip_log, now_local, profile=input_data.driver_profile, spells=input_data.wait_spells,
    )
    ml_info = None
    if pm.usable:
        pm, ml_info = build_ml_insights(input_data, pm, now_local)  # v5: ML refines the per-zone waits only if it wins the backtest
    areas_trip = areas_pos = input_data.areas
    pm_used: list[str] = []

    # 1. max_trip_value (Section 5.1)
    mode_trip = resolve_readiness("max_trip_value", input_data.data_status, input_data.objective_readiness)
    if pm.usable and pm.has_trip_zones and not any(a.trip_value for a in input_data.areas):
        areas_trip, pm_used = [a for a in pm.areas if a.trip_value], pm_used + ["max_trip_value"]
        mode_trip = "PARTIAL"
    objectives["max_trip_value"] = score_max_trip_value(
        mode=mode_trip, areas=areas_trip, driver_ctx=ctx, economics=pm.economics,
    )

    # 2. maintain_position (Section 5.2)
    mode_pos = resolve_readiness("maintain_position", input_data.data_status, input_data.objective_readiness)
    if pm.usable and pm.has_wait_zones and not any(a.destination_distribution for a in input_data.areas):
        areas_pos, pm_used = [a for a in pm.areas if a.destination_distribution], pm_used + ["maintain_position"]
        mode_pos = "PARTIAL"
    objectives["maintain_position"] = score_maintain_position(mode=mode_pos, areas=areas_pos, driver_ctx=ctx)

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
    pm_summary: dict | None = None
    if input_data.trip_log or input_data.wait_spells:
        pm_summary = {**pm.summary, "used_for": pm_used}
        if pm_used:
            extra.append(
                f"Hướng {' & '.join('1' if k == 'max_trip_value' else '2' for k in pm_used)} dùng DỮ LIỆU CỦA CHÍNH BẠN "
                f"({pm.summary['trips_in_daypart']} chuyến, {pm.summary['wait_spells_in_daypart']} đợt chờ trong khung giờ; "
                f"{pm.summary['zones_built']} vùng) — không phải dữ liệu thị trường; vùng ít mẫu bị kéo về mức trung bình cá nhân."
            )
            extra.extend(pm.summary.get("notes", []))
        elif pm.summary.get("status") != "ok":
            extra.append(f"Dữ liệu cá nhân chưa dùng được: {pm.summary.get('reason', 'không đủ dữ liệu')}")
        else:
            extra.append("Đã có dữ liệu ở cấp khu vực nên dữ liệu cá nhân không được trộn vào để tránh so sánh hai nguồn khác bản chất.")
    if ml_info:
        if ml_info["wait_model"]["used"]:
            extra.append(
                "Thời gian chờ theo vùng do MÔ HÌNH ML (hazard/survival học từ đợt chờ của chính bạn theo giờ, mưa, vị trí) ước tính vì nó "
                "thắng baseline thống kê trên tập kiểm tra theo thời gian; đợt offline/đổi chỗ vẫn được coi là bị kiểm duyệt."
            )
        extra.extend(ml_info["notes"])
        explore = (ml_info.get("bandit") or {}).get("explore") or []
        if explore:
            names = {a.area_id: (a.area_name or a.area_id) for a in pm.areas}
            extra.append(
                "Lịch sử của bạn chưa đủ để loại các vùng sau (ít dữ liệu nhưng còn cơ hội cao nhất đáng kể): "
                + "; ".join(names.get(e, e) for e in explore) + " — cân nhắc thử vài lần."
            )
    assumptions = build_assumptions(input_data, prefs, extra)

    tier = data_tier(pm_summary, input_data.driver_profile)
    output = DriverRecommendationOutput(
        generated_at=input_data.generated_at or "",
        objectives=objectives,
        assumptions_used=assumptions,
        final_note=get_final_note(),
        synthesized_action=None,
        direction_priority=build_priority(objectives, ctx, prefs),
        data_quality_warnings=warnings,
        personal_model=pm_summary,
        tradeoff_matrix=build_tradeoff_matrix(objectives, ctx, pm_summary),
        data_roadmap=build_data_roadmap(input_data, objectives, pm_summary, tier),
        data_tier=tier,
        what_if=build_what_if(pm.economics, pm.speed_kmh),
        ml_insights=ml_info,
    )
    if explain:
        from engine.src.counterfactual import build_decision_boundaries  # local import: avoids a cycle

        output = replace(output, decision_boundaries=build_decision_boundaries(input_data, ctx, prefs, output))
    return output
