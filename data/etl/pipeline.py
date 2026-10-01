#!/usr/bin/env python3
"""Build a normalized Decision Engine snapshot from the checked-in samples."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SAMPLES_DIR = ROOT / "data" / "samples"
DEFAULT_OUTPUT = ROOT / "data" / "processed" / "engine_input_snapshot.json"
SAMPLE_FILES = {
    "weather": "open_meteo_weather_hcmc.json",
    "poi": "osm_overpass_pois_hcmc.json",
    "routing": "osrm_route_hcmc.json",
}


class PipelineError(RuntimeError):
    """Raised when an input sample cannot safely be normalized."""


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PipelineError(f"Missing source sample: {path}") from exc
    except json.JSONDecodeError as exc:
        raise PipelineError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise PipelineError(f"Expected a JSON object in {path}")
    return value


def require_dataset_id(dataset: dict[str, Any], path: Path) -> str:
    dataset_id = dataset.get("dataset_id")
    if not isinstance(dataset_id, str) or not dataset_id:
        raise PipelineError(f"{path} is missing a non-empty dataset_id")
    return dataset_id


def validate_weather(dataset: dict[str, Any], path: Path) -> list[dict[str, Any]]:
    observations = dataset.get("hourly")
    if not isinstance(observations, list) or not observations:
        raise PipelineError(f"{path} must contain a non-empty hourly array")
    for index, item in enumerate(observations):
        if not isinstance(item, dict) or not isinstance(item.get("valid_time"), str):
            raise PipelineError(f"{path}: hourly[{index}] needs a valid_time string")
        probability = item.get("precipitation_probability_pct")
        if probability is not None and (
            not isinstance(probability, (int, float)) or not 0 <= probability <= 100
        ):
            raise PipelineError(f"{path}: hourly[{index}] probability must be between 0 and 100")
        amount = item.get("precipitation_mm")
        if amount is not None and (
            not isinstance(amount, (int, float)) or amount < 0
        ):
            raise PipelineError(f"{path}: hourly[{index}] precipitation_mm must be non-negative")
    return observations


def validate_pois(dataset: dict[str, Any], path: Path) -> list[dict[str, Any]]:
    pois = dataset.get("pois")
    if not isinstance(pois, list):
        raise PipelineError(f"{path} must contain a pois array")
    for index, poi in enumerate(pois):
        if not isinstance(poi, dict):
            raise PipelineError(f"{path}: pois[{index}] must be an object")
        for coordinate in ("latitude", "longitude"):
            if not isinstance(poi.get(coordinate), (int, float)):
                raise PipelineError(f"{path}: pois[{index}] is missing numeric {coordinate}")
        if not isinstance(poi.get("category"), str):
            raise PipelineError(f"{path}: pois[{index}] is missing category")
    return pois


def extract_route(dataset: dict[str, Any], path: Path) -> dict[str, Any]:
    response = dataset.get("response")
    if not isinstance(response, dict) or response.get("code") != "Ok":
        raise PipelineError(f"{path} does not contain a successful route response")
    routes = response.get("routes")
    if not isinstance(routes, list) or not routes or not isinstance(routes[0], dict):
        raise PipelineError(f"{path} must contain at least one route")
    request = dataset.get("request")
    if not isinstance(request, dict) or not isinstance(request.get("destination"), dict):
        raise PipelineError(f"{path} is missing request.destination")
    return routes[0]


def sample_age_status(
    valid_times: list[dict[str, Any]], timezone_name: str | None
) -> tuple[str, str]:
    tz = ZoneInfo(timezone_name or "Asia/Ho_Chi_Minh")
    parsed: list[datetime] = []
    for item in valid_times:
        value = datetime.fromisoformat(item["valid_time"])
        if value.tzinfo is None:
            value = value.replace(tzinfo=tz)
        parsed.append(value)
    if not parsed:
        return "missing", "No valid forecast timestamps were provided."
    now = datetime.now(timezone.utc)
    latest = max(parsed).astimezone(timezone.utc)
    if latest < now:
        return "stale", f"Forecast sample expired at {latest.isoformat()}; refresh before live recommendations."
    return "partial", "Forecast is available for one provider grid near the sample point, not area-wide."


def build_engine_input(samples_dir: Path) -> dict[str, Any]:
    paths = {name: samples_dir / filename for name, filename in SAMPLE_FILES.items()}
    datasets = {name: load_json(path) for name, path in paths.items()}
    dataset_ids = {
        name: require_dataset_id(data, paths[name]) for name, data in datasets.items()
    }

    weather = datasets["weather"]
    pois = datasets["poi"]
    routing = datasets["routing"]
    hourly = validate_weather(weather, paths["weather"])
    poi_items = validate_pois(pois, paths["poi"])
    route = extract_route(routing, paths["routing"])

    location = weather.get("requested_location")
    if not isinstance(location, dict):
        raise PipelineError(f"{paths['weather']} is missing requested_location")
    latitude, longitude = location.get("latitude"), location.get("longitude")
    if not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float)):
        raise PipelineError(f"{paths['weather']} requested_location needs numeric coordinates")

    weather_source = weather.get("source", {})
    weather_status, weather_reason = sample_age_status(
        hourly, weather_source.get("timezone") if isinstance(weather_source, dict) else None
    )
    poi_counts = dict(Counter(item["category"] for item in poi_items))
    route_request = routing["request"]
    route_source = routing.get("source", {})
    route_profile = route_request.get("profile", route_source.get("profile", "unknown"))
    generated = [
        data["generated_at"]
        for data in datasets.values()
        if isinstance(data.get("generated_at"), str)
    ]
    source_date = max(generated)[:10] if generated else "unknown"

    data_status = [
        {
            "dataset": "weather",
            "status": weather_status,
            "reason": weather_reason,
            "source_dataset_id": dataset_ids["weather"],
        },
        {
            "dataset": "poi",
            "status": "partial",
            "reason": "POIs cover one search radius; their presence does not verify legal or suitable waiting/parking.",
            "source_dataset_id": dataset_ids["poi"],
        },
        {
            "dataset": "routing",
            "status": "partial",
            "reason": f"One {route_profile} route is available; motorcycle suitability and live traffic are unverified.",
            "source_dataset_id": dataset_ids["routing"],
        },
        {"dataset": "traffic", "status": "missing", "reason": "No traffic feed has passed provider and live-response verification."},
        {"dataset": "road_incidents", "status": "missing", "reason": "No incident/closure feed has been verified."},
        {"dataset": "verified_waiting_places", "status": "missing", "reason": "POIs are candidates only; legality and suitability are not verified."},
        {"dataset": "events", "status": "missing", "reason": "No event source has been verified."},
        {"dataset": "vehicle_density", "status": "missing", "reason": "No licensed vehicle-supply feed is available."},
        {"dataset": "booking_and_destinations", "status": "missing", "reason": "No booking-rate or destination data is available."},
        {"dataset": "trip_value", "status": "missing", "reason": "No licensed fare/trip-value data is available."},
    ]

    safety_status = "partial" if weather_status == "partial" else "insufficient_data"
    safety_reason = (
        "Rain forecast is available only for one sample point; traffic and incident feeds are missing, "
        "so this is only a partial rain-related safety assessment."
        if safety_status == "partial"
        else f"{weather_reason} Traffic and incident feeds are also missing, so broader safety ranking is incomplete."
    )
    return {
        "schema_version": "0.1",
        "snapshot_id": f"hcmc_demo_point_01_etl_{source_date}",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_dataset_ids": list(dataset_ids.values()),
        "data_status": data_status,
        "objective_readiness": [
            {
                "objective": "max_trip_value",
                "status": "insufficient_data",
                "blocking_datasets": ["booking_and_destinations", "trip_value"],
                "reason": "No booking, destination, or fare data is available.",
            },
            {
                "objective": "maintain_position",
                "status": "insufficient_data",
                "blocking_datasets": ["booking_and_destinations"],
                "reason": "A single route does not estimate passenger drop-off or next-trip opportunity.",
            },
            {
                "objective": "rest_spot",
                "status": "partial",
                "blocking_datasets": ["verified_waiting_places"],
                "reason": "POIs are unverified candidates, not confirmed places to stop or park.",
            },
            {
                "objective": "safety_comfort",
                "status": safety_status,
                "blocking_datasets": ["traffic", "road_incidents"]
                + (["weather"] if weather_status == "stale" else []),
                "reason": safety_reason,
            },
        ],
        "areas": [
            {
                "area_id": "hcmc_demo_point_01",
                "spatial_scope": "point_sample",
                "representative_point": {"latitude": latitude, "longitude": longitude},
                "weather": {
                    "provider_grid_location": weather_source.get(
                        "provider_location",
                        {"latitude": latitude, "longitude": longitude, "elevation_m": None},
                    ),
                    "hourly": hourly,
                },
                "poi_counts_by_category": poi_counts,
                "routing_samples": [
                    {
                        "destination_id": "sample_destination_01",
                        "profile": route_profile,
                        "route_distance_m": route.get("distance"),
                        "route_duration_s": route.get("duration"),
                    }
                ],
            }
        ],
        "limitations": [
            "This ETL run transforms checked-in samples; it does not fetch live data.",
            f"Samples were collected at {source_date}; verify each data_status before use.",
            "Coverage is one point and a POI search radius, not a city-wide grid.",
            "OSRM driving route duration is not live traffic or verified motorcycle travel time.",
            "POI counts do not imply passenger demand, waiting legality, or trip probability.",
            "Unverified providers are not silently substituted; fallback requires comparable fields and coverage.",
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples-dir", type=Path, default=DEFAULT_SAMPLES_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--refresh-weather",
        action="store_true",
        help="Fetch a fresh Open-Meteo forecast before transforming samples",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.refresh_weather:
            from data.etl.extractors.open_meteo import fetch_weather_sample

            weather_path = fetch_weather_sample(args.samples_dir)
            print(f"Weather sample refreshed: {weather_path}")
        snapshot = build_engine_input(args.samples_dir)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"ETL failed: {exc}", file=sys.stderr)
        return 1
    print(f"Engine input written: {args.output}")
    for status in snapshot["data_status"]:
        print(f"- {status['dataset']}: {status['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
