"""Objective 1 — Max trip value (spec 5.1), v4.

Ranks areas by estimated NET INCOME PER HOUR, with every cost counted (fuel of the paid leg AND of the empty leg):

    income per trip = a + (b − c)·d̄_z − c·r_z        a, b: tariff (before fuel)   c: fuel VND/km
    hours per trip  = d̄_z / v_z + r_z / v_rep + w_z / 60
    yield           = income per trip / hours per trip

Rules kept from the spec:
- every input number comes from the DRIVER'S OWN data (trip log, tariff, wait spells): a missing required field EXCLUDES
  the area with a stated reason (no default distance, no default speed, no invented per-km rate);
- the tariff (a, b) and fuel cost (c) arrive in `economics`; without a tariff the lens is insufficient — it never
  falls back to a "market average fare";
- repositioning from the driver's position is an explicit ESTIMATE (straight-line x detour), labelled as such;
- the Pareto check trades yield against its P10 (profit vs. how sure we are), not against a platform-defined index.
"""

from __future__ import annotations

from engine.src.config import ROBUSTNESS_CFG, TRIP_CFG, GEO_CFG
from engine.src.robustness import analyze_top1, describe
from engine.src.scorers._common import geo_base_params, missing_fields, num, reposition_for, straight_distance_to_area
from engine.src.types import (
    AreaSample,
    DirectionPlan,
    DriverContext,
    DriverEconomics,
    ObjectiveResult,
    PlanStep,
    ReadinessMode,
    TripValueCandidate,
)
from engine.src.uncertainty import resolve_confidence

REQUIRED = ["avg_trip_distance_km", "avg_speed_kmh"]


def _insufficient(reason: str, excluded: list[dict] | None = None) -> ObjectiveResult:
    return ObjectiveResult(
        objective="max_trip_value",
        status="insufficient_data",
        confidence="none",
        reason_for_insufficiency=reason,
        excluded=excluded or None,
    )


def _pareto(cands: list[dict]) -> dict[str, bool | None]:
    """Non-dominated on (yield, P10 of yield) among areas that have an interval — profit vs. certainty."""
    with_d = [c for c in cands if c["p10"] is not None]
    out: dict[str, bool | None] = {c["area"].area_id: None for c in cands}
    for c in with_d:
        dominated = any(
            o is not c and o["yield"] >= c["yield"] and o["p10"] >= c["p10"]
            and (o["yield"] > c["yield"] or o["p10"] > c["p10"])
            for o in with_d
        )
        out[c["area"].area_id] = not dominated
    return out


