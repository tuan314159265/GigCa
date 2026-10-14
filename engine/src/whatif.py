"""What-if table — what the tariff implies for THIS driver, before any trip has been logged (data tier 0).

No zone is ranked and nothing is predicted about where rides appear: this is a SCENARIO table that answers "if I take
a trip of X km and then wait Y minutes, how many VND per hour is that, and what is the lowest fare worth taking for my
goal?". It uses only:
- the tariff: the PUBLISHED price list in config (`tariff`) or the driver's own typed values, field by field;
- the driver's share of the fare (fixed in config, e.g. 75%, or typed by the driver);
- the fuel cost and the hourly goal the driver typed in.
The assumed numbers are labelled: the trip speed (learned from the log when there is one, else a config value; it also
drives the per-minute charge) and, when the share is the config value, the share itself (a second yield column at the
low end of `tariff.driver_share_range` shows how much the conclusion depends on it).
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from engine.src.config import TARIFF_CFG, WHAT_IF_CFG
from engine.src.personal_model import describe_tariff, tariff_dict
from engine.src.types import DriverEconomics

_KM_SCAN_MAX = 40.0
_KM_SCAN_STEP = 0.1


def _yield(econ: DriverEconomics, km: float, wait: float, v: float) -> float:
    hours = km / v + wait / 60.0
    return (econ.net_fare_vnd(km, v) - econ.fuel_cost_vnd_per_km * km) / hours


def break_even_km(econ: DriverEconomics, wait: float, v: float) -> float | None:
    """Shortest trip (km, 0.1 km steps up to 40 km) whose yield after fuel reaches the driver's goal, for this wait.

    None = no trip length in that range reaches the goal (with this tariff/share/speed the goal is out of reach)."""
    if econ.target_vnd_per_hour is None:
        return None
    km = _KM_SCAN_STEP
    while km <= _KM_SCAN_MAX + 1e-9:
        if _yield(econ, km, wait, v) >= econ.target_vnd_per_hour:
            return round(km, 1)
        km += _KM_SCAN_STEP
    return None


def build_what_if(
    econ: DriverEconomics | None,
    speed_kmh: float | None = None,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Scenario grid km x wait -> VND/hour (after fuel) and, if the driver set a goal, the break-even fare."""
    if econ is None:
        return None
    cfg = cfg or WHAT_IF_CFG
    learned = speed_kmh is not None and speed_kmh > 0
    v = float(speed_kmh) if learned else float(cfg["assumed_trip_speed_kmh"])
    c = econ.fuel_cost_vnd_per_km
    lo_share = float(TARIFF_CFG["driver_share_range"][0])
    show_low = econ.share_source != "driver_input" and lo_share < econ.driver_share
    econ_low = replace(econ, driver_share=lo_share) if show_low else None

    rows: list[dict[str, Any]] = []
    for km in cfg["trip_km"]:
        km = float(km)
        mins_after = econ.moving_min_after_base(km, v)
        gross = econ.gross_fare_vnd(km, mins_after)
        net = econ.net_fare_vnd(km, v)
        for wait in cfg["wait_min"]:
            hours = km / v + float(wait) / 60.0
            row: dict[str, Any] = {
                "trip_km": km,
                "wait_min": wait,
                "billed_minutes_after_base": round(mins_after, 1),
                "customer_fare_vnd": round(gross),
                "net_before_fuel_vnd": round(net),
                "net_after_fuel_vnd": round(net - c * km),
                "hours": round(hours, 3),
                "yield_vnd_per_hour": round((net - c * km) / hours),
            }
            if econ_low is not None:
                row["yield_at_low_share_vnd_per_hour"] = round(_yield(econ_low, km, float(wait), v))
            if econ.target_vnd_per_hour is not None:
                need_net = econ.target_vnd_per_hour * hours + c * km
                row["min_fare_for_target_vnd"] = round(need_net)  # tiền thực nhận tối thiểu (trước xăng)
                row["min_customer_fare_for_target_vnd"] = round(need_net / econ.driver_share)
                row["tariff_meets_target"] = net >= need_net
            rows.append(row)

    break_even = None
    if econ.target_vnd_per_hour is not None:
        break_even = [{"wait_min": w, "min_trip_km": break_even_km(econ, float(w), v)} for w in cfg["wait_min"]]

    notes = [
        "Đây là KỊCH BẢN theo biểu cước, không phải dự đoán vùng nào có cuốc hay chờ bao lâu.",
        describe_tariff(econ),
        ("Tốc độ chạy lấy từ nhật ký chuyến của bạn." if learned
         else f"Tốc độ chạy {v:g} km/h là GIẢ ĐỊNH cấu hình (đề xuất tạm) vì chưa có nhật ký để học tốc độ; "
              "nó ảnh hưởng cả phụ phí theo phút."),
        "Số phút tính phí = (cự ly − số km gói) / tốc độ × 60 — ước tính, không gồm thời gian kẹt xe đứng yên.",
    ]
    if show_low:
        notes.append(
            f"Cột yield_at_low_share_vnd_per_hour: cùng kịch bản nếu tài xế chỉ nhận {lo_share * 100:.0f}% (cận dưới của khoảng "
            "thực tế) — để thấy kết luận phụ thuộc giả định tỷ lệ nhận đến đâu."
        )
    if econ.fuel_source == "config_default":
        notes.append(f"Xăng tính theo cấu hình {c:g}đ/km vì bạn chưa nhập lít/100km và giá xăng.")
    if econ.target_vnd_per_hour is None:
        notes.append("Chưa có mục tiêu thu nhập/giờ nên chưa có cột cước tối thiểu để nhận cuốc.")
    elif break_even and any(b["min_trip_km"] is None for b in break_even):
        notes.append(
            f"Với một số mức chờ, không cuốc nào ≤ {_KM_SCAN_MAX:g} km đạt mục tiêu {econ.target_vnd_per_hour:,.0f}đ/giờ theo biểu cước "
            "này — mục tiêu có thể quá cao so với biểu cước, hoặc cần chờ ít hơn."
        )
    return {
        "kind": "scenario",
        "tariff": tariff_dict(econ),
        "fuel_cost_vnd_per_km": round(c),
        "fuel_source": econ.fuel_source,
        "speed_kmh": round(v, 1),
        "speed_source": "learned_from_log" if learned else "assumed_config",
        "target_vnd_per_hour": econ.target_vnd_per_hour,
        "rows": rows,
        "break_even_trip_km": break_even,
        "notes": notes,
    }
