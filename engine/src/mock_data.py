"""Mock and synthetic data for Decision Engine.

Provides temporary realistic fixtures (POIs, routing samples, weather, areas)
to run the engine end-to-end until complete verified feeds are integrated.
"""

from __future__ import annotations

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
        data_label="mock_data — dữ liệu giả lập cho test/demo",
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