def score_max_trip_value(
    mode: ReadinessMode,
    areas: list[AreaSample],
    driver_ctx: DriverContext | None = None,
    economics: DriverEconomics | None = None,
) -> ObjectiveResult:
    if mode == "INSUFFICIENT":
        return _insufficient("Thiếu dữ liệu của chính tài xế: nhật ký chuyến (có cự ly) và biểu cước a + b·km.")
    if economics is None:
        return _insufficient(
            "Chưa có biểu cước a + b·km: cần nhập biểu cước (giá mở cửa, đơn giá/km) hoặc cung cấp ≥ 20 chuyến có cự ly để engine tự fit."
        )
    E = economics
    base_params = {**geo_base_params(), "cost_vnd_per_km": float(E.fuel_cost_vnd_per_km)}

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
        km, speed = num(tv["avg_trip_distance_km"]), num(tv["avg_speed_kmh"])
        if km is None or speed is None or km <= 0 or speed <= 0:
            excluded.append({"id": area.area_id, "name": name, "reason": "cự ly/tốc độ không hợp lệ (cần cự ly > 0 và tốc độ > 0)"})
            continue
        straight = straight_distance_to_area(driver_ctx, area)
        if driver_ctx is not None and straight is None:
            excluded.append({"id": area.area_id, "name": name, "reason": "khu vực thiếu tọa độ đại diện hợp lệ nên không ước tính được chi phí dịch chuyển"})
            continue
        rep = reposition_for(straight, base_params) if straight is not None else None  # fuel c of THIS driver, same as yield_of
        if rep is not None and max_km is not None and rep.km > max_km:
            excluded.append({
                "id": area.area_id, "name": name,
                "reason": f"ngoài bán kính dịch chuyển tối đa: ước tính ~{rep.km:.1f}km > {max_km:g}km",
            })
            continue
        dd = area.destination_distribution or {}
        rows.append({
            "area": area, "name": name, "km": km, "speed": speed, "straight": straight, "rep": rep,
            "wait": num(dd["expected_wait_min"]) if "expected_wait_min" in dd else num(tv.get("fallback_wait_min")),
            "wait_is_fallback": "expected_wait_min" not in dd and num(tv.get("fallback_wait_min")) is not None,
            "wait_se": num(dd.get("wait_se_min")),
            "hotspots": [str(x) for x in (tv.get("hotspot_features") or [])],
            "km_se": num(tv.get("km_se")), "z": num(tv.get("interval_z")),
            "evidence_n": int(tv["evidence_n"]) if num(tv.get("evidence_n")) is not None else None,
            "source": tv.get("data_source"),
        })

    if not rows:
        return _insufficient(
            "Không có khu vực nào đủ dữ liệu và nằm trong bán kính dịch chuyển để đánh giá.", excluded
        )

    # Wait time enters the yield only if EVERY ranked area has it — otherwise the comparison would be unfair.
    use_wait = all(r["wait"] is not None and r["wait"] >= 0 for r in rows)

    def yield_of(r: dict, params: dict[str, float] | None = None, km: float | None = None, wait: float | None = None) -> float:
        p = base_params if params is None else params
        c = p["cost_vnd_per_km"]
        d = r["km"] if km is None else km
        rep = reposition_for(r["straight"], p) if r["straight"] is not None else None
        income = E.fare_base_vnd + (E.fare_per_km_vnd - c) * d - (rep.cost_vnd if rep else 0.0)
        w = (r["wait"] if wait is None else wait) if use_wait else 0.0
        minutes = d / r["speed"] * 60.0 + (rep.minutes if rep else 0.0) + w
        return income / (minutes / 60.0)

    def yield_interval(r: dict) -> tuple[int, int] | None:
        """P10–P90 from the sampling noise of the zone's mean trip distance and mean wait (± z·se, all corners, through
        the same formula). Not a full prediction interval: tariff and speed uncertainty are not included."""
        if r["km_se"] is None or r["z"] is None:
            return None
        half_km = r["z"] * r["km_se"]
        half_w = r["z"] * r["wait_se"] if (use_wait and r["wait_se"] is not None) else 0.0
        ys = [
            yield_of(r, None, max(r["km"] + dk * half_km, 0.05), max(r["wait"] + dw * half_w, 0.0) if use_wait else None)
            for dk in (-1, 0, 1) for dw in (-1, 0, 1)
        ]
        return round(min(ys)), round(max(ys))

    for r in rows:
        r["yield"] = yield_of(r)
        iv = yield_interval(r)
        r["p10"] = None if iv is None else iv[0]
    rows.sort(key=lambda r: (-r["yield"], r["area"].area_id))
    pareto = _pareto(rows)
    conf = resolve_confidence("available" if mode == "FULL" else "partial")

    candidates: list[TripValueCandidate] = []
    for rank, r in enumerate(rows, 1):
        rep = r["rep"]
        net = E.fare_base_vnd + E.fare_per_km_vnd * r["km"]
        net_after_fuel = net - E.fuel_cost_vnd_per_km * r["km"]
        trip_min = r["km"] / r["speed"] * 60.0
        r["net"], r["net_after_fuel"], r["trip_min"] = net, net_after_fuel, trip_min
        parts = [
            f"{r['name']}: cuốc TB ~{r['km']:.1f}km (~{trip_min:.0f} phút), cước ròng ~{net:,.0f}đ/chuyến trước xăng "
            f"(~{net_after_fuel:,.0f}đ sau xăng chặng chở khách)",
        ]
        if rep is not None:
            parts.append(
                f"dịch chuyển ước tính ~{rep.km:.1f}km/~{rep.minutes:.0f} phút/~{rep.cost_vnd:,.0f}đ "
                f"(đường chim bay x{GEO_CFG['detour_factor']:g}, KHÔNG phải routing)"
            )
        if use_wait:
            parts.append(
                f"chờ cuốc ~{r['wait']:.0f} phút"
                + (" (mức chờ trung bình chung của bạn: vùng này chưa đủ đợt chờ riêng)" if r["wait_is_fallback"] else "")
            )
        parts.append(f"năng suất ước tính ~{r['yield']:,.0f}đ/giờ")
        iv = yield_interval(r)
        if iv is not None:
            parts.append(f"P10–P90 do dao động cự ly cuốc và thời gian chờ {iv[0]:,}–{iv[1]:,}đ/giờ (dựa trên {r['evidence_n']} chuyến thật)")
        candidates.append(TripValueCandidate(
            area_id=r["area"].area_id, area_name=r["name"],
            expected_net_value_vnd=round(net), net_after_fuel_vnd=round(net_after_fuel),
            estimated_duration_min=int(round(trip_min)),
            avg_trip_distance_km=round(r["km"], 2),
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
        base_params,
        ROBUSTNESS_CFG,
    )
    names = {r["area"].area_id: r["name"] for r in rows}
    rb_text = describe(rb, names)

    top = candidates[0]
    tr = rows[0]
    wait_h = (tr["wait"] / 60.0) if use_wait else 0.0
    accept_min = None
    if E.target_vnd_per_hour is not None:
        # break-even fare (before fuel) for a trip as long as this zone's average: hits the driver's own hourly goal
        accept_min = round(E.target_vnd_per_hour * (tr["km"] / tr["speed"] + wait_h) + E.fuel_cost_vnd_per_km * tr["km"])
    facts = [f"cước ròng ~{tr['net']:,.0f}đ/chuyến trước xăng", f"~{tr['trip_min']:.0f} phút/chuyến", f"cự ly TB {tr['km']:.1f}km"]
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
                f"Mức hòa vốn với mục tiêu {E.target_vnd_per_hour:,.0f}đ/giờ của bạn: cuốc dài ~{tr['km']:.1f}km cần cước ròng "
                f"(trước xăng) từ ~{accept_min:,.0f}đ; mỗi km dài hơn/ngắn hơn thì cộng/trừ ~"
                f"{E.target_vnd_per_hour / tr['speed'] + E.fuel_cost_vnd_per_km:,.0f}đ. "
                f"Giới hạn chờ {TRIP_CFG['max_wait_min']} phút (tham số cấu hình)."
                if accept_min is not None else
                "Bạn chưa đặt mục tiêu thu nhập/giờ nên engine chưa đưa ra ngưỡng nhận cuốc — nhập mục tiêu để có mức hòa vốn "
                f"(tự tính từ thời gian chuyến, thời gian chờ và xăng). Giới hạn chờ {TRIP_CFG['max_wait_min']} phút (tham số cấu hình)."
            ),
            "Chỉ nhận cuốc đạt mức hòa vốn theo mục tiêu của chính bạn" if accept_min is not None else "Có ngưỡng nhận cuốc dựa trên mục tiêu của bạn",
        ),
    ]
    if tr["hotspots"]:
        steps.append(PlanStep(
            3, "Trong khi chờ", "Điểm đón có đặc trưng địa lý (chỉ để tham khảo)",
            f"Đặc trưng địa lý ghi nhận: {', '.join(tr['hotspots'])}. Đây là mô tả, KHÔNG phải bằng chứng có cầu.",
            "Biết nơi chờ có tiện ích; không kỳ vọng thêm cuốc vì điều này",
        ))

    trade = [
        "Chi phí dịch chuyển là ước tính từ đường chim bay; cước thực tế phụ thuộc thời điểm và cầu.",
        "Engine không dự báo xác suất có cuốc — kết quả dựa trên cuốc và đợt chờ ĐÃ XẢY RA của chính bạn.",
    ]
    if E.fuel_source == "config_default":
        trade.append(
            f"Xăng tính theo cấu hình {E.fuel_cost_vnd_per_km:g}đ/km vì bạn chưa nhập lít/100km và giá xăng — nhập để năng suất sát xe của bạn."
        )
    if not use_wait:
        trade.append("Thiếu thời gian chờ (đợt chờ GPS/nút bấm) ở ít nhất một khu vực nên năng suất chưa tính thời gian chờ.")
    if rb_text:
        trade.append(rb_text)
    second = candidates[1] if len(candidates) > 1 else None
    if (second is not None and top.yield_low_vnd_per_hour is not None and second.yield_high_vnd_per_hour is not None):
        if top.yield_low_vnd_per_hour <= second.yield_high_vnd_per_hour:
            trade.append(
                f"Khoảng P10–P90 của {top.area_name} ({top.yield_low_vnd_per_hour:,}–{top.yield_high_vnd_per_hour:,}đ/giờ) "
                f"chồng lấn với {second.area_name} ({second.yield_low_vnd_per_hour:,}–{second.yield_high_vnd_per_hour:,}đ/giờ) "
                "— với số chuyến hiện có chưa đủ cơ sở nói hai vùng khác nhau."
            )
        else:
            trade.append(
                f"Khoảng P10–P90 của {top.area_name} nằm hoàn toàn trên {second.area_name} — chênh lệch đủ rõ so với dao động mẫu."
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
            "expected_net_value_vnd": round(tr["net"]),
            "net_after_fuel_vnd": round(tr["net_after_fuel"]),
            "avg_trip_distance_km": round(tr["km"], 2),
            "min_accept_fare_vnd": accept_min,
            "yield_vnd_per_hour": top.yield_vnd_per_hour,
            "reposition_km_estimated": top.reposition_km,
            "wait_min_used": top.wait_min,
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
    tariff_txt = "fit từ nhật ký của bạn" if E.tariff_source == "fitted_from_log" else "do bạn nhập"
    caveat = f"Biểu cước {tariff_txt}; chi phí/thời gian dịch chuyển là ước tính từ đường chim bay; dữ liệu có thể là mô phỏng."
    if top.data_source == "driver_trip_log":
        caveat = (f"Cự ly, tốc độ lấy từ nhật ký chuyến của chính bạn (không phải thị trường); biểu cước {tariff_txt}; "
                  "chi phí/thời gian dịch chuyển là ước tính từ đường chim bay.")
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
