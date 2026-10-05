"""Strategic Synthesis Layer — derives actionable plans from the 4 lenses.

Combines driver idle duration, weather safe window, and rest spot accessibility
into a single concrete tactical recommendation without flattening scores.
"""

from __future__ import annotations

from typing import Any

from engine.src.types import (
    DriverContext,
    DriverPreferences,
    ObjectiveKey,
    ObjectiveResult,
    SynthesizedAction,
)


def synthesize_decision(
    objectives: dict[ObjectiveKey, ObjectiveResult],
    ctx: DriverContext,
    prefs: DriverPreferences,
) -> SynthesizedAction:
    """Synthesize 4 objective outputs into a clear, actionable recommendation for the driver."""
    safety_res = objectives.get("safety_comfort")
    rest_res = objectives.get("rest_spot")

    weather_signal = safety_res.weather_action_signal if safety_res else "THOI_TIET_THUAN_LOI"
    safe_window = safety_res.safe_window_min if safety_res else None
    peak_time = safety_res.peak_rain_time if safety_res else None

    top_rest = rest_res.candidates[0] if (rest_res and rest_res.candidates) else None

    # Case 1: Urgent Rain Storm (immediate or within 0 min)
    if weather_signal == "TRU_MUA_NGAY" or safe_window == 0:
        target_name = (
            f"{top_rest.name} ({round(top_rest.distance_m)}m, ~{max(1, round(top_rest.duration_s / 60))} phút)"
            if top_rest and top_rest.distance_m is not None and top_rest.duration_s is not None
            else "Điểm có mái che gần nhất"
        )
        return SynthesizedAction(
            action_type="TRU_MUA_NGAY",
            headline="Mưa to đang diễn ra hoặc sắp ập đến — Tấp vào trú mưa ngay lập tức",
            recommended_target=target_name,
            urgency="cao",
            deadline_time="Ngay bây giờ",
            strategic_reason=(
                f"Dự báo mưa tại khu vực vượt mức chịu đựng '{prefs.rain_tolerance_level}'. "
                "Cần ưu tiên hàng đầu cho an toàn tay lái và bảo vệ sức khỏe, tạm dừng chạy rỗng ngoài đường."
            ),
        )

    # Case 2: Rain is approaching within the planning horizon
    if weather_signal == "DI_CHUYEN_TRUOC_KHI_MUA" and safe_window is not None:
        target_name = (
            f"{top_rest.name} ({round(top_rest.distance_m)}m, ~{max(1, round(top_rest.duration_s / 60))} phút)"
            if top_rest and top_rest.distance_m is not None and top_rest.duration_s is not None
            else "Điểm dừng chân thuận lợi"
        )
        time_hint = peak_time.split("T")[-1] if (peak_time and "T" in peak_time) else "sắp tới"
        return SynthesizedAction(
            action_type="DI_CHUYEN_NGHI",
            headline=f"Thời tiết còn an toàn trong ~{safe_window} phút — Nên di chuyển tới điểm nghỉ trước đợt mưa",
            recommended_target=target_name,
            urgency="trung_binh",
            deadline_time=f"Trước {time_hint}",
            strategic_reason=(
                f"Đợt mưa dự kiến đạt đỉnh lúc {time_hint}. "
                f"Bạn đã rảnh {ctx.idle_duration_min} phút; việc chủ động tấp vào điểm nghỉ {round(top_rest.distance_m) if top_rest and top_rest.distance_m else ''}m "
                "giúp vừa hồi phục thể lực, vừa tránh kẹt xe và ướt đồ khi mưa đổ xuống."
            ),
        )

    # Case 3: Weather is clear/favorable
    if ctx.idle_duration_min >= 30:
        target_name = (
            f"{top_rest.name} ({round(top_rest.distance_m)}m)"
            if top_rest and top_rest.distance_m is not None
            else "Điểm nghỉ có bóng mát"
        )
        return SynthesizedAction(
            action_type="NGHI_NGOI_NAP_NANG_LUONG",
            headline="Thời tiết khô ráo nhưng bạn đã rảnh lâu — Nên tấp nghỉ giữ sức",
            recommended_target=target_name,
            urgency="trung_binh",
            deadline_time=None,
            strategic_reason=(
                f"Bạn đã chờ {ctx.idle_duration_min} phút chưa có cuốc mới. "
                "Tránh chạy rông lòng vòng hao tổn nhiên liệu khi chưa có tín hiệu nhu cầu; "
                "nên dừng chân tại điểm có chỗ ngồi hoặc bãi đỗ xe hợp lệ."
            ),
        )

    # Case 4: Flexible waiting
    target_name = top_rest.name if top_rest else None
    return SynthesizedAction(
        action_type="CHO_LINH_HOAT",
        headline="Thời tiết thuận lợi — Có thể nán lại vị trí hiện tại hoặc tấp nhẹ điểm chờ gần",
        recommended_target=target_name,
        urgency="thap",
        deadline_time=None,
        strategic_reason=(
            f"Thời tiết trong {ctx.horizon_min} phút tới không có nguy cơ mưa vượt ngưỡng. "
            "Bạn mới rảnh thời gian ngắn, có thể duy trì trạng thái sẵn sàng nhận cuốc."
        ),
    )
