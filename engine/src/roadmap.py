"""Data roadmap — which missing data blocks which lens, and the cheapest way to unlock it (v3).

A decision product is only credible if it knows what it does NOT know. For every lens that is not fully backed by
data, this lists the blocking datasets (from the same dependency map the readiness gate uses) and concrete unlock paths.
For the two earning lenses it also reports how far the driver's own trip log is from being usable.
"""

from __future__ import annotations

from typing import Any

from engine.src.config import OBJECTIVE_DATA_DEPENDENCIES, PERSONAL_CFG
from engine.src.types import EngineInput, ObjectiveKey, ObjectiveResult

_ORDER: tuple[ObjectiveKey, ...] = ("max_trip_value", "maintain_position", "rest_spot", "safety_comfort")
_NOT_OK = ("missing", "stale", "not_integrated", "partial", None)

_UNLOCK: dict[str, list[str]] = {
    "trip_value": [
        "Bậc 0: nhập biểu cước (giá mở cửa, đơn giá/km), lít/100km, giá xăng, mục tiêu đ/giờ — engine cho bảng kịch bản và mức cước tối thiểu ngay.",
        "Bậc 1: nhật ký chuyến của chính tài xế (giờ bắt đầu, điểm đón, cước ròng, thời lượng, cự ly) — ≥ 20 chuyến để fit biểu cước và xếp hạng vùng. Nguồn tự nguyện, không cần nền tảng chia sẻ dữ liệu.",
    ],
    "booking_and_destinations": [
        "Bậc 2: ghi các đợt chờ (app companion nhận diện đứng yên hoặc nút 'bắt đầu chờ') kèm cách kết thúc: có cuốc / offline / đổi chỗ — engine tính thời gian chờ bằng survival, không còn bị nhiễm giờ nghỉ.",
        "Bậc 3: dữ liệu cộng đồng ẩn danh, gộp theo vùng-giờ với ngưỡng k-ẩn danh — chưa có trong engine.",
    ],
    "verified_waiting_places": [
        "Tài xế xác nhận tại chỗ (cho phép dừng/đỗ, có nhà vệ sinh/ổ sạc) — mỗi lượt xác nhận chuyển 1 điểm từ 'ứng viên' sang 'đã xác minh'.",
    ],
    "traffic": [
        "Chạy định kỳ scripts/fetch_tomtom_traffic.py trên nhiều đoạn đường chính, lưu observed_at; cần phủ nhiều đoạn thay vì 1 đoạn mẫu.",
    ],
    "routing": [
        "Bổ sung mẫu routing OSRM từ vị trí tài xế tới từng điểm nghỉ/khu vực (scripts/fetch_osrm_waiting_candidate_routes.py).",
    ],
    "weather": [
        "Làm mới dự báo Open-Meteo (data/etl/refresh_weather.py) để dự báo phủ khung giờ đang xét.",
    ],
    "poi": [
        "Làm mới POI từ OSM/TomTom cho khu vực tài xế đang hoạt động.",
    ],
}


def build_data_roadmap(
    input_data: EngineInput,
    objectives: dict[ObjectiveKey, ObjectiveResult],
    personal_summary: dict[str, Any] | None,
    tier: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for key in _ORDER:
        res = objectives.get(key)
        deps = OBJECTIVE_DATA_DEPENDENCIES.get(key, [])
        limiting = [
            {"dataset": d, "status": input_data.data_status.get(d) or "unknown",
             "reason": input_data.data_status_reasons.get(d)}
            for d in deps if input_data.data_status.get(d) in _NOT_OK
        ]
        status = res.status if res else "insufficient_data"
        fully_backed = status == "available" and not limiting
        if fully_backed:
            continue
        entry: dict[str, Any] = {
            "objective": key,
            "current_status": status,
            "current_confidence": res.confidence if res else "none",
            "limiting_datasets": limiting,
            "unlock_paths": [{"dataset": x["dataset"], "options": _UNLOCK.get(x["dataset"], [])} for x in limiting],
        }
        if key in ("max_trip_value", "maintain_position"):
            if tier is not None:
                entry["data_tier"] = {"tier": tier["tier"], "label": tier["label"], "next_step": tier["next_step"]}
            need = int(PERSONAL_CFG["min_trips_total"])
            have = (personal_summary or {}).get("trips_in_daypart")
            if personal_summary is None:
                entry["fastest_unlock"] = (
                    f"Cung cấp nhật ký ≥ {need} chuyến gần đây (trong khung giờ đang hoạt động) để engine học thu nhập theo vùng của chính bạn."
                )
            elif personal_summary.get("status") != "ok":
                entry["fastest_unlock"] = (
                    f"Nhật ký hiện có {have if have is not None else 0}/{need} chuyến phù hợp khung giờ — "
                    f"{personal_summary.get('reason', 'chưa đủ để học')}"
                )
            else:
                entry["fastest_unlock"] = (
                    f"Đang dùng dữ liệu của bạn ({personal_summary['trips_in_daypart']} chuyến, "
                    f"{personal_summary.get('wait_spells_in_daypart', 0)} đợt chờ trong khung giờ). "
                    "Mỗi chuyến/đợt chờ ghi thêm làm hẹp khoảng bất định; bước mở rộng tiếp theo là dữ liệu cộng đồng ẩn danh (nhiều tài xế, k-ẩn danh)."
                )
        out.append(entry)
    return out
