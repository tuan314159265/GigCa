"""Ordering of the four directions — NOT a combined score (spec Principle 3 still holds).

The engine never merges the four objectives into one number. It only says which lens deserves the driver's
attention FIRST, using explicit, config-driven triage rules, each with a stated reason:

  tier 0  Safety now      rain exceeds the driver's tolerance within priority.rain_lead_min minutes
  tier 1  Rest now        the driver reports idle >= priority.fatigue_idle_min (a proxy: idle is not fatigue)
  tier 2  Rain ahead      rain exceeds tolerance later inside the horizon — it caps how long an earning plan can run
  tier 3  Earning lenses  ordered by the driver's goal_weights (declaration order when no weights are given)
  tier 4  Reference       remaining lenses that are informational right now
  tier 9  Not rankable    objective has insufficient data

Ties inside a tier are broken by goal_weights (higher first), then by a fixed lens order — deterministic.
"""

from __future__ import annotations

from typing import Any

from engine.src.config import PRIORITY_CFG
from engine.src.types import DriverContext, DriverPreferences, ObjectiveKey, ObjectiveResult
from engine.src.weather import SIGNAL_BEFORE, SIGNAL_NOW

_ORDER: tuple[ObjectiveKey, ...] = ("max_trip_value", "maintain_position", "rest_spot", "safety_comfort")


def build_priority(
    objectives: dict[ObjectiveKey, ObjectiveResult],
    ctx: DriverContext,
    prefs: DriverPreferences,
) -> list[dict[str, Any]]:
    weights = prefs.goal_weights or {}
    lead = int(PRIORITY_CFG["rain_lead_min"])
    fatigue = int(PRIORITY_CFG["fatigue_idle_min"])
    rows: list[dict[str, Any]] = []
    for key in _ORDER:
        res = objectives.get(key)
        w = float(weights.get(key, 0.0)) if weights else 0.0
        if res is None or res.status == "insufficient_data":
            why = (res.reason_for_insufficiency if res else None) or "chưa có kết quả"
            rows.append({"objective": key, "tier": 9, "rankable": False, "weight": w,
                         "reason": f"Chưa đủ dữ liệu nên không xếp hạng: {why}"})
            continue
        tier, reason = 4, "Tham khảo — chưa có tín hiệu khẩn cấp"
        if key in ("max_trip_value", "maintain_position"):
            tier = 3
            reason = (f"Theo trọng số ưu tiên bạn chọn ({w:g})" if weights else
                      "Không có trọng số ưu tiên — giữ thứ tự mặc định của engine")
        if key == "safety_comfort" and res.weather_action_signal in (SIGNAL_NOW, SIGNAL_BEFORE) \
                and res.safe_window_min is not None:
            if res.safe_window_min <= lead:
                tier = 0
                reason = ("Mưa vượt mức chịu đựng ngay bây giờ" if res.safe_window_min == 0 else
                          f"Mưa vượt mức chịu đựng sau ~{res.safe_window_min} phút (ngưỡng khẩn: {lead} phút)")
            else:
                tier = 2
                reason = (f"Mưa vượt mức chịu đựng sau ~{res.safe_window_min} phút — giới hạn thời gian cho "
                          "các kế hoạch kiếm tiền")
        if key == "rest_spot" and ctx.idle_duration_min >= fatigue:
            tier = min(tier, 1)
            reason = f"Bạn đã chờ {ctx.idle_duration_min} phút (>= {fatigue}) — nên cân nhắc nghỉ"
        rows.append({"objective": key, "tier": tier, "rankable": True, "weight": w, "reason": reason})

    order_index = {k: i for i, k in enumerate(_ORDER)}
    rows.sort(key=lambda r: (r["tier"], -r["weight"], order_index[r["objective"]]))
    for rank, r in enumerate(rows, 1):
        r["rank"] = rank if r["rankable"] else None
    return rows
