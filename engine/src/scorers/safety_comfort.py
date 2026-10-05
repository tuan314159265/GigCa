"""Objective 4 — Safety & comfort (spec 5.4), upgraded.

Compared with the naive version:
- rain is evaluated over the real window [now, now + horizon] (not the first N list items);
- forecast values are mapped to the hour they describe and coverage is measured — a forecast that does not cover
  the horizon yields KHONG_DU_DU_BAO, never 'good weather';
- traffic is classified from current/free-flow speed ratio with a freshness filter; corridors and avoid-zones come
  ONLY from real edges — no invented street names, no invented 'avoid' lists;
- plan text carries numbers from the data (windows, mm, %, speeds) instead of fixed claims.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from engine.src.config import RAIN_TOLERANCE_THRESHOLDS, TIME_CFG, TRAFFIC_CFG, WEATHER_CFG
from engine.src.traffic import TrafficAnalysis, analyze_traffic
from engine.src.types import (
    AreaSample,
    DataStatusValue,
    DirectionPlan,
    DriverContext,
    DriverPreferences,
    ObjectiveResult,
    PlanStep,
    ReadinessMode,
    TrafficEdge,
    WeatherHour,
)
from engine.src.weather import (
    SIGNAL_BEFORE,
    SIGNAL_NOW,
    SIGNAL_OK,
    SIGNAL_UNKNOWN,
    WeatherAnalysis,
    analyze_weather,
)


def _traffic_note(status: str | None, ta: TrafficAnalysis) -> str:
    if ta.usable:
        speed = f", tốc độ TB ~{ta.mean_speed_kmh:.0f} km/h" if ta.mean_speed_kmh is not None else ""
        ratio = f" (~{ta.mean_ratio*100:.0f}% tốc độ tự do)" if ta.mean_ratio is not None else ""
        age = f"; dữ liệu mới nhất cách {ta.newest_age_min} phút" if ta.newest_age_min is not None else ""
        partial = " Dữ liệu giao thông một phần — chỉ áp dụng cho các đoạn có dữ liệu." if status == "partial" else ""
        return (
            f"Giao thông trên {ta.used_edges}/{ta.total_edges} đoạn có dữ liệu: {len(ta.smooth)} thông thoáng, "
            f"{len(ta.slow)} chậm, {len(ta.congested)} ùn tắc{speed}{ratio}{age}.{partial}"
        )
    if status in ("available", "partial") and ta.total_edges:
        return (
            "Có nguồn giao thông nhưng không đoạn nào dùng được (quá cũ hoặc thiếu tốc độ) — "
            "không thể đánh giá kẹt xe hay chỉ ra hành lang thông thoáng."
        )
    return "Chưa có dữ liệu giao thông thời gian thực; không thể đánh giá kẹt xe hay chỉ ra hành lang thông thoáng."


def _road_sentence(ta: TrafficAnalysis) -> tuple[str, str]:
    """(corridor sentence, avoid sentence) built only from real edges."""
    if not ta.usable:
        return ("chưa có dữ liệu giao thông nên chưa chỉ ra được hành lang thông thoáng", "")
    corr = f"đoạn đang thông thoáng theo dữ liệu: {', '.join(ta.smooth[:3])}" if ta.smooth else "không có đoạn nào thông thoáng trong dữ liệu"
    avoid = f"đoạn ùn tắc/chậm cần né: {', '.join((ta.congested + ta.slow)[:3])}" if (ta.congested or ta.slow) else ""
    return corr, avoid


def score_safety_comfort(
    mode: ReadinessMode,
    weather_hourly: list[WeatherHour],
    driver_ctx: DriverContext,
    driver_prefs: DriverPreferences,
    data_status: dict[str, DataStatusValue],
    traffic_edges: list[TrafficEdge] | None = None,
    areas: list[AreaSample] | None = None,
    now_local: datetime | None = None,
    weather_notes: list[str] | None = None,
    **kwargs: Any,
) -> ObjectiveResult:
    if mode == "INSUFFICIENT":
        return ObjectiveResult(
            objective="safety_comfort", status="insufficient_data", confidence="none", plan=None, candidates=[],
            reason_for_insufficiency="Chưa có dữ liệu dự báo thời tiết hoặc an toàn đường xá.",
        )

    level = driver_prefs.rain_tolerance_level
    thr = RAIN_TOLERANCE_THRESHOLDS.get(level, RAIN_TOLERANCE_THRESHOLDS["medium"])
    thr_prob, thr_mm = float(thr["prob_pct"]), float(thr["mm"])
    off = int(TIME_CFG["local_utc_offset_minutes"])

    wa: WeatherAnalysis = analyze_weather(weather_hourly, now_local, driver_ctx.horizon_min, thr_prob, thr_mm, WEATHER_CFG, off)
    traffic_status = data_status.get("traffic", "missing")
    ta = analyze_traffic(traffic_edges or [], traffic_status, now_local, TRAFFIC_CFG, off)

    if wa.signal == SIGNAL_UNKNOWN and not ta.usable:
        notes = list(weather_notes or []) + wa.warnings + ta.warnings
        return ObjectiveResult(
            objective="safety_comfort", status="insufficient_data", confidence="none", plan=None, candidates=[],
            rain_flags=wa.flags or None, weather_action_signal=SIGNAL_UNKNOWN,
            traffic_note=_traffic_note(traffic_status, ta),
            reason_for_insufficiency=(
                "Không có dự báo mưa phủ khung thời gian đang xét và không có dữ liệu giao thông dùng được."
                + (" " + " ".join(notes) if notes else "")
            ),
        )

    signal = wa.signal
    corr_txt, avoid_txt = _road_sentence(ta)
    road_txt = corr_txt + (f"; {avoid_txt}" if avoid_txt else "")
    first_start = (wa.first_exceed_window or "").split("–")[0] or None
    peak = wa.peak_flag
    window_val = wa.safe_window_min
    cutoff = None
    if signal == SIGNAL_BEFORE and window_val is not None:
        buf = int(WEATHER_CFG["pre_rain_buffer_min"])
        cutoff = min(window_val, max(5, window_val - buf))

    def rain_desc() -> str:
        f = wa.flags and next((x for x in wa.flags if x.exceeds_tolerance), None)
        if not f:
            return ""
        prob = "n/a" if f.prob_pct is None else f"{f.prob_pct:.0f}%"
        mm = "n/a" if f.mm is None else f"{f.mm:.1f}mm"
        return f"khung {f.window}: {prob}, {mm} — vượt mức chịu mưa '{level}' (ngưỡng {thr_prob:.0f}% / {thr_mm:.1f}mm)"

    if signal == SIGNAL_NOW:
        lead = "Mưa lớn đang diễn ra hoặc sắp ập đến" if wa.heavy else f"Mưa vượt mức chịu đựng '{level}' đang diễn ra hoặc sắp ập đến"
        plan_summary = f"{lead} ({rain_desc()}). Ưu tiên an toàn: tấp vào chỗ có mái che thay vì tiếp tục chạy."
        plan_target = "Điểm có mái che / cây xăng gần nhất trên tuyến"
        steps = [
            PlanStep(1, "Ngay lập tức (0 - 2 phút)", "Tấp xe vào lề có mái che hoặc cây xăng gần nhất",
                     "Bật xi-nhan, giảm tốc và vào khu vực có mái che kiên cố; tránh đứng dưới gốc cây lớn hoặc biển quảng cáo khi có dông gió.",
                     "Xe và người được che chắn."),
            PlanStep(2, "Trong lúc mưa vượt ngưỡng", "Tạm ngưng nhận cuốc",
                     f"Không nhận đơn trong khung mưa vượt ngưỡng ({wa.first_exceed_window}); bảo vệ điện thoại khỏi nước.",
                     "Tránh đi xe khi đường trơn và tầm nhìn kém."),
            PlanStep(3, "Khi mưa ngớt", "Kiểm tra lại dự báo và tình trạng đường",
                     "Xem lại dự báo giờ kế tiếp và quan sát mặt đường trước khi chạy tiếp" + (f"; {road_txt}." if ta.usable else "; hiện không có dữ liệu giao thông."),
                     "Quyết định tiếp tục dựa trên tình hình thực tế."),
            PlanStep(4, "Sau mưa", "Tiếp tục chạy khi đường an toàn",
                     "Chỉ chạy tiếp khi mưa giảm và mặt đường an toàn; tự đánh giá đoạn ngập vì engine không có dữ liệu ngập.",
                     "Quay lại ca chạy an toàn."),
        ]
    elif signal == SIGNAL_BEFORE:
        plan_summary = (
            f"Cửa sổ thời tiết còn an toàn trong ~{window_val} phút trước khi mưa vượt mức chịu đựng '{level}' "
            f"(từ {first_start}; {rain_desc()}). Đường: {road_txt}."
        )
        plan_target = "Chạy các đoạn thông thoáng theo dữ liệu" if ta.smooth else "Khu vực hiện tại, ưu tiên cuốc ngắn"
        steps = [
            PlanStep(1, f"0 - {cutoff} phút", f"Chỉ nhận cuốc ngắn (kết thúc trước {first_start})",
                     f"Tận dụng cửa sổ an toàn còn ~{window_val} phút: ưu tiên cuốc có thể hoàn thành trước {first_start}"
                     + (f"; {road_txt}." if ta.usable else "; chưa có dữ liệu giao thông để chọn tuyến."),
                     "Hoàn thành chuyến trước khi mưa vượt ngưỡng."),
            PlanStep(2, f"{cutoff} - {window_val} phút", "Chuẩn bị sẵn sàng áo mưa và điểm trú",
                     "Mặc sẵn áo mưa, bọc điện thoại chống nước, xác định nơi có mái che gần vị trí.",
                     "Sẵn sàng khi mưa tới."),
            PlanStep(3, f"Từ {first_start}", "Giảm tốc độ, tăng khoảng cách an toàn hoặc tấp vào chỗ trú",
                     "Khi mưa vượt ngưỡng, giảm tốc độ và tăng khoảng cách phanh; nếu đường phía trước ngập hoặc tầm nhìn kém thì dừng ở nơi an toàn.",
                     "Giảm nguy cơ trượt ngã."),
            PlanStep(4, "Sau đợt mưa", "Kiểm tra lại dự báo trước khi chạy tiếp",
                     "Xem lại dự báo và mặt đường trước khi nhận cuốc trở lại.",
                     "Quay lại ca chạy khi điều kiện đã ổn."),
        ]
    elif signal == SIGNAL_OK:
        plan_summary = (
            f"Trong {wa.covered_min} phút tới dự báo không vượt mức chịu mưa '{level}' (ngưỡng {thr_prob:.0f}% / {thr_mm:.1f}mm). "
            f"Đường: {road_txt}."
        )
        plan_target = "Chạy các đoạn thông thoáng theo dữ liệu" if ta.smooth else "Khu vực hiện tại"
        steps = [
            PlanStep(1, "Khung giờ hiện tại", "Lưu thông trên đoạn thông thoáng, né đoạn ùn tắc" if ta.usable else "Theo dõi dự báo và tình hình đường",
                     (f"{road_txt.capitalize()}." if ta.usable else "Chưa có dữ liệu giao thông nên tự quan sát tình hình đường."),
                     "Giảm thời gian mắc kẹt giữa dòng xe" if ta.usable else "Không bị bất ngờ bởi thay đổi thời tiết."),
            PlanStep(2, f"Trong {wa.covered_min} phút tới", "Xem lại dự báo khi khung này kết thúc",
                     "Dự báo chỉ phủ khung thời gian nêu trên; hãy cập nhật trước khi quyết định cho giai đoạn sau.",
                     "Luôn dựa trên dự báo còn hiệu lực."),
        ]
    else:  # SIGNAL_UNKNOWN but traffic usable
        plan_summary = (
            "Chưa đủ dự báo mưa phủ khung thời gian đang xét nên chưa đánh giá được rủi ro mưa. "
            f"Đường: {road_txt}."
        )
        plan_target = "Chạy các đoạn thông thoáng theo dữ liệu" if ta.smooth else "Khu vực hiện tại"
        steps = [
            PlanStep(1, "Ngay bây giờ", "Tự kiểm tra thời tiết trước khi quyết định",
                     "Engine không có dự báo phủ khung này — hãy xem trời/ứng dụng thời tiết. " + road_txt.capitalize() + ".",
                     "Quyết định có đủ thông tin."),
        ]

    conf_ok = mode == "FULL" and signal != SIGNAL_UNKNOWN and ta.usable
    status = "available" if conf_ok else "partial"
    confidence = "medium" if conf_ok else "low"

    avoid_zones: list[str] | None
    az: list[str] = [f"Đoạn {x}" for x in ta.congested + ta.slow]
    if wa.first_exceed_window:
        az.append(f"Khung mưa vượt ngưỡng {wa.first_exceed_window}")
    avoid_zones = az if (ta.usable or wa.first_exceed_window) else None
    safe_corridors = [f"Trục {x}" for x in ta.smooth] if ta.usable else None

    warnings = list(weather_notes or []) + wa.warnings + ta.warnings
    caveat = (
        "Chỉ dựa trên dự báo mưa theo giờ và tốc độ đoạn đường trong dữ liệu; không có dữ liệu gió, nhiệt, UV, ngập úng."
    )
    if warnings:
        caveat += " " + " ".join(warnings)

    plan = DirectionPlan(
        plan_id="safety_comfort",
        direction_title="Hướng 4: Lưu thông an toàn — né mưa & né kẹt xe (Safe Corridor & Traffic-Weather Defense)",
        objective_focus="Giảm tiếp xúc với mưa vượt mức chịu đựng và đoạn đường ùn tắc theo dữ liệu hiện có",
        summary=plan_summary,
        target_location=plan_target,
        steps=steps,
        key_metrics={
            "safe_corridors": safe_corridors,
            "avoid_zones": avoid_zones,
            "safe_window_min": wa.safe_window_min,
            "peak_rain_time": peak.valid_time if peak else None,
            "weather_action_signal": signal,
            "rain_tolerance_level": level,
            "forecast_coverage_pct": round(wa.coverage_ratio * 100),
            "traffic_speed_kmh": None if ta.mean_speed_kmh is None else round(ta.mean_speed_kmh, 1),
            "traffic_mean_ratio": None if ta.mean_ratio is None else round(ta.mean_ratio, 2),
            "traffic_edges_used": ta.used_edges,
        },
        trade_offs=(
            "Né đoạn ùn tắc có thể làm quãng đường dài hơn; engine không có routing né kẹt nên không tính được chênh lệch cự ly/thời gian."
            if ta.usable else
            "Không có dữ liệu giao thông nên không thể cân nhắc đánh đổi giữa né kẹt và quãng đường."
        ),
        contingency_fallback=(
            "Nếu mưa lớn kèm gió mạnh hoặc đường ngập, tấp vào nơi có mái che và chờ; engine không có dữ liệu ngập/gió nên hãy tự đánh giá."
        ),
    )
    return ObjectiveResult(
        objective="safety_comfort",
        status=status,
        confidence=confidence,
        plan=plan,
        candidates=[],
        rain_flags=wa.flags,
        safe_window_min=wa.safe_window_min,
        peak_rain_time=peak.valid_time if peak else None,
        weather_action_signal=signal,
        traffic_note=_traffic_note(traffic_status, ta),
        avoid_zones=avoid_zones,
        safe_corridors=safe_corridors,
        caveat=caveat,
    )
