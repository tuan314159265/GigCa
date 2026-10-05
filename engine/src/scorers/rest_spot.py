"""Objective 3 — Rest spot (spec 5.3), upgraded.

Hard rules (unchanged, now actually enforced):
- distance/duration come ONLY from routing samples; no haversine fallback for rest spots;
- a POI is 'verified' / 'parking allowed' ONLY if the input says so (the old code auto-verified everything in FULL mode);
- a routing sample is used only if its origin (the area's representative point) is near the driver — a route
  measured from somewhere else is not the driver's distance.

New: opening-hours check at the estimated arrival time, fit score (travel time + category fit for how long the
driver has been idle), config-driven rest duration, and a robustness check on the ranking.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from engine.src.config import REST_CATEGORIES, REST_CFG, ROBUSTNESS_CFG, ROUTING_CFG
from engine.src.explanation import format_rest_spot_explanation
from engine.src.robustness import analyze_top1, describe
from engine.src.scorers._common import num, straight_distance_to_area
from engine.src.timeutil import hhmm, is_open_at
from engine.src.types import (
    AreaSample,
    DirectionPlan,
    DriverContext,
    DriverPreferences,
    ObjectiveResult,
    PlanStep,
    PoiCandidate,
    ReadinessMode,
    RestSpotCandidate,
    RoutingSample,
)

VERIFIED_BONUS = 10.0  # verified POIs always rank above unverified ones (config note in engine_config.json)


def find_routing_sample(routing_samples: list[RoutingSample], poi: PoiCandidate) -> RoutingSample | None:
    """Find a routing sample matching destination_id or poi_id (first match wins; list is ordered nearest-origin first)."""
    for route in routing_samples:
        if route.destination_id in (poi.poi_id, f"dest_{poi.poi_id}"):
            return route
    return None


def canonical_category(poi: PoiCandidate) -> str | None:
    aliases = REST_CFG["category_aliases"]
    for raw in [poi.category, poi.subcategory, *poi.tags.values()]:
        if raw is None:
            continue
        cat = aliases.get(raw, raw)
        if cat in REST_CATEGORIES:
            return cat
    return None


def usable_routing_samples(
    areas: list[AreaSample], ctx: DriverContext
) -> tuple[list[RoutingSample], list[dict[str, Any]]]:
    """Routing samples whose origin is close enough to the driver, nearest origin first; plus rejections."""
    tol = float(ROUTING_CFG["origin_tolerance_m"])
    ok: list[tuple[float, str, AreaSample]] = []
    rejected: list[dict[str, Any]] = []
    for area in areas:
        if not area.routing_samples:
            continue
        d = straight_distance_to_area(ctx, area)
        name = area.area_name or area.area_id
        if d is None:
            rejected.append({"id": area.area_id, "name": name, "reason": "mẫu routing không dùng: không xác định được điểm xuất phát"})
        elif d > tol:
            rejected.append({
                "id": area.area_id, "name": name,
                "reason": f"mẫu routing xuất phát cách bạn ~{d:.0f}m (> {tol:g}m) nên không phải khoảng cách của bạn — không dùng",
            })
        else:
            ok.append((d, area.area_id, area))
    ok.sort(key=lambda t: (t[0], t[1]))
    samples: list[RoutingSample] = []
    for _, _, area in ok:
        samples.extend(area.routing_samples)
    return samples, rejected


def rest_duration_min(idle_min: float) -> int:
    chosen = REST_CFG["rest_duration_min_by_idle"][0]["rest_min"]
    for row in sorted(REST_CFG["rest_duration_min_by_idle"], key=lambda r: r["idle_ge"]):
        if idle_min >= row["idle_ge"]:
            chosen = row["rest_min"]
    return int(chosen)


def _fit(duration_s: float, category: str, long_idle: bool, params: dict[str, float]) -> float:
    fit_table = REST_CFG["category_fit_long_idle" if long_idle else "category_fit_short_idle"]
    cat = float(fit_table.get(category, 0.0))
    time_score = 1.0 / (1.0 + duration_s / params["ref_s"])
    wt, wc = params["w_time"], params["w_cat"]
    return (wt * time_score + wc * cat) / (wt + wc)


def score_rest_spot(
    mode: ReadinessMode,
    poi_candidates: list[PoiCandidate],
    routing_samples: list[RoutingSample],
    driver_ctx: DriverContext,
    driver_prefs: DriverPreferences,
    areas: list[AreaSample] | None = None,
    now_local: datetime | None = None,
    **kwargs: Any,
) -> ObjectiveResult:
    if mode == "INSUFFICIENT":
        return ObjectiveResult(
            objective="rest_spot", status="insufficient_data", confidence="none", candidates=[],
            reason_for_insufficiency="Chưa có dữ liệu điểm chờ/nghỉ hoặc bản đồ POI.",
        )

    excluded: list[dict[str, Any]] = []
    if areas is not None:
        routing_samples, rejected = usable_routing_samples(areas, driver_ctx)
        excluded.extend(rejected)

    long_idle = driver_ctx.idle_duration_min >= REST_CFG["long_idle_min"]
    base = {
        "w_time": float(REST_CFG["weights"]["travel_time"]),
        "w_cat": float(REST_CFG["weights"]["category_fit"]),
        "ref_s": float(REST_CFG["travel_time_ref_s"]),
    }
    max_m = driver_ctx.max_reposition_km * 1000.0
    rows: list[dict[str, Any]] = []
    for poi in poi_candidates:
        cat = canonical_category(poi)
        if cat is None:
            continue
        route = find_routing_sample(routing_samples, poi)
        if route is None or route.route_distance_m is None or route.route_duration_s is None:
            excluded.append({"id": poi.poi_id, "name": poi.name, "reason": "không có mẫu routing hợp lệ từ vị trí của bạn (không ước lượng đường chim bay)"})
            continue
        dist, dur = num(route.route_distance_m), num(route.route_duration_s)
        if dist is None or dur is None or dist < 0 or dur < 0:
            excluded.append({"id": poi.poi_id, "name": poi.name, "reason": "mẫu routing có giá trị không hợp lệ"})
            continue
        if dist > max_m:
            excluded.append({"id": poi.poi_id, "name": poi.name, "reason": f"xa hơn bán kính tối đa: {dist:.0f}m > {max_m:.0f}m"})
            continue
        arrival = now_local + timedelta(seconds=dur) if now_local is not None else None
        opened = is_open_at(poi.opening_hours, arrival)
        if opened is False:
            excluded.append({"id": poi.poi_id, "name": poi.name, "reason": f"đóng cửa lúc bạn tới (~{hhmm(arrival)}, giờ mở cửa {poi.opening_hours})"})
            continue
        rows.append({"poi": poi, "cat": cat, "route": route, "dist": dist, "dur": dur, "open": opened, "arrival": arrival})

    if not rows:
        return ObjectiveResult(
            objective="rest_spot", status="insufficient_data", confidence="none", candidates=[],
            excluded=excluded or None,
            reason_for_insufficiency="Không có điểm nghỉ nào có mẫu routing hợp lệ, còn mở cửa và trong bán kính cho phép.",
        )

    def rank_score(r: dict[str, Any], params: dict[str, float] | None = None) -> float:
        p = params or base
        return _fit(r["dur"], r["cat"], long_idle, p) + (VERIFIED_BONUS if r["poi"].verified else 0.0)

    rows.sort(key=lambda r: (-rank_score(r), r["dur"], r["poi"].poi_id))
    top_rows = rows[: int(REST_CFG["max_candidates"])]
    cuts = REST_CFG["tier_cutoffs"]
    tags_by_cat = REST_CFG["amenity_tags"]

    candidates: list[RestSpotCandidate] = []
    for rank, r in enumerate(top_rows, 1):
        poi = r["poi"]
        fit = _fit(r["dur"], r["cat"], long_idle, base)
        tier = "toi_uu" if fit >= cuts["toi_uu"] else ("kha" if fit >= cuts["kha"] else "tieu_chuan")
        explanation = format_rest_spot_explanation(
            name=poi.name, distance_m=r["dist"], duration_s=r["dur"], profile=r["route"].profile,
            verified=poi.verified, parking_allowed=poi.parking_allowed,
        )
        candidates.append(RestSpotCandidate(
            poi_id=poi.poi_id, name=poi.name, category=poi.category,
            distance_m=r["dist"], duration_s=r["dur"],
            verified=poi.verified, parking_allowed=poi.parking_allowed,  # chỉ theo dữ liệu đầu vào
            opening_hours=poi.opening_hours, suitability_tier=tier,
            synergy_tags=list(tags_by_cat.get(r["cat"], [])), explanation=explanation,
            rank=rank, fit_score=round(fit, 3), is_open=r["open"],
            arrival_time=None if r["arrival"] is None else hhmm(r["arrival"]),
        ))

    by_id = {r["poi"].poi_id: r for r in rows}
    rb = analyze_top1([r["poi"].poi_id for r in rows], lambda i, p: rank_score(by_id[i], p), base, ROBUSTNESS_CFG)
    rb_text = describe(rb, {r["poi"].poi_id: r["poi"].name for r in rows})

    top = candidates[0]
    dist_m = top.distance_m or 0.0
    dur_min = max(1, round((top.duration_s or 60) / 60))
    rest_min = rest_duration_min(driver_ctx.idle_duration_min)
    t_arrive = 2 + dur_min
    t_end = t_arrive + rest_min
    legal_ok = top.verified and top.parking_allowed
    fallback = (
        f"Nếu {top.name} hết chỗ hoặc không đỗ được, chuyển sang {candidates[1].name} "
        f"({candidates[1].distance_m:.0f}m theo routing)."
        if len(candidates) > 1 else "Dữ liệu hiện chỉ có 1 điểm hợp lệ; nếu không đỗ được, hãy tự tìm điểm khác."
    )
    unopened = top.is_open is None and top.opening_hours is not None
    hours_note = (
        f" Giờ mở cửa ghi nhận: {top.opening_hours} (đã kiểm tra với giờ tới ~{top.arrival_time})."
        if top.is_open else (
            f" Không đọc được giờ mở cửa ({top.opening_hours}) — hãy kiểm tra khi tới." if unopened else ""
        )
    )
    plan = DirectionPlan(
        plan_id="rest_spot",
        direction_title="Hướng 3: Nghỉ ngơi & phục hồi (Rest & Recharge)",
        objective_focus="Dừng chân ở điểm gần, còn mở cửa, phục hồi trước khi chạy tiếp",
        summary=(
            f"Tạm dừng nhận cuốc và di chuyển {dist_m:.0f}m (~{dur_min} phút) đến {top.name} "
            f"để nghỉ khoảng {rest_min} phút."
        ),
        target_location=top.name,
        steps=[
            PlanStep(1, "1 - 2 phút tới", "Tạm dừng ứng dụng (Chế độ tạm nghỉ)",
                     "Tắt chế độ nhận cuốc trên app để tránh nhận cuốc khi đang di chuyển tới điểm nghỉ.",
                     "Chủ động chuyển sang trạng thái nghỉ."),
            PlanStep(2, f"2 - {t_arrive} phút tới", f"Di chuyển theo lộ trình ngắn {dist_m:.0f}m đến {top.name}",
                     ("Điểm này được dữ liệu ghi nhận đã xác minh và cho phép đỗ xe máy." if legal_ok else
                      "Điểm này CHƯA được xác minh quyền đỗ xe máy — hãy tự kiểm tra biển báo/chỗ đỗ khi tới nơi.") + hours_note,
                     "Đến điểm nghỉ theo khoảng cách routing đã đo." ),
            PlanStep(3, f"{t_arrive} - {t_end} phút tới ({rest_min} phút)", "Nghỉ ngơi và nạp năng lượng",
                     "Uống nước, nghỉ mắt, duỗi cơ; dùng các tiện ích có tại điểm"
                     + (f" (dữ liệu ghi nhận: {', '.join(top.synergy_tags)})." if top.synergy_tags else "."),
                     "Hồi phục thể lực trước khi chạy tiếp."),
            PlanStep(4, f"Sau {t_end} phút", "Bật lại ứng dụng khi đã sẵn sàng",
                     "Khởi động lại xe và bật lại ứng dụng khi bạn thấy đủ tỉnh táo.",
                     "Quay lại nhận cuốc."),
        ],
        key_metrics={
            "target_spot": top.name,
            "distance_m": dist_m,
            "duration_min": dur_min,
            "verified_parking": top.verified,
            "recommended_rest_min": rest_min,
            "amenities": top.synergy_tags,
            "fit_score": top.fit_score,
            "arrival_time": top.arrival_time,
            "candidates_excluded": len(excluded),
        },
        trade_offs=f"Tạm dừng nhận cuốc khoảng {rest_min} phút. " + (rb_text or ""),
        contingency_fallback=fallback,
    )

    n_unverified = sum(1 for c in candidates if not c.verified)
    fully_verified = top.verified and mode == "FULL"
    if n_unverified == 0:
        caveat = "Các điểm nghỉ được liệt kê đều có cờ đã xác minh trong dữ liệu đầu vào; vẫn nên tự kiểm tra biển báo/chỗ đỗ."
    else:
        caveat = (
            f"{n_unverified}/{len(candidates)} điểm là ứng viên từ dữ liệu bản đồ (OSM/Overpass), CHƯA xác minh quyền dừng/đỗ, "
            "giờ mở cửa hay phù hợp cho xe máy. Không phải điểm dừng an toàn/hợp pháp đã kiểm chứng."
        )
    if rb_text:
        caveat += " " + rb_text
    return ObjectiveResult(
        objective="rest_spot",
        status="available" if fully_verified else "partial",
        confidence="medium" if fully_verified else "low",
        plan=plan,
        candidates=candidates,
        excluded=excluded or None,
        robustness=rb,
        caveat=caveat,
    )
