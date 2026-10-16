"""Trade-off matrix — the four directions on shared, comparable axes (v3).

The engine still never merges the four lenses into one score. This module only answers the question a driver
actually asks when staring at four plans: "what do I give up for each one, in the same units?"

Every number is derived from figures the scorers already produced:
- income lenses: estimated net VND/hour (lens 1 directly; lens 2 only when lens 1 also evaluated the same area);
- rest: income forgone while resting = reference yield x rest minutes (an ESTIMATE of opportunity cost);
- safety: how much earning time remains before rain exceeds the driver's tolerance.

The reference yield is lens 1's best estimated yield, else the driver's own historical baseline, else none — and the
matrix says which. Missing inputs give None, never 0.
"""

from __future__ import annotations

from typing import Any

from engine.src.types import DriverContext, ObjectiveKey, ObjectiveResult
from engine.src.weather import SIGNAL_BEFORE, SIGNAL_NOW

_LABEL = {
    "max_trip_value": "Hướng 1 — Săn cuốc giá trị cao",
    "maintain_position": "Hướng 2 — Giữ vị trí thuận lợi",
    "rest_spot": "Hướng 3 — Nghỉ ngơi",
    "safety_comfort": "Hướng 4 — An toàn / né mưa",
}


def _fmt(v: float | int) -> str:
    return f"{v:,.0f}đ"


