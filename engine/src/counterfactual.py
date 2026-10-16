"""Decision boundaries — "what would change this recommendation?" (v3).

The engine is a pure function, so the honest way to answer is to RE-RUN it with one input changed at a time
(idle time, planning horizon, rain tolerance, the driver's position) and report where the answer flips.
Nothing here is a model of the world; it is a sensitivity map of the engine's own output.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from engine.src.config import COUNTERFACTUAL_CFG
from engine.src.geo import valid_point
from engine.src.types import DriverContext, DriverPreferences, DriverRecommendationOutput, EngineInput

_DIR = {
    "max_trip_value": "Hướng 1 (săn cuốc giá trị cao)",
    "maintain_position": "Hướng 2 (giữ vị trí)",
    "rest_spot": "Hướng 3 (nghỉ ngơi)",
    "safety_comfort": "Hướng 4 (an toàn/né mưa)",
}


def signature(out: DriverRecommendationOutput) -> dict[str, Any]:
    first = next((r["objective"] for r in (out.direction_priority or []) if r.get("rankable")), None)

    def top(key: str, attr: str) -> str | None:
        res = out.objectives.get(key)
        return getattr(res.candidates[0], attr) if res and res.plan and res.candidates else None

    safety = out.objectives.get("safety_comfort")
    return {
        "first_direction": first,
        "trip_target": top("max_trip_value", "area_name"),
        "position_target": top("maintain_position", "area_name"),
        "rest_target": top("rest_spot", "name"),
        "safety_signal": safety.weather_action_signal if safety else None,
    }


_CHANGE_LABEL = {
    "first_direction": "hướng nên xem đầu tiên",
    "trip_target": "đích của Hướng 1",
    "position_target": "đích của Hướng 2",
    "rest_target": "điểm nghỉ của Hướng 3",
    "safety_signal": "tín hiệu thời tiết",
}


def _changed(a: dict[str, Any], b: dict[str, Any]) -> list[str]:
    return [k for k in a if a[k] != b[k]]


def _scan_idle(run, ctx: DriverContext, base: dict[str, Any]) -> dict[str, Any]:
    cfg = COUNTERFACTUAL_CFG
    step, cap = int(cfg["idle_scan_step_min"]), int(cfg["idle_scan_max_min"])
    up = down = None
    for v in range(0, cap + 1, step):
        if v > ctx.idle_duration_min and up is None:
            sig = run(replace(ctx, idle_duration_min=v))
            if sig["first_direction"] != base["first_direction"]:
                up = {"at_idle_min": v, "first_direction": sig["first_direction"]}
    for v in range(min(cap, ctx.idle_duration_min - 1), -1, -step):
        sig = run(replace(ctx, idle_duration_min=v))
        if sig["first_direction"] != base["first_direction"]:
            down = {"at_idle_min": v, "first_direction": sig["first_direction"]}
            break
    return {"current_idle_min": ctx.idle_duration_min, "if_waiting_longer": up, "if_waiting_less": down}


def build_decision_boundaries(
    input_data: EngineInput,
    ctx: DriverContext,
    prefs: DriverPreferences,
    base_output: DriverRecommendationOutput,
) -> dict[str, Any]:
    from engine.src.engine import run_driver_engine  # local import: engine.py imports this module

    cfg = COUNTERFACTUAL_CFG

    def run(c: DriverContext, p: DriverPreferences | None = None) -> dict[str, Any]:
        return signature(run_driver_engine(input_data, c, p or prefs, explain=False))

    base = signature(base_output)
    sentences: list[str] = []

    idle = _scan_idle(run, ctx, base)
    if idle["if_waiting_longer"]:
        w = idle["if_waiting_longer"]
        sentences.append(
            f"Nếu bạn chờ thêm đến ~{w['at_idle_min']} phút không có cuốc, hướng nên xem đầu tiên đổi từ "
            f"{_DIR.get(base['first_direction'], '—')} sang {_DIR.get(w['first_direction'], '—')}."
        )
    if idle["if_waiting_less"]:
        w = idle["if_waiting_less"]
        sentences.append(
            f"Nếu bạn mới chờ chỉ ~{w['at_idle_min']} phút, hướng xem đầu tiên sẽ là {_DIR.get(w['first_direction'], '—')}."
        )

    horizons = []
    for h in sorted({int(x) for x in cfg["horizon_scan_min"]} | {ctx.horizon_min}):
        sig = run(replace(ctx, horizon_min=h))
        horizons.append({"horizon_min": h, "is_current": h == ctx.horizon_min, **sig, "changes": _changed(base, sig)})
    flips_h = [x for x in horizons if x["changes"] and not x["is_current"]]
    if flips_h:
        x = flips_h[0]
        sentences.append(
            f"Khung lập kế hoạch {x['horizon_min']} phút (thay vì {ctx.horizon_min}) làm đổi: "
            + ", ".join(_CHANGE_LABEL.get(c, c) for c in x["changes"]) + "."
        )

    rain = []
    for lvl in ("low", "medium", "high"):
        sig = run(ctx, replace(prefs, rain_tolerance_level=lvl))
        rain.append({"rain_tolerance": lvl, "is_current": lvl == prefs.rain_tolerance_level, **sig, "changes": _changed(base, sig)})
    flips_r = [x for x in rain if x["changes"] and not x["is_current"]]
    if flips_r:
        sentences.append(
            "Mức chịu mưa quyết định khuyến nghị: " + "; ".join(
                f"'{x['rain_tolerance']}' → {_DIR.get(x['first_direction'], '—')} (tín hiệu {x['safety_signal']})" for x in flips_r
            ) + "."
        )

    position = []
    seen: set[tuple[float, float]] = set()
    for a in sorted(input_data.areas, key=lambda a: a.area_id):
        pt = valid_point(a.representative_point)
        if pt is None or pt in seen:
            continue
        seen.add(pt)
        if len(position) >= int(cfg["max_position_points"]):
            break
        sig = run(replace(ctx, current_lat=pt[0], current_lng=pt[1]))
        position.append({"from_area_id": a.area_id, "from_name": a.area_name or a.area_id, **sig, "changes": _changed(base, sig)})
    flips_p = [x for x in position if "trip_target" in x["changes"]]
    if flips_p:
        sentences.append(
            f"Điểm đến của Hướng 1 phụ thuộc vị trí: từ {len(position)} vị trí thử, {len(flips_p)} vị trí cho đích khác hiện tại."
        )

    if not sentences:
        sentences.append("Khuyến nghị ổn định: đổi thời gian chờ, khung lập kế hoạch, mức chịu mưa hay vị trí (trong các mốc đã thử) không làm đổi hướng nên xem đầu tiên.")

    return {
        "method": "chạy lại engine (hàm thuần) với đầu vào đổi từng biến một",
        "baseline": base,
        "idle": idle,
        "horizon": horizons,
        "rain_tolerance": rain,
        "position": position,
        "summary": sentences,
    }
