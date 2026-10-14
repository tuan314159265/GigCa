"""Readiness Gate — entrance control before any objective scorer runs.

Implements Section 4 of engine/spec.md.
A scorer must never decide its own readiness mode; the gate determines
FULL, PARTIAL, or INSUFFICIENT based on objective_readiness and data_status.
"""

from __future__ import annotations

from typing import Any

from engine.src.config import OBJECTIVE_DATA_DEPENDENCIES, PERSONAL_CFG
from engine.src.types import (
    DataStatusValue,
    ObjectiveKey,
    ObjectiveStatus,
    ReadinessMode,
)


def resolve_readiness(
    objective: ObjectiveKey,
    data_status: dict[str, DataStatusValue],
    objective_readiness: dict[ObjectiveKey, ObjectiveStatus],
) -> ReadinessMode:
    """Resolve the execution mode (FULL, PARTIAL, INSUFFICIENT) for an objective.

    Rules:
    - If declared readiness is 'insufficient_data', returns 'INSUFFICIENT'.
    - If declared readiness is 'partial', returns 'PARTIAL'.
    - Even if declared is 'available', each required data dependency is inspected:
      if any dependency is 'missing', 'stale', or 'not_integrated', it degrades to 'PARTIAL'.
    - Returns 'FULL' only if declared is 'available' and all dependencies are 'available'.
    """
    declared = objective_readiness.get(objective)
    if declared == "insufficient_data":
        return "INSUFFICIENT"
    if declared == "partial":
        return "PARTIAL"

    required_groups = OBJECTIVE_DATA_DEPENDENCIES.get(objective, [])
    for group in required_groups:
        status = data_status.get(group)
        if status in ("missing", "stale", "not_integrated", None):
            return "PARTIAL"

    return "FULL" if declared == "available" else "PARTIAL"


def data_tier(personal_summary: dict[str, Any] | None, has_tariff: bool) -> dict[str, Any]:
    """Readiness ladder for the data the DRIVER contributes (not market data).

    0  no usable log: with the tariff (published in config or typed) the engine gives a what-if table and a break-even fare,
       no zone ranking.
    1  >= min_trips_total trips in the current day-part: learn zone distance/speed, rank zones (low confidence), and check
       the driver's observed share of the fare against the configured share.
    2  + >= min_spells_total wait spells (GPS/button): survival wait times, direction 2 and a wait term in direction 1.
    3  community: many drivers contribute anonymously, merged per zone-hour with k-anonymity. NOT implemented in the
       engine yet — it is the stated expansion path, so this function never returns it.
    """
    ps = personal_summary or {}
    trips = int(ps.get("trips_in_daypart") or 0)
    spells = int(ps.get("wait_spells_in_daypart") or 0)
    need_trips, need_spells = int(PERSONAL_CFG["min_trips_total"]), int(PERSONAL_CFG["min_spells_total"])
    if trips >= need_trips and spells >= need_spells:
        tier = 2
    elif trips >= need_trips:
        tier = 1
    else:
        tier = 0
    info = {
        0: ("Bậc 0 — chưa có nhật ký đủ dùng",
            ["Bảng kịch bản (what-if) theo biểu cước và mức cước tối thiểu theo mục tiêu của bạn"] if has_tariff else [],
            f"Nhập lít/100km, giá xăng, mục tiêu đ/giờ (biểu cước mặc định là bảng giá công bố); rồi ghi ≥ {need_trips} chuyến "
            "(có cự ly) trong khung giờ đang hoạt động."),
        1: ("Bậc 1 — đủ nhật ký chuyến",
            ["Cự ly/tốc độ theo vùng, xếp hạng vùng theo thu nhập/giờ (độ tin cậy thấp)",
             "Kiểm tra tỷ lệ thực nhận của bạn so với tỷ lệ đang giả định"],
            f"Ghi các đợt chờ (GPS/nút 'bắt đầu chờ'): cần ≥ {need_spells} đợt trong khung giờ để tính thời gian chờ bằng survival."),
        2: ("Bậc 2 — có nhật ký chuyến và đợt chờ",
            ["Thời gian chờ theo survival (đợt offline/đổi chỗ là bị kiểm duyệt)", "Hướng 2 (giữ vị trí) và số hạng chờ trong Hướng 1"],
            "Bậc 3 (cộng đồng): nhiều tài xế đóng góp ẩn danh, gộp theo vùng-giờ với ngưỡng k-ẩn danh — chưa có trong engine."),
    }[tier]
    return {
        "tier": tier, "label": info[0], "unlocked": info[1], "next_step": info[2],
        "trips_in_daypart": trips, "wait_spells_in_daypart": spells,
        "needs": {"trips": need_trips, "wait_spells": need_spells},
    }
