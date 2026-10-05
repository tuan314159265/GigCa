"""Uncertainty Layer — confidence levels, data-driven assumptions, and the final disclaimer (spec Section 7)."""

from __future__ import annotations

from engine.src.config import (
    FINAL_NOTE,
    GEO_CFG,
    RAIN_TOLERANCE_THRESHOLDS,
    ROBUSTNESS_CFG,
    ROUTING_CFG,
)
from engine.src.types import Confidence, DriverPreferences, EngineInput, ObjectiveStatus

_DATASET_LABEL = {
    "weather": "Thời tiết",
    "traffic": "Giao thông",
    "poi": "POI điểm nghỉ",
    "verified_waiting_places": "Điểm chờ đã xác minh",
    "routing": "Routing",
    "trip_value": "Cước phí / trip_value",
    "booking_and_destinations": "Booking & điểm đến",
}


def resolve_confidence(status: ObjectiveStatus) -> Confidence:
    """Map objective status to display confidence level."""
    if status == "available":
        return "medium"
    elif status == "partial":
        return "low"
    return "none"


def build_assumptions(
    input_data: EngineInput,
    prefs: DriverPreferences,
    extra: list[str] | None = None,
) -> list[str]:
    """Assumptions/limitations actually in force for THIS run (driven by the data, not a fixed list)."""
    out: list[str] = []
    if input_data.is_demo:
        label = f" ({input_data.data_label})" if input_data.data_label else ""
        out.append(f"Dữ liệu đầu vào là dữ liệu demo/mô phỏng{label} — không phản ánh thị trường thực.")

    for dataset in sorted(input_data.data_status):
        status = input_data.data_status[dataset]
        if status == "available":
            continue
        reason = input_data.data_status_reasons.get(dataset)
        label = _DATASET_LABEL.get(dataset, dataset)
        out.append(f"{label}: trạng thái '{status}'" + (f" — {reason}" if reason else "") + "; phần phụ thuộc không được tính hoặc chỉ tính một phần.")
    if "adapter" in input_data.data_status_reasons:
        out.append(f"Chuẩn hóa dữ liệu: {input_data.data_status_reasons['adapter']}.")

    th = RAIN_TOLERANCE_THRESHOLDS.get(prefs.rain_tolerance_level, RAIN_TOLERANCE_THRESHOLDS["medium"])
    out.append(
        f"Mức chịu mưa '{prefs.rain_tolerance_level}' = ngưỡng {float(th['prob_pct']):.0f}% xác suất hoặc {float(th['mm']):.1f}mm "
        "(tham số đề xuất tạm, chưa hiệu chỉnh thực nghiệm)."
    )
    out.append(
        f"Chi phí/thời gian dịch chuyển giữa các khu vực là ƯỚC TÍNH từ đường chim bay x{GEO_CFG['detour_factor']:g}, "
        f"tốc độ {GEO_CFG['reposition_speed_kmh']:g} km/h, {GEO_CFG['reposition_cost_vnd_per_km']:g}đ/km — không phải routing."
    )
    out.append(
        f"Khoảng cách tới điểm nghỉ chỉ lấy từ mẫu routing xuất phát trong {ROUTING_CFG['origin_tolerance_m']:g}m quanh bạn; "
        "không ước lượng đường chim bay cho điểm nghỉ."
    )
    out.append(
        f"Độ vững của thứ hạng được kiểm bằng cách dao động từng tham số giả định ±{ROBUSTNESS_CFG['perturbation_pct']:g}%."
    )
    out.extend(extra or [])
    return out


def get_final_note() -> str:
    """Return mandatory disclaimer concluding every engine run."""
    return FINAL_NOTE
