"""What-if table — what the driver's OWN tariff implies, before any trip has been logged (data tier 0).

No zone is ranked and nothing is predicted about where rides appear: this is a SCENARIO table that answers "if I take
a trip of X km and then wait Y minutes, how many VND per hour is that, and what is the lowest fare worth taking for my
goal?". It uses only the tariff (a + b·km), the fuel cost and the goal the driver typed in (or the fit from their log).
The only assumed number is the trip speed — learned from the log when there is one, otherwise a labelled config value.
"""

from __future__ import annotations

from typing import Any

from engine.src.config import WHAT_IF_CFG
from engine.src.types import DriverEconomics


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
    a, b, c = econ.fare_base_vnd, econ.fare_per_km_vnd, econ.fuel_cost_vnd_per_km
    rows: list[dict[str, Any]] = []
    for km in cfg["trip_km"]:
        for wait in cfg["wait_min"]:
            hours = km / v + wait / 60.0
            net_after_fuel = a + (b - c) * km
            row: dict[str, Any] = {
                "trip_km": km,
                "wait_min": wait,
                "net_before_fuel_vnd": round(a + b * km),
                "net_after_fuel_vnd": round(net_after_fuel),
                "hours": round(hours, 3),
                "yield_vnd_per_hour": round(net_after_fuel / hours),
            }
            if econ.target_vnd_per_hour is not None:
                row["min_fare_for_target_vnd"] = round(econ.target_vnd_per_hour * hours + c * km)
            rows.append(row)
    notes = [
        "Đây là KỊCH BẢN theo biểu cước của chính bạn, không phải dự đoán vùng nào có cuốc hay chờ bao lâu.",
        ("Tốc độ chạy lấy từ nhật ký chuyến của bạn." if learned
         else f"Tốc độ chạy {v:g} km/h là GIẢ ĐỊNH cấu hình (đề xuất tạm) vì chưa có nhật ký để học tốc độ."),
    ]
    if econ.fuel_source == "config_default":
        notes.append(f"Xăng tính theo cấu hình {c:g}đ/km vì bạn chưa nhập lít/100km và giá xăng.")
    if econ.target_vnd_per_hour is None:
        notes.append("Chưa có mục tiêu thu nhập/giờ nên chưa có cột cước tối thiểu để nhận cuốc.")
    return {
        "kind": "scenario",
        "tariff": {
            "source": econ.tariff_source,
            "fare_base_vnd": round(a),
            "fare_per_km_vnd": round(b),
        },
        "fuel_cost_vnd_per_km": round(c),
        "fuel_source": econ.fuel_source,
        "speed_kmh": round(v, 1),
        "speed_source": "learned_from_log" if learned else "assumed_config",
        "target_vnd_per_hour": econ.target_vnd_per_hour,
        "rows": rows,
        "notes": notes,
    }
