"""Seeded simulator of ONE driver with a KNOWN ground truth — used to test/benchmark the ML layer.

Everything here is SYNTHETIC. It exists because a model can only be shown to "recover the truth" when the truth is known.
Results on this data prove the pipeline works and that the gate is honest; they say nothing about real-world accuracy.

Ground truth (what a model should discover): waits are shorter in peak hours, much longer at night, shorter in rain, and
the zone x hour interaction matters (Bến Thành is busy at night, Hàng Xanh is dead in the morning, Tân Định peaks at
lunch). The simulated driver is NAIVE (picks zones by habit, ignores the time of day), which is exactly the selection
bias a bandit has to cope with.
"""

from __future__ import annotations

import math
import random
from datetime import datetime, timedelta
from typing import Any

TZ = "+07:00"
PROFILE = {
    "fare_base_vnd": 12000, "fare_per_km_vnd": 4800, "fuel_l_per_100km": 2.2, "fuel_price_vnd_per_l": 24000,
    "target_vnd_per_hour": 90000,
}
FUEL_VND_PER_KM = PROFILE["fuel_l_per_100km"] * PROFILE["fuel_price_vnd_per_l"] / 100.0
# zone: (lat, lng, mean trip km, mean speed km/h, base mean wait min, habit weight)
ZONES: dict[str, tuple[float, float, float, float, float, float]] = {
    "ben_thanh": (10.7725, 106.6980, 4.5, 20.0, 6.0, 0.34),
    "tan_dinh": (10.7890, 106.6910, 3.5, 19.0, 9.0, 0.22),
    "vo_thi_sau": (10.7830, 106.6960, 3.0, 18.0, 10.0, 0.22),
    "hang_xanh": (10.8010, 106.7110, 8.0, 24.0, 18.0, 0.22),
}
PATIENCE_MIN = 25.0
NOISE_VND = 2500.0
JITTER_DEG = 0.0007


def wait_multiplier(zone: str, hour: int, rain_mm: float) -> float:
    """Ground-truth factor on the zone's base mean wait."""
    if 7 <= hour < 9:
        m = 0.6
    elif 11 <= hour < 14:
        m = 0.8
    elif 17 <= hour < 20:
        m = 0.5
    elif hour >= 21:
        m = 1.6
    else:
        m = 1.0
    if zone == "ben_thanh" and hour >= 21:
        m = 0.8
    if zone == "hang_xanh" and 7 <= hour < 9:
        m *= 1.6
    if zone == "tan_dinh" and 11 <= hour < 14:
        m *= 0.6
    if rain_mm > 0.2:
        m *= 0.65
    return m


def draw_wait(rng: random.Random, zone: str, hour: int, rain_mm: float) -> float:
    return rng.expovariate(1.0 / (ZONES[zone][4] * wait_multiplier(zone, hour, rain_mm)))


def draw_trip(rng: random.Random, zone: str, rain_mm: float) -> tuple[float, float, float]:
    """(km, net_vnd before fuel, duration_min)."""
    _, _, mean_km, speed, _, _ = ZONES[zone]
    wet = rain_mm > 0.2
    km = max(0.8, rng.lognormvariate(math.log(mean_km * (1.1 if wet else 1.0)), 0.35))
    net = max(PROFILE["fare_base_vnd"] + PROFILE["fare_per_km_vnd"] * km + rng.gauss(0.0, NOISE_VND), 8000.0)
    v = max(8.0, rng.gauss(speed * (0.85 if wet else 1.0), 2.0))
    return km, net, km / v * 60.0


def cycle_yield(rng: random.Random, zone: str, hour: int, rain_mm: float) -> float:
    """VND/hour of one completed cycle (wait + paid trip), fuel of the paid leg included. Ground-truth sampler."""
    w = draw_wait(rng, zone, hour, rain_mm)
    km, net, dur = draw_trip(rng, zone, rain_mm)
    return (net - FUEL_VND_PER_KM * km) / ((w + dur) / 60.0)


