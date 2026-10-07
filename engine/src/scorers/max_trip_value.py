"""Objective 1 — Max trip value (spec 5.1), upgraded.

Ranks areas by estimated NET INCOME PER HOUR, not by a raw fare:

    yield = (net_fare - repositioning_cost) / hours(trip + repositioning + expected wait)

Rules kept from the spec:
- every input number comes from the snapshot; a missing required field EXCLUDES the area with a stated reason
  (no default duration, no default fare, no invented per-km rate);
- repositioning from the driver's position is an explicit ESTIMATE (straight-line x detour), labelled as such;
- demand_index is never turned into a probability; it is reported and used only for a Pareto check.
"""

from __future__ import annotations

from engine.src.config import ROBUSTNESS_CFG, TRIP_CFG, GEO_CFG
from engine.src.robustness import analyze_top1, describe
from engine.src.scorers._common import geo_base_params, missing_fields, num, reposition_for, straight_distance_to_area
from engine.src.types import (
    AreaSample,
    DirectionPlan,
    DriverContext,
    ObjectiveResult,
    PlanStep,
    ReadinessMode,
    TripValueCandidate,
)
from engine.src.uncertainty import resolve_confidence

REQUIRED = ["net_value_vnd", "avg_duration_min"]


def _insufficient(reason: str, excluded: list[dict] | None = None) -> ObjectiveResult:
    return ObjectiveResult(
        objective="max_trip_value",
        status="insufficient_data",
        confidence="none",
        reason_for_insufficiency=reason,
        excluded=excluded or None,
    )


def _pareto(cands: list[dict]) -> dict[str, bool | None]:
    """Non-dominated on (yield, demand_index) among areas that report a demand_index."""
    with_d = [c for c in cands if c["demand"] is not None]
    out: dict[str, bool | None] = {c["area"].area_id: None for c in cands}
    for c in with_d:
        dominated = any(
            o is not c and o["yield"] >= c["yield"] and o["demand"] >= c["demand"]
            and (o["yield"] > c["yield"] or o["demand"] > c["demand"])
            for o in with_d
        )
        out[c["area"].area_id] = not dominated
    return out