def build_tradeoff_matrix(
    objectives: dict[ObjectiveKey, ObjectiveResult],
    ctx: DriverContext,
    personal_summary: dict[str, Any] | None,
) -> dict[str, Any] | None:
    trip = objectives.get("max_trip_value")
    pos = objectives.get("maintain_position")
    rest = objectives.get("rest_spot")
    safety = objectives.get("safety_comfort")

    trip_top = trip.candidates[0] if trip and trip.plan and trip.candidates else None
    yield_by_area = {c.area_id: c for c in (trip.candidates if trip and trip.plan else [])}

    ref_yield: float | None = None
    ref_source: str | None = None
    if trip_top is not None and trip_top.yield_vnd_per_hour is not None:
        ref_yield, ref_source = float(trip_top.yield_vnd_per_hour), f"năng suất ước tính tốt nhất của Hướng 1 ({trip_top.area_name})"
    elif personal_summary and personal_summary.get("baseline_yield_vnd_per_hour"):
        ref_yield, ref_source = float(personal_summary["baseline_yield_vnd_per_hour"]), "mức năng suất trung bình trong nhật ký chuyến của bạn"

    rows: list[dict[str, Any]] = []

    # Lens 1
    if trip_top is not None:
        rows.append({
            "objective": "max_trip_value", "label": _LABEL["max_trip_value"], "available": True,
            "target": trip_top.area_name,
            "income_vnd_per_hour": trip_top.yield_vnd_per_hour,
            "income_interval_vnd_per_hour": (
                None if trip_top.yield_low_vnd_per_hour is None
                else [trip_top.yield_low_vnd_per_hour, trip_top.yield_high_vnd_per_hour]
            ),
            "time_to_start_min": trip_top.reposition_min,
            "main_cost": (
                f"dịch chuyển ước tính ~{trip_top.reposition_km:g}km (~{_fmt(trip_top.reposition_cost_vnd or 0)} nhiên liệu)"
                if trip_top.reposition_km else "không cần dịch chuyển"
            ),
        })
    else:
        rows.append({"objective": "max_trip_value", "label": _LABEL["max_trip_value"], "available": False,
                     "reason": (trip.reason_for_insufficiency if trip else None) or "chưa có kết quả"})

    # Lens 2 — money only when lens 1 priced the very same area
    pos_top = pos.candidates[0] if pos and pos.plan and pos.candidates else None
    if pos_top is not None:
        same = yield_by_area.get(pos_top.area_id)
        rows.append({
            "objective": "maintain_position", "label": _LABEL["maintain_position"], "available": True,
            "target": pos_top.area_name,
            "income_vnd_per_hour": None if same is None else same.yield_vnd_per_hour,
            "income_basis": (
                "năng suất của chính khu vực này theo Hướng 1" if same is not None
                else "không quy đổi được ra tiền: Hướng 2 chỉ đo thời gian chờ (survival) từ các đợt chờ của bạn"
            ),
            "position_score": pos_top.position_score,
            "p_wait_le_pct": pos_top.p_wait_le_pct,
            "wait_threshold_min": pos_top.wait_threshold_min,
            "expected_wait_min": pos_top.expected_wait_min,
            "main_cost": (f"dịch chuyển ước tính ~{pos_top.reposition_km:g}km" if pos_top.reposition_km else "không cần dịch chuyển"),
        })
    else:
        rows.append({"objective": "maintain_position", "label": _LABEL["maintain_position"], "available": False,
                     "reason": (pos.reason_for_insufficiency if pos else None) or "chưa có kết quả"})

    # Lens 3 — opportunity cost of resting
    rest_min = rest.plan.key_metrics.get("recommended_rest_min") if rest and rest.plan else None
    if rest and rest.plan:
        forgone = None
        if ref_yield is not None and isinstance(rest_min, (int, float)):
            forgone = round(ref_yield * rest_min / 60.0)
        rows.append({
            "objective": "rest_spot", "label": _LABEL["rest_spot"], "available": True,
            "target": rest.plan.target_location, "rest_min": rest_min,
            "income_forgone_vnd": forgone,
            "income_basis": (f"chi phí cơ hội ≈ {ref_source} × thời gian nghỉ" if forgone is not None
                             else "chưa có mức năng suất tham chiếu nên không ước tính được thu nhập bỏ lỡ"),
            "main_cost": "tạm dừng nhận cuốc",
        })
    else:
        rows.append({"objective": "rest_spot", "label": _LABEL["rest_spot"], "available": False,
                     "reason": (rest.reason_for_insufficiency if rest else None) or "chưa có kết quả"})

    # Lens 4 — earning time left before rain exceeds tolerance
    if safety and safety.plan:
        window = safety.safe_window_min
        rain_soon = safety.weather_action_signal in (SIGNAL_NOW, SIGNAL_BEFORE) and window is not None
        usable = min(window, ctx.horizon_min) if rain_soon else None
        income_before = round(ref_yield * usable / 60.0) if (ref_yield is not None and usable is not None) else None
        rows.append({
            "objective": "safety_comfort", "label": _LABEL["safety_comfort"], "available": True,
            "target": safety.plan.target_location,
            "weather_action_signal": safety.weather_action_signal,
            "safe_window_min": window,
            "earning_minutes_before_rain": usable,
            "income_before_rain_vnd": income_before,
            "income_basis": (f"≈ {ref_source} × thời gian còn lại trước khi mưa vượt mức chịu đựng"
                             if income_before is not None else "không có mốc mưa trong khung đang xét hoặc thiếu mức năng suất tham chiếu"),
            "main_cost": "có thể phải đổi tuyến/khu vực để tránh mưa hoặc điểm kẹt",
        })
    else:
        rows.append({"objective": "safety_comfort", "label": _LABEL["safety_comfort"], "available": False,
                     "reason": (safety.reason_for_insufficiency if safety else None) or "chưa có kết quả"})

    if not any(r["available"] for r in rows):
        return None

    comparisons: list[str] = []
    if trip_top is not None and pos_top is not None and trip_top.area_id != pos_top.area_id:
        same = yield_by_area.get(pos_top.area_id)
        if same is not None and same.yield_vnd_per_hour is not None and trip_top.yield_vnd_per_hour is not None:
            diff = trip_top.yield_vnd_per_hour - same.yield_vnd_per_hour
            comparisons.append(
                f"Chọn {trip_top.area_name} (Hướng 1) thay vì {pos_top.area_name} (Hướng 2): "
                f"{'hơn' if diff >= 0 else 'kém'} ~{_fmt(abs(diff))}/giờ theo ước tính của Hướng 1, "
                f"đổi lại phải chấp nhận khác biệt về thời gian chờ và quãng dịch chuyển."
            )
    for r in rows:
        if r["objective"] == "rest_spot" and r.get("income_forgone_vnd") is not None:
            comparisons.append(
                f"Nghỉ ~{r['rest_min']} phút tại {r['target']} bỏ lỡ khoảng {_fmt(r['income_forgone_vnd'])} thu nhập dự kiến (ước tính)."
            )
        if r["objective"] == "safety_comfort" and r.get("earning_minutes_before_rain") == 0:
            comparisons.append("Mưa đã vượt mức chịu đựng của bạn ngay bây giờ: không còn khung thời gian kiếm tiền an toàn trong dự báo hiện có.")
        elif r["objective"] == "safety_comfort" and r.get("income_before_rain_vnd") is not None:
            comparisons.append(
                f"Còn ~{r['earning_minutes_before_rain']} phút kiếm tiền trước khi mưa vượt mức chịu đựng "
                f"(~{_fmt(r['income_before_rain_vnd'])} theo mức năng suất tham chiếu)."
            )

    return {
        "reference_yield_vnd_per_hour": None if ref_yield is None else round(ref_yield),
        "reference_source": ref_source,
        "rows": rows,
        "comparisons": comparisons,
        "note": "Đây là bảng so sánh trên cùng đơn vị, KHÔNG phải điểm tổng; các số quy đổi tiền đều là ước tính từ dữ liệu hiện có.",
    }
