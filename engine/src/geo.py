"""Geometry helpers.

Straight-line distance x detour factor is ONLY an ESTIMATE used for repositioning cost between areas.
It is never presented as routing and never used for rest-spot distances (those come from routing samples only).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

EARTH_RADIUS_M = 6371008.8


def valid_point(point: Any) -> tuple[float, float] | None:
    """Return (lat, lng) if the dict holds a valid coordinate, else None."""
    try:
        lat = float(point["latitude"])
        lng = float(point["longitude"])
    except (KeyError, TypeError, ValueError):
        return None
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0):
        return None
    return lat, lng


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


@dataclass(frozen=True)
class Reposition:
    straight_m: float
    km: float
    minutes: float
    cost_vnd: float
    already_there: bool


def estimate_reposition(
    straight_m: float,
    *,
    detour_factor: float,
    speed_kmh: float,
    cost_vnd_per_km: float,
    at_area_radius_m: float,
) -> Reposition:
    if straight_m <= at_area_radius_m:
        return Reposition(straight_m, 0.0, 0.0, 0.0, True)
    km = straight_m * detour_factor / 1000.0
    return Reposition(straight_m, km, km / speed_kmh * 60.0, km * cost_vnd_per_km, False)