def score_max_trip_value(
    mode: ReadinessMode,
    areas: list[AreaSample],
    driver_ctx: DriverContext | None = None,
) -> ObjectiveResult:
    if mode == "INSUFFICIENT":
        return _insufficient("Thiếu dữ liệu cước phí/booking thực tế (trip_value, booking_and_destinations).")

    excluded: list[dict] = []
    rows: list[dict] = []
    max_km = driver_ctx.max_reposition_km if driver_ctx else None
    for area in areas:
        name = area.area_name or area.area_id
        tv = area.trip_value
        if not tv:
            excluded.append({"id": area.area_id, "name": name, "reason": "không có dữ liệu trip_value"})
            continue
        miss = missing_fields(tv, REQUIRED)
        if miss:
            excluded.append({"id": area.area_id, "name": name, "reason": f"thiếu trường bắt buộc: {', '.join(miss)}"})
            continue
        net, dur = num(tv["net_value_vnd"]), num(tv["avg_duration_min"])
        if net is None or dur is None or dur <= 0 or net < 0:
            excluded.append({"id": area.area_id, "name": name, "reason": "giá trị cước/thời lượng không hợp lệ (cần net >= 0, thời lượng > 0)"})
            continue
        straight = straight_distance_to_area(driver_ctx, area)
        if driver_ctx is not None and straight is None:
            excluded.append({"id": area.area_id, "name": name, "reason": "khu vực thiếu tọa độ đại diện hợp lệ nên không ước tính được chi phí dịch chuyển"})
            continue
        rep = reposition_for(straight) if straight is not None else None
        if rep is not None and max_km is not None and rep.km > max_km:
            excluded.append({
                "id": area.area_id, "name": name,
                "reason": f"ngoài bán kính dịch chuyển tối đa: ước tính ~{rep.km:.1f}km > {max_km:g}km",
            })
            continue
        dd = area.destination_distribution or {}
        rows.append({
            "area": area, "name": name, "net": net, "dur": dur, "gross": num(tv.get("gross_fare_vnd")),
            "demand": num(tv.get("demand_index")), "straight": straight, "rep": rep,
            "wait": num(dd.get("avg_next_wait_min")),
            "avg_km": num(tv.get("avg_trip_distance_km")), "long_pct": num(tv.get("long_trip_rate_pct")),
            "hotspots": [str(x) for x in (tv.get("hotspot_features") or [])],
            "net_se": num(tv.get("net_se_vnd")), "z": num(tv.get("interval_z")),
            "evidence_n": int(tv["evidence_n"]) if num(tv.get("evidence_n")) is not None else None,
            "source": tv.get("data_source"),
        })

    if not rows:
        return _insufficient(
            "Không có khu vực nào đủ dữ liệu và nằm trong bán kính dịch chuyển để đánh giá.", excluded
        )

    # Wait time enters the yield only if EVERY ranked area has it — otherwise the comparison would be unfair.
    use_wait = all(r["wait"] is not None and r["wait"] >= 0 for r in rows)

    def yield_of(r: dict, params: dict[str, float] | None = None, net: float | None = None) -> float:
        rep = reposition_for(r["straight"], params) if r["straight"] is not None else None
        cost = rep.cost_vnd if rep else 0.0
        rep_min = rep.minutes if rep else 0.0
        minutes = r["dur"] + rep_min + (r["wait"] if use_wait else 0.0)
        return ((r["net"] if net is None else net) - cost) / (minutes / 60.0)

    def yield_interval(r: dict) -> tuple[int, int] | None:
        """Only the fare-noise part: net +/- z*se propagated through the same formula. Not a full prediction interval."""
        if r["net_se"] is None or r["z"] is None:
            return None
        half = r["z"] * r["net_se"]
        return round(yield_of(r, None, max(r["net"] - half, 0.0))), round(yield_of(r, None, r["net"] + half))

    for r in rows:
        r["yield"] = yield_of(r)
    rows.sort(key=lambda r: (-r["yield"], r["area"].area_id))
    pareto = _pareto(rows)
    conf = resolve_confidence("available" if mode == "FULL" else "partial")

    candidates: list[TripValueCandidate] = []
    for rank, r in enumerate(rows, 1):
        rep = r["rep"]
        parts = [
            f"{r['name']}: cước ròng ~{r['net']:,.0f}đ/chuyến (~{r['dur']:.0f} phút)",
        ]
        if rep is not None:
            parts.append(
                f"dịch chuyển ước tính ~{rep.km:.1f}km/~{rep.minutes:.0f} phút/~{rep.cost_vnd:,.0f}đ "
                f"(đường chim bay x{GEO_CFG['detour_factor']:g}, KHÔNG phải routing)"
            )
        if use_wait:
            parts.append(f"chờ cuốc ~{r['wait']:.0f} phút")
        parts.append(f"năng suất ước tính ~{r['yield']:,.0f}đ/giờ")
        iv = yield_interval(r)
        if iv is not None:
            parts.append(f"khoảng ~80% do dao động cước {iv[0]:,}–{iv[1]:,}đ/giờ (dựa trên {r['evidence_n']} chuyến thật)")
        candidates.append(TripValueCandidate(
            area_id=r["area"].area_id, area_name=r["name"],
            expected_net_value_vnd=r["net"], gross_fare_vnd=r["gross"],
            estimated_duration_min=int(round(r["dur"])), demand_index=r["demand"],
            avg_trip_distance_km=r["avg_km"], long_trip_rate_pct=r["long_pct"],
            hotspot_features=r["hotspots"], source_confidence=conf,
            explanation="; ".join(parts) + ".",
            rank=rank,
            reposition_km=None if rep is None else round(rep.km, 2),
            reposition_min=None if rep is None else round(rep.minutes, 1),
            reposition_cost_vnd=None if rep is None else round(rep.cost_vnd),
            wait_min=r["wait"] if use_wait else None,
            yield_vnd_per_hour=round(r["yield"]),
            pareto_optimal=pareto[r["area"].area_id],
            evidence_n=r["evidence_n"],
            yield_low_vnd_per_hour=None if iv is None else iv[0],
            yield_high_vnd_per_hour=None if iv is None else iv[1],
            data_source=r["source"],
        ))

    by_id = {r["area"].area_id: r for r in rows}
    rb = analyze_top1(
        [r["area"].area_id for r in rows],
        lambda i, p: yield_of(by_id[i], p),
        geo_base_params(),
        ROBUSTNESS_CFG,
    )
    names = {r["area"].area_id: r["name"] for r in rows}
    rb_text = describe(rb, names)

    top = candidates[0]
    tr = rows[0]
    accept_min = round(tr["net"] * TRIP_CFG["trip_accept_ratio"])
    facts = [f"cước ròng ~{tr['net']:,.0f}đ/chuyến", f"~{tr['dur']:.0f} phút/chuyến"]
    if tr["avg_km"] is not None:
        facts.append(f"cự ly TB {tr['avg_km']:g}km")
    if tr["long_pct"] is not None:
        facts.append(f"{tr['long_pct']:g}% cuốc đi xa")
    if tr["demand"] is not None:
        facts.append(f"chỉ số cầu {tr['demand']:g}")
    summary = (
        f"Ưu tiên {top.area_name}: năng suất ước tính ~{top.yield_vnd_per_hour:,.0f}đ/giờ "
        f"({'; '.join(facts)})."
    )

    steps = [
        PlanStep(
            1,
            "Bây giờ",
            f"Tiến tới {top.area_name}" if (tr["rep"] is None or not tr["rep"].already_there) else f"Giữ vị trí tại {top.area_name}",
            (
                f"Dịch chuyển ước tính ~{tr['rep'].km:.1f}km (~{tr['rep'].minutes:.0f} phút, ~{tr['rep'].cost_vnd:,.0f}đ nhiên liệu — đây là ước tính, hãy kiểm tra lộ trình thật)."
                if tr["rep"] is not None and not tr["rep"].already_there
                else "Bạn đang ở trong khu vực này theo tọa độ đại diện."
            ),
            "Vào khu vực mục tiêu với chi phí dịch chuyển thấp nhất có thể",
        ),
        PlanStep(
            2,
            f"Tối đa {TRIP_CFG['max_wait_min']} phút",
            "Chỉ nhận cuốc đạt ngưỡng",
            (
                f"Cân nhắc nhận cuốc có cước ròng từ ~{accept_min:,.0f}đ "
                f"({TRIP_CFG['trip_accept_ratio']*100:.0f}% cước ròng bình quân {tr['net']:,.0f}đ của khu vực); "
                f"giới hạn chờ {TRIP_CFG['max_wait_min']} phút (tham số cấu hình)."
            ),
            "Giữ cước ròng mỗi chuyến ở mức bình quân khu vực trở lên",
        ),
    ]
    if tr["hotspots"]:
        steps.append(PlanStep(
            3, "Trong khi chờ", "Chờ tại điểm đón có đặc trưng phù hợp",
            f"Dữ liệu ghi nhận đặc trưng điểm đón: {', '.join(tr['hotspots'])}.",
            "Chờ ở nơi dữ liệu cho thấy có cuốc phù hợp",
        ))

    trade = [
        "Chi phí dịch chuyển và thời gian chờ là ước tính; cước thực tế phụ thuộc thời điểm và cầu.",
        "Engine không dự báo xác suất có cuốc — chỉ số cầu chỉ để tham khảo.",
    ]
    if not use_wait:
        trade.append("Thiếu thời gian chờ (avg_next_wait_min) ở ít nhất một khu vực nên năng suất chưa tính thời gian chờ.")
    if rb_text:
        trade.append(rb_text)
    second = candidates[1] if len(candidates) > 1 else None
    if (second is not None and top.yield_low_vnd_per_hour is not None and second.yield_high_vnd_per_hour is not None):
        if top.yield_low_vnd_per_hour <= second.yield_high_vnd_per_hour:
            trade.append(
                f"Khoảng bất định của {top.area_name} ({top.yield_low_vnd_per_hour:,}–{top.yield_high_vnd_per_hour:,}đ/giờ) "
                f"chồng lấn với {second.area_name} ({second.yield_low_vnd_per_hour:,}–{second.yield_high_vnd_per_hour:,}đ/giờ) "
                "— với số chuyến hiện có chưa đủ cơ sở nói hai vùng khác nhau."
            )
        else:
            trade.append(
                f"Khoảng bất định của {top.area_name} nằm hoàn toàn trên {second.area_name} — chênh lệch đủ rõ so với dao động cước."
            )
    fallback = (
        f"Nếu {top.area_name} không có cuốc đạt ngưỡng sau {TRIP_CFG['max_wait_min']} phút, cân nhắc {second.area_name} "
        f"(~{second.yield_vnd_per_hour:,.0f}đ/giờ ước tính)."
        if second else "Nếu không có cuốc đạt ngưỡng, chuyển sang hướng giữ vị trí (Hướng 2)."
    )

    plan = DirectionPlan(
        plan_id="max_trip_value",
        direction_title="Hướng 1: Săn cuốc giá trị cao (Max Trip Value)",
        objective_focus="Tối đa hóa thu nhập ròng theo giờ, đã trừ chi phí dịch chuyển",
        summary=summary,
        target_location=top.area_name,
        steps=steps,
        key_metrics={
            "expected_net_value_vnd": tr["net"],
            "yield_vnd_per_hour": top.yield_vnd_per_hour,
            "reposition_km_estimated": top.reposition_km,
            "wait_min_used": top.wait_min,
            "demand_index": tr["demand"],
            "pareto_optimal": top.pareto_optimal,
            "areas_ranked": len(candidates),
            "areas_excluded": len(excluded),
            "evidence_n": top.evidence_n,
            "yield_interval_vnd_per_hour": (
                None if top.yield_low_vnd_per_hour is None else [top.yield_low_vnd_per_hour, top.yield_high_vnd_per_hour]
            ),
            "data_source": top.data_source,
        },
        trade_offs=" ".join(trade),
        contingency_fallback=fallback,
    )
    caveat = "Chi phí/thời gian dịch chuyển là ước tính từ đường chim bay; dữ liệu cước có thể là mô phỏng."
    if top.data_source == "driver_trip_log":
        caveat = ("Dữ liệu cước lấy từ nhật ký chuyến của chính bạn (không phải thị trường); chi phí/thời gian dịch chuyển "
                  "là ước tính từ đường chim bay.")
    if rb_text:
        caveat += " " + rb_text
    return ObjectiveResult(
        objective="max_trip_value",
        status="available" if mode == "FULL" else "partial",
        confidence=conf,
        plan=plan,
        candidates=candidates,
        excluded=excluded or None,
        robustness=rb,
        caveat=caveat,
    )
