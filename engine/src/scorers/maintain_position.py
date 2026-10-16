"""Objective 2 — Maintain position (spec 5.2), v4.

    position_score = 100·P(wait ≤ t0) - wait_penalty * expected_wait_min - reposition_penalty * reposition_km
                     (clamped to 0-100)

P(wait ≤ t0) and the expected wait are SURVIVAL estimates (Kaplan–Meier) from the driver's own wait spells in that
zone: "in your own history, this share of waits here ended with a trip within t0 minutes". Spells that ended because the
driver went offline or moved are censored, so a lunch break no longer counts as a long wait. This replaces the old
platform-style `favorable_dropoff_pct`, which mixed demand with where the driver chose to drive.

Both inputs must come from the driver's data; a missing field EXCLUDES the area with a stated reason. Penalties are
config parameters, not constants in the logic.
"""

from __future__ import annotations

from engine.src.config import GEO_CFG, POSITION_CFG, ROBUSTNESS_CFG
from engine.src.robustness import analyze_top1, describe
from engine.src.scorers._common import geo_base_params, num, reposition_for, straight_distance_to_area
from engine.src.types import (
    AreaSample,
    DirectionPlan,
    DriverContext,
    ObjectiveResult,
    PlanStep,
    PositionCandidate,
    ReadinessMode,
)
from engine.src.uncertainty import resolve_confidence

T0 = float(POSITION_CFG["wait_thresholds_min"][0])


def _tkey(t: float) -> str:
    return str(int(t)) if float(t).is_integer() else str(t)


def _insufficient(reason: str, excluded: list[dict] | None = None) -> ObjectiveResult:
    return ObjectiveResult(
        objective="maintain_position",
        status="insufficient_data",
        confidence="none",
        reason_for_insufficiency=reason,
        excluded=excluded or None,
    )