def true_mean_yield(zone: str, hour: int, rain_mm: float, n: int = 20000, seed: int = 99) -> float:
    rng = random.Random(seed)
    return sum(cycle_yield(rng, zone, hour, rain_mm) for _ in range(n)) / n


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S") + TZ


def simulate_driver(seed: int = 20261006, days: int = 30, now: datetime | None = None) -> dict[str, Any]:
    """A full multi-week log: shifts across the day, rain windows, lunch/off-line breaks, relocations after 25 min."""
    now = now or datetime(2026, 10, 6, 19, 35)
    rng = random.Random(seed)
    names = sorted(ZONES)
    weights = [ZONES[n][5] for n in names]
    trips: list[dict] = []
    spells: list[dict] = []
    tid = sid = 0
    for day in range(days, 0, -1):
        d0 = (now - timedelta(days=day)).replace(hour=0, minute=0, second=0, microsecond=0)
        rain_start = rng.randint(6, 20) if rng.random() < 0.35 else None
        rain_len = rng.randint(2, 4)
        rain_level = rng.uniform(1.0, 6.0)

        def rain_at(dt: datetime) -> float:
            if rain_start is not None and rain_start <= dt.hour < rain_start + rain_len:
                return round(rain_level, 2)
            return 0.0

        clock = d0 + timedelta(hours=rng.randint(7, 10), minutes=rng.randint(0, 59))
        end = d0 + timedelta(hours=rng.randint(20, 23), minutes=rng.randint(0, 59))
        zone = rng.choices(names, weights=weights)[0]
        while clock < end:
            lat0, lng0 = ZONES[zone][0], ZONES[zone][1]
            lat = round(lat0 + rng.uniform(-JITTER_DEG, JITTER_DEG), 6)
            lng = round(lng0 + rng.uniform(-JITTER_DEG, JITTER_DEG), 6)
            rain = rain_at(clock)
            wait = draw_wait(rng, zone, clock.hour, rain)
            sid += 1
            base = {"spell_id": f"w{sid:04d}", "start": _iso(clock), "lat": lat, "lng": lng, "rain_mm": rain}
            if rng.random() < 0.05:  # a break: the driver gives up waiting and goes offline (censored)
                gone = rng.uniform(8, 40)
                spells.append({**base, "end": _iso(clock + timedelta(minutes=gone)), "ended_by": "offline"})
                clock += timedelta(minutes=gone + rng.uniform(40, 90))
                continue
            if wait > PATIENCE_MIN:  # patience ran out: relocate (censored)
                spells.append({**base, "end": _iso(clock + timedelta(minutes=PATIENCE_MIN)), "ended_by": "moved"})
                clock += timedelta(minutes=PATIENCE_MIN)
                zone = rng.choices([n for n in names if n != zone], weights=[ZONES[n][5] for n in names if n != zone])[0]
                continue
            spells.append({**base, "end": _iso(clock + timedelta(minutes=wait)), "ended_by": "trip"})
            clock += timedelta(minutes=wait)
            km, net, dur = draw_trip(rng, zone, rain)
            tid += 1
            trips.append({
                "trip_id": f"t{tid:04d}", "started_at": _iso(clock), "pickup_lat": lat, "pickup_lng": lng,
                "net_vnd": round(net), "duration_min": round(dur, 1), "distance_km": round(km, 2),
            })
            clock += timedelta(minutes=dur)
            zone = rng.choices([n for n in names if n != zone], weights=[ZONES[n][5] for n in names if n != zone])[0]
    return {"trip_log": trips, "wait_spells": spells, "driver_profile": dict(PROFILE), "generated_at": _iso(now),
            "_truth": {"zones": {k: list(v) for k, v in ZONES.items()}, "note": "synthetic ground truth, never read by the engine"}}
