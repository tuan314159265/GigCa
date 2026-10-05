"""Shared helpers for the objective scorers (reposition estimation between the driver and an area)."""

from __future__ import annotations

from typing import Any

from engine.src.config import GEO_CFG
from engine.src.geo import Reposition, estimate_reposition, haversine_m, valid_point
from engine.src.types import AreaSample, DriverContext


def straight_distance_to_area(ctx: DriverContext | None, area: AreaSample) -> float | None:
    """Straight-line metres from the driver to the area's representative point; None if either is unknown."""
    if ctx is None:
        return None
    pt = valid_point(area.representative_point)
    if pt is None:
        return None
    return haversine_m(ctx.current_lat, ctx.current_lng, pt[0], pt[1])


def reposition_for(straight_m: float, params: dict[str, float] | None = None) -> Reposition:
    p = params or {}
    return estimate_reposition(
        straight_m,
        detour_factor=p.get("detour_factor", GEO_CFG["detour_factor"]),
        speed_kmh=p.get("speed_kmh", GEO_CFG["reposition_speed_kmh"]),
        cost_vnd_per_km=p.get("cost_vnd_per_km", GEO_CFG["reposition_cost_vnd_per_km"]),
        at_area_radius_m=GEO_CFG["at_area_radius_m"],
    )


def geo_base_params() -> dict[str, float]:
    return {
        "detour_factor": float(GEO_CFG["detour_factor"]),
        "speed_kmh": float(GEO_CFG["reposition_speed_kmh"]),
        "cost_vnd_per_km": float(GEO_CFG["reposition_cost_vnd_per_km"]),
    }


def num(value: Any) -> float | None:
    """Coerce to float; None for missing/non-numeric/NaN. Never turns missing into 0."""
    if value is None or isinstance(value, bool):
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return None if v != v else v


def missing_fields(data: dict[str, Any] | None, required: list[str]) -> list[str]:
    data = data or {}
    return [f for f in required if num(data.get(f)) is None]