def score_maintain_position(
    mode: ReadinessMode,
    areas: list[AreaSample],
    driver_ctx: DriverContext | None = None,
) -> ObjectiveResult:
    if mode == "INSUFFICIENT":
        return _insufficient("Thiếu dữ liệu phân bố điểm đến (booking_and_destinations) hoặc routing.")

    excluded: list[dict] = []
    rows: list[dict] = []
    max_km = driver_ctx.max_reposition_km if driver_ctx else None
    for area in areas:
        name = area.area_name or area.area_id
        dd = area.destination_distribution
        if not dd:
            excluded.append({"id": area.area_id, "name": name, "reason": "không có destination_distribution"})
            continue
        pw = dd.get("p_wait_le_pct")
        by_min = {str(k): num(v) for k, v in pw.items()} if isinstance(pw, dict) else {}
        fav, wait = by_min.get(_tkey(T0)), num(dd.get("expected_wait_min"))
        miss = ([] if fav is not None else [f"p_wait_le_pct[{_tkey(T0)}]"]) + ([] if wait is not None else ["expected_wait_min"])
        if miss:
            excluded.append({"id": area.area_id, "name": name, "reason": f"thiếu trường bắt buộc: {', '.join(miss)}"})
            continue
        if not (0.0 <= fav <= 100.0) or wait < 0:
            excluded.append({"id": area.area_id, "name": name, "reason": "giá trị ngoài miền hợp lệ (p_wait_le_pct 0-100, expected_wait_min >= 0)"})
            continue
        straight = straight_distance_to_area(driver_ctx, area)
        if driver_ctx is not None and straight is None:
            excluded.append({"id": area.area_id, "name": name, "reason": "khu vực thiếu tọa độ đại diện hợp lệ nên không ước tính được quãng dịch chuyển"})
            continue
        rep = reposition_for(straight) if straight is not None else None
        if rep is not None and max_km is not None and rep.km > max_km:
            excluded.append({
                "id": area.area_id, "name": name,
                "reason": f"ngoài bán kính dịch chuyển tối đa: ước tính ~{rep.km:.1f}km > {max_km:g}km",
            })
            continue
        ev = num(dd.get("evidence_n"))
        rows.append({"area": area, "name": name, "fav": fav, "wait": wait, "straight": straight, "rep": rep,
                     "by_min": {k: v for k, v in by_min.items() if v is not None}, "median": num(dd.get("median_wait_min")),
                     "evidence_n": int(ev) if ev is not None else None, "source": dd.get("data_source"),
                     "model": dd.get("model")})

    if not rows:
        return _insufficient(
            "Không có khu vực nào đủ dữ liệu và nằm trong bán kính dịch chuyển để đánh giá.", excluded
        )

    def score_of(r: dict, params: dict[str, float] | None = None) -> float:
        p = params or {}
        rep = reposition_for(r["straight"], p) if r["straight"] is not None else None
        km = rep.km if rep else 0.0
        s = (
            r["fav"]
            - p.get("wait_penalty", POSITION_CFG["wait_penalty_per_min"]) * r["wait"]
            - p.get("reposition_penalty", POSITION_CFG["reposition_penalty_per_km"]) * km
        )
        return max(0.0, min(100.0, s))

    for r in rows:
        r["score"] = score_of(r)
    rows.sort(key=lambda r: (-r["score"], r["area"].area_id))
    conf = resolve_confidence("available" if mode == "FULL" else "partial")

    candidates: list[PositionCandidate] = []
    for rank, r in enumerate(rows, 1):
        rep = r["rep"]
        km_txt = f"; dịch chuyển ước tính ~{rep.km:.1f}km (đường chim bay x{GEO_CFG['detour_factor']:g})" if rep else ""
        lead = "mô hình học từ lịch sử của bạn (giờ, mưa, vị trí) ước tính" if r["model"] else "trong lịch sử của bạn"
        candidates.append(PositionCandidate(
            area_id=r["area"].area_id, area_name=r["name"],
            position_score=round(r["score"], 1), p_wait_le_pct=r["fav"], wait_threshold_min=T0,
            p_wait_le_by_min=r["by_min"], median_wait_min=r["median"], expected_wait_min=round(r["wait"], 1),
            source_confidence=conf,
            explanation=(
                f"{r['name']}: {lead} {r['fav']:g}% đợt chờ ở đây có cuốc trong ≤{T0:g} phút, "
                f"chờ kỳ vọng ~{r['wait']:.0f} phút{km_txt} → điểm giữ vị trí {r['score']:.1f}/100."
            ),
            rank=rank,
            reposition_km=None if rep is None else round(rep.km, 2),
            evidence_n=r["evidence_n"], data_source=r["source"],
        ))

    by_id = {r["area"].area_id: r for r in rows}
    base = {**geo_base_params(),
            "wait_penalty": float(POSITION_CFG["wait_penalty_per_min"]),
            "reposition_penalty": float(POSITION_CFG["reposition_penalty_per_km"])}
    rb = analyze_top1([r["area"].area_id for r in rows], lambda i, p: score_of(by_id[i], p), base, ROBUSTNESS_CFG)
    names = {r["area"].area_id: r["name"] for r in rows}
    rb_text = describe(rb, names)

    top, tr = candidates[0], rows[0]
    rep = tr["rep"]
    summary = (
        f"Ưu tiên ở lại/quay về {top.area_name}: điểm giữ vị trí {top.position_score:.1f}/100 "
        f"(trong lịch sử của bạn {tr['fav']:g}% đợt chờ ở đây có cuốc trong ≤{T0:g} phút, chờ kỳ vọng ~{tr['wait']:.0f} phút)."
    )
    steps = [
        PlanStep(
            1, "Sau khi trả khách",
            f"Hướng về {top.area_name}" if (rep is None or not rep.already_there) else f"Giữ vị trí tại {top.area_name}",
            (f"Quãng dịch chuyển ước tính ~{rep.km:.1f}km (~{rep.minutes:.0f} phút) — ước tính từ đường chim bay, hãy kiểm tra lộ trình thật."
             if rep is not None and not rep.already_there else "Bạn đang ở trong khu vực này theo tọa độ đại diện."),
            "Nằm ở khu vực mà lịch sử của bạn cho thấy chờ ngắn nhất trong phạm vi dịch chuyển",
        ),
        PlanStep(
            2, "Trong khi chờ",
            "Nhận cuốc kế tiếp trong khu vực",
            f"Lịch sử của bạn cho thấy chờ kỳ vọng ~{tr['wait']:.0f} phút; nếu chờ lâu hơn rõ rệt, xét lại vị trí.",
            "Giảm quãng chạy rỗng giữa hai cuốc",
        ),
    ]
    second = candidates[1] if len(candidates) > 1 else None
    trade = [
        f"Điểm là thước đo nội bộ 0-100: 100·P(chờ ≤ {T0:g} phút) trừ phạt chờ kỳ vọng ({POSITION_CFG['wait_penalty_per_min']:g}/phút) "
        f"và phạt dịch chuyển ({POSITION_CFG['reposition_penalty_per_km']:g}/km); tham số đề xuất tạm, chưa hiệu chỉnh.",
    ]
    if rb_text:
        trade.append(rb_text)
    plan = DirectionPlan(
        plan_id="maintain_position",
        direction_title="Hướng 2: Giữ vị trí thuận lợi (Maintain Position)",
        objective_focus="Giảm chạy rỗng, ở lại khu vực trả khách thuận lợi",
        summary=summary,
        target_location=top.area_name,
        steps=steps,
        key_metrics={
            "position_score": top.position_score,
            "p_wait_le_pct": tr["fav"],
            "wait_threshold_min": T0,
            "p_wait_le_by_min": top.p_wait_le_by_min,
            "median_wait_min": top.median_wait_min,
            "expected_wait_min": top.expected_wait_min,
            "reposition_km_estimated": top.reposition_km,
            "areas_ranked": len(candidates),
            "areas_excluded": len(excluded),
        },
        trade_offs=" ".join(trade),
        contingency_fallback=(
            f"Nếu chờ quá lâu tại {top.area_name}, cân nhắc {second.area_name} (điểm {second.position_score:.1f})."
            if second else "Nếu chờ quá lâu, chuyển sang hướng săn cuốc giá trị cao (Hướng 1)."
        ),
    )
    caveat = "Dữ liệu đợt chờ có thể là mô phỏng; quãng dịch chuyển là ước tính."
    if top.data_source == "driver_trip_log":
        caveat = (f"Thời gian chờ học từ {top.evidence_n} đợt chờ trong nhật ký của chính bạn (survival, đợt offline/đổi chỗ được coi là bị kiểm duyệt; "
                  "không phải thị trường và không phải xác suất có cuốc cho lần chờ sau); quãng dịch chuyển là ước tính.")
    if rb_text:
        caveat += " " + rb_text
    return ObjectiveResult(
        objective="maintain_position",
        status="available" if mode == "FULL" else "partial",
        confidence=conf,
        plan=plan,
        candidates=candidates,
        excluded=excluded or None,
        robustness=rb,
        caveat=caveat,
    )
