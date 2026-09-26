#!/usr/bin/env python3
"""Fetch small weather, POI, and routing samples into separate JSON files."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from collections import Counter
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "data" / "samples" / "hcmc_demo_snapshot.json"
DEFAULT_SAMPLES_DIR = ROOT / "data" / "samples"
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OSRM_URL = "https://router.project-osrm.org/route/v1/driving"
USER_AGENT = "GigCaDataProbe/0.1 (sample data; https://github.com/tuan314159265/GigCa)"
WEATHER_FIELDS = (
    "precipitation,precipitation_probability,apparent_temperature,"
    "shortwave_radiation,wind_speed_10m,wind_gusts_10m,weather_code"
)


def fetch_json(url: str, *, body: bytes | None = None, timeout: int = 60) -> dict[str, Any]:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded; charset=utf-8"
    request = Request(url, data=body, headers=headers)
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = response.read()
    except HTTPError as exc:
        detail = exc.read(500).decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} from {url}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Network error from {url}: {exc.reason}") from exc
    try:
        decoded = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Provider returned invalid JSON from {url}") from exc
    if not isinstance(decoded, dict):
        raise RuntimeError(f"Expected a JSON object from {url}")
    return decoded


def fetch_weather(lat: float, lon: float) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    params = urlencode(
        {
            "latitude": lat,
            "longitude": lon,
            "hourly": WEATHER_FIELDS,
            "forecast_days": 2,
            "timezone": "Asia/Ho_Chi_Minh",
            "temperature_unit": "celsius",
            "wind_speed_unit": "kmh",
            "precipitation_unit": "mm",
        }
    )
    response = fetch_json(f"{OPEN_METEO_URL}?{params}")
    hourly = response.get("hourly")
    if not isinstance(hourly, dict) or not isinstance(hourly.get("time"), list):
        raise RuntimeError("Open-Meteo response is missing hourly.time")

    source_names = {
        "precipitation": "precipitation_mm",
        "precipitation_probability": "precipitation_probability_pct",
        "apparent_temperature": "apparent_temperature_c",
        "shortwave_radiation": "shortwave_radiation_w_m2",
        "wind_speed_10m": "wind_speed_10m_kmh",
        "wind_gusts_10m": "wind_gusts_10m_kmh",
        "weather_code": "weather_code_wmo",
    }
    observations: list[dict[str, Any]] = []
    for index, valid_time in enumerate(hourly["time"]):
        observation: dict[str, Any] = {"valid_time": valid_time}
        for provider_field, normalized_field in source_names.items():
            values = hourly.get(provider_field)
            observation[normalized_field] = (
                values[index]
                if isinstance(values, list) and index < len(values)
                else None
            )
        observations.append(observation)

    metadata = {
        "provider": "Open-Meteo",
        "endpoint": OPEN_METEO_URL,
        "documentation": "https://open-meteo.com/en/docs",
        "license": "CC BY 4.0; free API terms restrict the free service to non-commercial use",
        "attribution": "Weather data by Open-Meteo.com",
        "timezone": response.get("timezone"),
        "provider_location": {
            "latitude": response.get("latitude"),
            "longitude": response.get("longitude"),
            "elevation_m": response.get("elevation"),
        },
        "hourly_units": response.get("hourly_units", {}),
    }
    return metadata, observations


def build_overpass_query(lat: float, lon: float, radius_m: int) -> str:
    filters = (
        '["amenity"~"^(cafe|restaurant|fast_food|food_court|toilets|bench|'
        'shelter|parking|fuel|bus_station)$"]',
        '["shop"~"^(convenience|supermarket|mall)$"]',
        '["public_transport"~"^(platform|station)$"]',
    )
    lines = ["[out:json][timeout:45];", "("]
    for object_type in ("node", "way", "relation"):
        for tag_filter in filters:
            lines.append(
                f"  {object_type}(around:{radius_m},{lat},{lon}){tag_filter};"
            )
    lines.extend((");", "out center tags;"))
    return "\n".join(lines)


def fetch_pois(lat: float, lon: float, radius_m: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    query = build_overpass_query(lat, lon, radius_m)
    body = urlencode({"data": query}).encode("utf-8")
    response = fetch_json(OVERPASS_URL, body=body)
    elements = response.get("elements")
    if not isinstance(elements, list):
        raise RuntimeError("Overpass response is missing elements")

    pois: list[dict[str, Any]] = []
    for element in elements:
        tags = element.get("tags") or {}
        if element.get("type") == "node":
            point = element
            point_method = "node_coordinate"
        else:
            point = element.get("center") or {}
            point_method = "osm_bbox_center_approximation"
        if point.get("lat") is None or point.get("lon") is None:
            continue

        tagged_category = next(
            (key for key in ("amenity", "shop", "public_transport") if key in tags),
            "other",
        )
        pois.append(
            {
                "osm_type": element.get("type"),
                "osm_id": element.get("id"),
                "name": tags.get("name"),
                "latitude": point["lat"],
                "longitude": point["lon"],
                "point_method": point_method,
                "category": tagged_category,
                "subcategory": tags.get(tagged_category),
                "tags": tags,
            }
        )

    metadata = {
        "provider": "OpenStreetMap via Overpass API",
        "endpoint": OVERPASS_URL,
        "documentation": "https://wiki.openstreetmap.org/wiki/Overpass_API/Language_Guide",
        "license": "Open Database License (ODbL) 1.0",
        "attribution": "© OpenStreetMap contributors",
        "query": query,
        "result_count": len(pois),
        "point_note": "Way/relation coordinates use the bounding-box center and are approximate, not entrances or legal stopping locations.",
    }
    return metadata, pois


def fetch_route(
    origin_lat: float,
    origin_lon: float,
    destination_lat: float,
    destination_lon: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    coordinates = f"{origin_lon},{origin_lat};{destination_lon},{destination_lat}"
    params = urlencode({"overview": "full", "geometries": "geojson", "steps": "false"})
    endpoint = f"{OSRM_URL}/{coordinates}?{params}"
    response = fetch_json(endpoint)
    if response.get("code") != "Ok":
        raise RuntimeError(f"OSRM could not route sample coordinates: {response.get('code')}")
    metadata = {
        "provider": "OSRM public demo server",
        "endpoint": endpoint,
        "documentation": "https://project-osrm.org/docs/v5.24.0/api/",
        "profile": "driving",
        "license": "OSRM software is open source; route data is based on OpenStreetMap. Verify server and data terms before reuse.",
        "attribution": "© OpenStreetMap contributors",
    }
    return metadata, response


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lat", type=float, default=10.7769, help="Sample center latitude (default: central Ho Chi Minh City)")
    parser.add_argument("--lon", type=float, default=106.7009, help="Sample center longitude (default: central Ho Chi Minh City)")
    parser.add_argument("--radius-m", type=int, default=1000, help="OSM POI search radius in meters (default: 1000; max: 5000)")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output JSON path")
    parser.add_argument("--samples-dir", type=Path, default=DEFAULT_SAMPLES_DIR, help="Directory for per-source JSON files")
    args = parser.parse_args()
    if not -90 <= args.lat <= 90:
        parser.error("--lat must be between -90 and 90")
    if not -180 <= args.lon <= 180:
        parser.error("--lon must be between -180 and 180")
    if not 100 <= args.radius_m <= 5000:
        parser.error("--radius-m must be between 100 and 5000")
    return args


def main() -> int:
    args = parse_args()
    collected_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        weather_source, weather = fetch_weather(args.lat, args.lon)
        poi_source, pois = fetch_pois(args.lat, args.lon, args.radius_m)
        route_source, route_response = fetch_route(
            args.lat,
            args.lon,
            10.7796,
            106.6932,
        )
    except RuntimeError as exc:
        print(f"Fetch failed; no snapshot written: {exc}", file=sys.stderr)
        return 1

    dataset = {
        "schema_version": "1.0",
        "dataset_id": "gigca_hcmc_demo_weather_poi",
        "generated_at": collected_at,
        "location": {"latitude": args.lat, "longitude": args.lon},
        "coverage": {"poi_radius_m": args.radius_m},
        "sources": [weather_source, poi_source],
        "weather": {"hourly": weather},
        "pois": pois,
        "limitations": [
            "Sample coverage is limited to one coordinate and a small POI radius.",
            "Weather values are provider forecasts, not guaranteed observations at every street.",
            "POI presence does not establish permission to stop or park and is not trip demand.",
            "No road traffic, vehicle density, booking probability, or fare data is included.",
        ],
    }

    route_dataset = {
        "schema_version": "1.0",
        "dataset_id": "gigca_hcmc_demo_osrm_route",
        "generated_at": collected_at,
        "request": {
            "origin": {"latitude": args.lat, "longitude": args.lon},
            "destination": {"latitude": 10.7796, "longitude": 106.6932},
            "profile": "driving",
        },
        "source": route_source,
        "response": route_response,
        "limitations": [
            "This sample uses the public OSRM driving profile, not a verified motorcycle profile.",
            "Route duration is not live traffic and must not be treated as motorcycle navigation advice.",
        ],
    }
    weather_dataset = {
        "schema_version": "1.0",
        "dataset_id": "gigca_hcmc_demo_open_meteo_weather",
        "generated_at": collected_at,
        "requested_location": {"latitude": args.lat, "longitude": args.lon},
        "source": weather_source,
        "hourly": weather,
        "limitations": [
            "Forecast grid coordinates may differ from requested coordinates; see source.provider_location.",
            "Weather values are forecasts, not guaranteed observations at every street.",
        ],
    }
    poi_dataset = {
        "schema_version": "1.0",
        "dataset_id": "gigca_hcmc_demo_osm_pois",
        "generated_at": collected_at,
        "requested_location": {"latitude": args.lat, "longitude": args.lon},
        "coverage": {"radius_m": args.radius_m},
        "source": poi_source,
        "pois": pois,
        "limitations": [
            "POI presence does not establish permission to stop or park and is not trip demand.",
            "Way/relation coordinates may be bounding-box centers, not entrances.",
        ],
    }
    route = (route_response.get("routes") or [{}])[0]
    route_dataset_id = "gigca_hcmc_demo_osrm_route"
    engine_input_dataset = {
        "schema_version": "0.1",
        "snapshot_id": "hcmc_demo_point_01",
        "generated_at": collected_at,
        "source_dataset_ids": [
            "gigca_hcmc_demo_open_meteo_weather",
            "gigca_hcmc_demo_osm_pois",
            route_dataset_id,
        ],
        "data_status": [
            {
                "dataset": "weather",
                "status": "available",
                "reason": "Forecast sample is available for the provider grid near one requested point; it is not area-wide.",
                "source_dataset_id": "gigca_hcmc_demo_open_meteo_weather",
            },
            {
                "dataset": "poi",
                "status": "available",
                "reason": "OSM/Overpass POI sample is available within the requested radius; parking legality is not verified.",
                "source_dataset_id": "gigca_hcmc_demo_osm_pois",
            },
            {
                "dataset": "routing",
                "status": "partial",
                "reason": "Only one OSRM driving-profile route is sampled; no motorcycle routing graph has been verified.",
                "source_dataset_id": route_dataset_id,
            },
            {"dataset": "traffic", "status": "missing", "reason": "No road-segment traffic feed has been verified."},
            {"dataset": "road_incidents", "status": "missing", "reason": "No incident/closure feed has been verified."},
            {"dataset": "verified_waiting_places", "status": "missing", "reason": "POIs are not verified as legal or suitable places to wait or park."},
            {"dataset": "events", "status": "missing", "reason": "No event source has been verified."},
            {"dataset": "vehicle_density", "status": "missing", "reason": "No licensed vehicle-supply feed is available."},
            {"dataset": "booking_and_destinations", "status": "missing", "reason": "No booking-rate or destination-distribution data is available."},
            {"dataset": "trip_value", "status": "missing", "reason": "No licensed fare/trip-value data is available."},
        ],
        "objective_readiness": [
            {
                "objective": "max_trip_value",
                "status": "insufficient_data",
                "blocking_datasets": ["booking_and_destinations", "trip_value"],
                "reason": "No booking, destination, or fare data is available to rank expected trip value.",
            },
            {
                "objective": "maintain_position",
                "status": "insufficient_data",
                "blocking_datasets": ["booking_and_destinations"],
                "reason": "A single driving route does not estimate where a passenger may be dropped off or the next-trip opportunity.",
            },
            {
                "objective": "rest_spot",
                "status": "partial",
                "blocking_datasets": ["verified_waiting_places"],
                "reason": "POIs are available as candidates, but legal access and suitability for waiting are not verified.",
            },
            {
                "objective": "safety_comfort",
                "status": "partial",
                "blocking_datasets": ["traffic", "road_incidents"],
                "reason": "Weather is available only for a sample point; traffic and incident feeds are missing.",
            },
        ],
        "areas": [
            {
                "area_id": "hcmc_demo_point_01",
                "spatial_scope": "point_sample",
                "representative_point": {"latitude": args.lat, "longitude": args.lon},
                "weather": {
                    "provider_grid_location": weather_source["provider_location"],
                    "hourly": weather,
                },
                "poi_counts_by_category": dict(
                    Counter(poi["category"] for poi in pois)
                ),
                "routing_samples": [
                    {
                        "destination_id": "hcmc_demo_destination_01",
                        "profile": "driving",
                        "route_distance_m": route.get("distance"),
                        "route_duration_s": route.get("duration"),
                    }
                ],
            }
        ],
        "limitations": [
            "This is a point sample, not weather or POI aggregated to a real map cell/polygon.",
            "The OSRM route uses a driving profile and is only a schema example, not a verified motorcycle route.",
            "POI counts describe mapped features and do not estimate booking demand or legal stopping availability.",
            "No decision scores are included; the Decision Engine owns score formulas and weights.",
        ],
    }

    samples_dir = args.samples_dir.expanduser().resolve()
    samples_dir.mkdir(parents=True, exist_ok=True)
    datasets = {
        samples_dir / "open_meteo_weather_hcmc.json": weather_dataset,
        samples_dir / "osm_overpass_pois_hcmc.json": poi_dataset,
        samples_dir / "osrm_route_hcmc.json": route_dataset,
        samples_dir / "engine_input" / "hcmc_demo_snapshot.json": engine_input_dataset,
    }
    for path, content in datasets.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(content, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)

    output_path = args.output.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(dataset, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(output_path)
    for path in datasets:
        print(f"Wrote {path}")
    print(f"Wrote combined snapshot {output_path}")
    print(f"Weather hours: {len(weather)}; POIs: {len(pois)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
