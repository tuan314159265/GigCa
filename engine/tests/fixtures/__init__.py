"""UNIT-TEST INPUTS for the Decision Engine — not data.

Hand-set POIs, routing samples, weather hours and areas that exercise one branch of the logic each (a POI without a
routing sample, a rain hour above the tolerance, ...). They live under engine/tests/ on purpose: nothing in engine/src,
data/ or scripts/ imports them, they are never loaded into the database and never shown as results. Real runs use the
ETL snapshot (Open-Meteo / OSM / OSRM) plus the driver's own inputs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from engine.src.types import (
    AreaSample,
    DataStatusValue,
    DriverContext,
    DriverPreferences,
    EngineInput,
    ObjectiveKey,
    ObjectiveStatus,
    PoiCandidate,
    RoutingSample,
    WeatherHour,
)

MOCK_POI_CANDIDATES: list[PoiCandidate] = [
    PoiCandidate(
        poi_id="poi_highlands_01",
        name="Highlands Coffee Nhà Thờ Đức Bà",
        latitude=10.7798,
        longitude=106.6990,
        category="cafe",
        subcategory="coffee_shop",
        tags={"amenity": "cafe", "brand": "Highlands Coffee"},
    ),
    PoiCandidate(
        poi_id="poi_trung_nguyen_02",
        name="Cà phê Trung Nguyên Legend Lê Duẩn",
        latitude=10.7785,
        longitude=106.6980,
        category="cafe",
        subcategory="coffee_shop",
        tags={"amenity": "cafe", "brand": "Trung Nguyên"},
    ),
    PoiCandidate(
        poi_id="poi_petrolimex_03",
        name="Cây xăng Petrolimex Số 1 Nguyễn Thị Minh Khai",
        latitude=10.7810,
        longitude=106.7020,
        category="gas_station",
        subcategory="fuel",
        tags={"amenity": "fuel"},
    ),
    PoiCandidate(
        poi_id="poi_parking_23_9_04",
        name="Bãi giữ xe Công viên 23/9",
        latitude=10.7695,
        longitude=106.6935,
        category="parking",
        subcategory="motorcycle_parking",
        tags={"amenity": "parking"},
    ),
    PoiCandidate(
        poi_id="poi_toilet_taodan_05",
        name="Điểm vệ sinh công cộng Công viên Tao Đàn",
        latitude=10.7745,
        longitude=106.6920,
        category="toilet",
        subcategory="public_toilet",
        tags={"amenity": "toilets"},
    ),
    PoiCandidate(
        poi_id="poi_phuc_long_unrouted_06",
        name="Phúc Long Coffee & Tea Mạc Đĩnh Chi (Chưa có routing)",
        latitude=10.7850,
        longitude=106.7000,
        category="cafe",
        subcategory="coffee_shop",
        tags={"amenity": "cafe"},
    ),
]

MOCK_ROUTING_SAMPLES: list[RoutingSample] = [
    RoutingSample(
        destination_id="poi_highlands_01",
        profile="driving_sample",
        route_distance_m=510.0,
        route_duration_s=70.0,
    ),
    RoutingSample(
        destination_id="poi_trung_nguyen_02",
        profile="driving_sample",
        route_distance_m=620.0,
        route_duration_s=85.0,
    ),
    RoutingSample(
        destination_id="poi_petrolimex_03",
        profile="driving_sample",
        route_distance_m=850.0,
        route_duration_s=115.0,
    ),
    RoutingSample(
        destination_id="poi_toilet_taodan_05",
        profile="driving_sample",
        route_distance_m=1150.0,
        route_duration_s=160.0,
    ),
    RoutingSample(
        destination_id="poi_parking_23_9_04",
        profile="driving_sample",
        route_distance_m=1420.0,
        route_duration_s=190.0,
    ),
    # Note: poi_phuc_long_unrouted_06 intentionally has NO routing sample!
]

MOCK_WEATHER_HOURLY: list[WeatherHour] = [
    WeatherHour(valid_time="2026-09-27T14:00", precipitation_mm=0.0, precipitation_probability_pct=25.0),
    WeatherHour(valid_time="2026-09-27T15:00", precipitation_mm=0.2, precipitation_probability_pct=40.0),
    WeatherHour(valid_time="2026-09-27T16:00", precipitation_mm=1.5, precipitation_probability_pct=65.0),
    WeatherHour(valid_time="2026-09-27T17:00", precipitation_mm=2.8, precipitation_probability_pct=85.0),
    WeatherHour(valid_time="2026-09-27T18:00", precipitation_mm=3.2, precipitation_probability_pct=95.0),
    WeatherHour(valid_time="2026-09-27T19:00", precipitation_mm=0.8, precipitation_probability_pct=60.0),
]

MOCK_AREAS: list[AreaSample] = [
    AreaSample(
        area_id="area_q1_ben_nghe",
        spatial_scope="point_sample",
        representative_point={"latitude": 10.7769, "longitude": 106.7009},
        poi_counts_by_category={"amenity": 726, "public_transport": 116, "shop": 78},
        routing_samples=MOCK_ROUTING_SAMPLES,
        weather_hourly=MOCK_WEATHER_HOURLY,
    ),
    AreaSample(
        area_id="area_q3_vo_thi_sau",
        spatial_scope="point_sample",
        representative_point={"latitude": 10.7850, "longitude": 106.6920},
        poi_counts_by_category={"amenity": 512, "public_transport": 84, "shop": 65},
        routing_samples=[],
        weather_hourly=MOCK_WEATHER_HOURLY,
    ),
]

MOCK_DATA_STATUS: dict[str, DataStatusValue] = {
    "weather": "available",
    "poi": "available",
    "routing": "partial",
    "traffic": "missing",
    "road_incidents": "missing",
    "verified_waiting_places": "missing",
    "events": "missing",
    "vehicle_density": "missing",
    "booking_and_destinations": "missing",
    "trip_value": "missing",
}

MOCK_OBJECTIVE_READINESS: dict[ObjectiveKey, ObjectiveStatus] = {
    "max_trip_value": "insufficient_data",
    "maintain_position": "insufficient_data",
    "rest_spot": "partial",
    "safety_comfort": "partial",
}


def create_mock_engine_input(
    weather_hourly: list[WeatherHour] | None = None,
    areas: list[AreaSample] | None = None,
    poi_candidates: list[PoiCandidate] | None = None,
    data_status: dict[str, DataStatusValue] | None = None,
    objective_readiness: dict[ObjectiveKey, ObjectiveStatus] | None = None,
    snapshot_id: str = "hcmc_mock_snapshot_v1",
) -> EngineInput:
    """Create a fully-populated EngineInput using mock fixtures."""
    return EngineInput(
        weather_hourly=weather_hourly if weather_hourly is not None else list(MOCK_WEATHER_HOURLY),
        areas=areas if areas is not None else list(MOCK_AREAS),
        traffic=[],
        data_status=dict(data_status if data_status is not None else MOCK_DATA_STATUS),
        objective_readiness=dict(
            objective_readiness if objective_readiness is not None else MOCK_OBJECTIVE_READINESS
        ),
        poi_candidates=poi_candidates if poi_candidates is not None else list(MOCK_POI_CANDIDATES),
        snapshot_id=snapshot_id,
        generated_at="2026-09-27T14:00:00+07:00",
        data_label="đầu vào kiểm thử (unit test), không phải dữ liệu",
        is_demo=True,
    )


def create_default_driver_context(
    lat: float = 10.7769,
    lng: float = 106.7009,
    idle_min: int = 15,
    horizon_min: int = 180,
    max_reposition_km: float = 3.0,
) -> DriverContext:
    """Create default DriverContext around central HCMC."""
    return DriverContext(
        current_lat=lat,
        current_lng=lng,
        idle_duration_min=idle_min,
        horizon_min=horizon_min,
        max_reposition_km=max_reposition_km,
    )


def create_default_driver_preferences(
    rain_tolerance: str = "medium",
) -> DriverPreferences:
    """Create DriverPreferences."""
    return DriverPreferences(
        rain_tolerance_level=rain_tolerance,  # type: ignore[arg-type]
    )


SCENARIO_PATH = Path(__file__).resolve().parent / "unit_test_scenario.json"


# --------------------------------------------------------------------------- scenario + driver-log builders (TEST ONLY)
import json as _json
import random as _random
from datetime import datetime as _dt, timedelta as _td

from engine.src.personal_model import resolve_economics as _resolve_economics

TEST_NOW = _dt(2026, 9, 27, 14, 0)  # generated_at of unit_test_scenario.json (local time, UTC+7)
# Vehicle and goal of the hypothetical test driver; the tariff and share come from config (published tariff).
TEST_PROFILE = {"fuel_l_per_100km": 2.2, "fuel_price_vnd_per_l": 24000, "target_vnd_per_hour": 90000}
# zone: (lat, lng, mean trip km, mean speed km/h, mean wait min) — hand-set so each zone differs on one axis
TEST_ZONES = {
    "ben_thanh": (10.7725, 106.6980, 4.5, 20.0, 6.0),
    "tan_dinh": (10.7890, 106.6910, 3.5, 19.0, 9.0),
    "vo_thi_sau": (10.7830, 106.6960, 3.0, 18.0, 10.0),
    "hang_xanh": (10.8010, 106.7110, 8.0, 24.0, 18.0),
}
HANG_XANH = (10.801, 106.711)


def tariff_net(km: float, duration_min: float) -> float:
    """What the published tariff pays the driver for a trip (share x customer fare), per-minute part on the trip's own
    moving minutes after the base km (duration x (km - k0) / km)."""
    econ = _resolve_economics(None, [])
    mins_after = duration_min * max(0.0, km - econ.fare_base_km) / km
    return econ.driver_share * econ.gross_fare_vnd(km, mins_after)


def make_log(now: _dt = TEST_NOW, seed: int = 7, days: int = 12, per_day: int = 6, hour: int | None = None,
             minute: int = 30, zones: dict | None = None, with_waits: bool = False, noise_vnd: float = 1500.0):
    """Deterministic TEST log: trips paid by the published tariff (+/- noise_vnd) and the wait spells before each trip.

    Only for unit tests (it pins behaviour with inputs whose answer is known); never used by the engine or a demo."""
    zones = zones or TEST_ZONES
    hour = (now - _td(hours=1, minutes=30)).hour if hour is None else hour
    rng = _random.Random(seed)
    log: list[dict] = []
    spells: list[dict] = []
    for day in range(days):
        cur = (now - _td(days=days - day)).replace(hour=hour, minute=minute, second=0, microsecond=0)
        for i in range(per_day):
            la, lo, mean_km, speed, mean_wait = zones[rng.choice(sorted(zones))]
            wait = rng.expovariate(1.0 / mean_wait)
            la, lo = la + rng.uniform(-0.001, 0.001), lo + rng.uniform(-0.001, 0.001)
            spells.append({"spell_id": f"w{day}_{i}", "start": cur.isoformat(), "end": (cur + _td(minutes=wait)).isoformat(),
                           "lat": la, "lng": lo, "ended_by": "trip"})
            cur += _td(minutes=wait)
            km = mean_km * rng.uniform(0.8, 1.2)
            d = km / speed * 60.0
            log.append({
                "trip_id": f"t{day}_{i}", "started_at": cur.isoformat(), "pickup_lat": la, "pickup_lng": lo,
                "net_vnd": tariff_net(km, d) + rng.uniform(-noise_vnd, noise_vnd), "duration_min": d, "distance_km": km,
            })
            cur += _td(minutes=d)
    return (log, spells) if with_waits else log


def scenario_payload(now: _dt | None = None) -> dict:
    """The hand-set test scenario (weather/POI/routing/traffic), optionally re-dated to `now`. No driver data."""
    p = _json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    if now is not None:
        p["generated_at"] = now.isoformat() + "+07:00"
    return p


def full_scenario_payload(now: _dt = TEST_NOW, **log_kw) -> dict:
    """Scenario + test driver log + wait spells + profile: every lens has inputs."""
    p = scenario_payload(now if now != TEST_NOW else None)
    p["trip_log"], p["wait_spells"] = make_log(now=now, with_waits=True, **log_kw)
    p["driver_profile"] = dict(TEST_PROFILE)
    return p


def zone_id_near(payload: dict, lat: float, lng: float) -> str:
    """area_id of the log-derived zone whose representative point is closest to (lat, lng)."""
    from engine.src.adapter import load_engine_input_from_dict
    from engine.src.geo import haversine_m
    from engine.src.personal_model import build_personal_model
    from engine.src.timeutil import parse_local

    inp = load_engine_input_from_dict(payload)
    pm = build_personal_model(inp.trip_log, parse_local(inp.generated_at, 420), profile=inp.driver_profile,
                              spells=inp.wait_spells)
    best = min(pm.areas, key=lambda a: haversine_m(lat, lng, a.representative_point["latitude"],
                                                   a.representative_point["longitude"]))
    return best.area_id
