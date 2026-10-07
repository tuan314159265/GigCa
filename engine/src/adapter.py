"""Snapshot Adapter — converts data snapshot JSONs into typed EngineInput.

Handles both raw arrays (from contracts/engine_input.schema.json)
and normalized structures expected by the Decision Engine.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from engine.src.types import (
    AreaSample,
    DataStatusValue,
    EngineInput,
    ObjectiveKey,
    ObjectiveStatus,
    PoiCandidate,
    RoutingSample,
    TrafficEdge,
    TripRecord,
    WeatherHour,
)


def normalize_data_status(raw_status: Any) -> dict[str, DataStatusValue]:
    """Normalize data_status from array of objects or direct mapping."""
    result: dict[str, DataStatusValue] = {}
    if isinstance(raw_status, list):
        for item in raw_status:
            if isinstance(item, dict) and "dataset" in item and "status" in item:
                result[item["dataset"]] = item["status"]
    elif isinstance(raw_status, dict):
        result = raw_status
    return result


def extract_status_reasons(raw_status: Any) -> dict[str, str]:
    """Keep the human-readable `reason` of each data_status entry (used to explain limits in assumptions)."""
    reasons: dict[str, str] = {}
    if isinstance(raw_status, list):
        for item in raw_status:
            if isinstance(item, dict) and item.get("dataset") and item.get("reason"):
                reasons[str(item["dataset"])] = str(item["reason"])
    return reasons


def normalize_objective_readiness(raw_readiness: Any) -> dict[ObjectiveKey, ObjectiveStatus]:
    """Normalize objective_readiness from array of objects or direct mapping."""
    result: dict[ObjectiveKey, ObjectiveStatus] = {}
    if isinstance(raw_readiness, list):
        for item in raw_readiness:
            if isinstance(item, dict) and "objective" in item and "status" in item:
                result[item["objective"]] = item["status"]
    elif isinstance(raw_readiness, dict):
        result = raw_readiness
    return result


def parse_weather_hours(hourly_raw: list[dict[str, Any]]) -> list[WeatherHour]:
    """Parse list of hourly forecast objects into WeatherHour dataclasses."""
    hours: list[WeatherHour] = []
    for h in hourly_raw:
        hours.append(
            WeatherHour(
                valid_time=str(h.get("valid_time", "")),
                precipitation_mm=h.get("precipitation_mm"),
                precipitation_probability_pct=h.get("precipitation_probability_pct"),
            )
        )
    return hours


def parse_routing_samples(routing_raw: list[dict[str, Any]]) -> list[RoutingSample]:
    """Parse raw routing sample objects."""
    routes: list[RoutingSample] = []
    for r in routing_raw:
        routes.append(
            RoutingSample(
                destination_id=str(r.get("destination_id", "")),
                profile=str(r.get("profile", "driving")),
                route_distance_m=r.get("route_distance_m"),
                route_duration_s=r.get("route_duration_s"),
            )
        )
    return routes


def parse_areas(areas_raw: list[dict[str, Any]]) -> list[AreaSample]:
    """Parse areas array into AreaSample instances."""
    areas: list[AreaSample] = []
    for a in areas_raw:
        weather_raw = a.get("weather", {}).get("hourly", [])
        weather_hours = parse_weather_hours(weather_raw)
        routing_samples = parse_routing_samples(a.get("routing_samples", []))
        areas.append(
            AreaSample(
                area_id=str(a.get("area_id", "")),
                spatial_scope=str(a.get("spatial_scope", "point_sample")),
                representative_point=a.get("representative_point", {}),
                area_name=a.get("area_name"),
                poi_counts_by_category=a.get("poi_counts_by_category", {}),
                routing_samples=routing_samples,
                weather_hourly=weather_hours,
                trip_value=a.get("trip_value"),
                destination_distribution=a.get("destination_distribution"),
                traffic_feed=a.get("traffic"),
            )
        )
    return areas


def parse_trip_log(raw: Any) -> tuple[list[TripRecord], int]:
    """Parse the driver's own trip log. A trip missing any required field is REJECTED and counted, never defaulted."""
    if not isinstance(raw, list):
        return [], 0
    trips: list[TripRecord] = []
    rejected = 0
    for i, t in enumerate(raw):
        try:
            if not isinstance(t, dict) or not t.get("started_at"):
                raise ValueError("started_at")
            lat, lng = float(t["pickup_lat"]), float(t["pickup_lng"])
            net, dur = float(t["net_vnd"]), float(t["duration_min"])
            if not (-90 <= lat <= 90 and -180 <= lng <= 180) or net < 0 or dur <= 0 or net != net or dur != dur:
                raise ValueError("range")
            d_lat, d_lng = t.get("dropoff_lat"), t.get("dropoff_lng")
            if d_lat is not None and d_lng is not None:
                d_lat, d_lng = float(d_lat), float(d_lng)
                if not (-90 <= d_lat <= 90 and -180 <= d_lng <= 180):
                    d_lat = d_lng = None
            else:
                d_lat = d_lng = None
        except (KeyError, TypeError, ValueError):
            rejected += 1
            continue
        trips.append(TripRecord(
            trip_id=str(t.get("trip_id", f"trip_{i}")), started_at=str(t["started_at"]),
            pickup_lat=lat, pickup_lng=lng, net_vnd=net, duration_min=dur,
            dropoff_lat=d_lat, dropoff_lng=d_lng,
        ))
    return trips, rejected


def load_engine_input_from_dict(
    payload: dict[str, Any],
    fallback_pois: list[PoiCandidate] | None = None,
) -> EngineInput:
    """Transform a snapshot payload dictionary into typed EngineInput."""
    data_status = normalize_data_status(payload.get("data_status", []))
    objective_readiness = normalize_objective_readiness(payload.get("objective_readiness", []))

    areas = parse_areas(payload.get("areas", []))

    # Weather: top-level only. Per-area weather stays on the area; the engine picks the sample nearest the driver
    # (and checks it is within scope) instead of silently borrowing the first area's forecast.
    weather_hourly: list[WeatherHour] = []
    if isinstance(payload.get("weather"), dict) and "hourly" in payload["weather"]:
        weather_hourly = parse_weather_hours(payload["weather"]["hourly"])

    adapter_notes: list[str] = []

    # POI candidates
    poi_candidates: list[PoiCandidate] = []
    if "pois" in payload and isinstance(payload["pois"], list):
        skipped = 0
        for p in payload["pois"]:
            try:
                lat, lng = float(p["latitude"]), float(p["longitude"])
            except (KeyError, TypeError, ValueError):
                skipped += 1  # a POI without coordinates must not be placed at (0, 0)
                continue
            poi_candidates.append(
                PoiCandidate(
                    poi_id=str(p.get("osm_id", p.get("poi_id", ""))),
                    name=p.get("name", "Unknown POI"),
                    latitude=lat,
                    longitude=lng,
                    category=p.get("category", "amenity"),
                    subcategory=p.get("subcategory"),
                    verified=bool(p.get("verified", False)),
                    parking_allowed=bool(p.get("parking_allowed", False)),
                    opening_hours=p.get("opening_hours"),
                    tags=p.get("tags", {}),
                )
            )
        if skipped:
            adapter_notes.append(f"Bỏ {skipped} POI thiếu tọa độ hợp lệ")
    else:
        # No implicit mock POIs: an absent POI list stays empty. Callers that want fixtures must pass them explicitly.
        poi_candidates = list(fallback_pois) if fallback_pois is not None else []

    # Traffic edges
    traffic_edges: list[TrafficEdge] = []
    if "traffic" in payload and isinstance(payload["traffic"], list):
        for t in payload["traffic"]:
            traffic_edges.append(
                TrafficEdge(
                    edge_id=str(t.get("edge_id", "")),
                    from_node=t.get("from_node"),
                    to_node=t.get("to_node"),
                    length_m=t.get("length_m"),
                    current_speed_kmh=t.get("current_speed_kmh"),
                    free_flow_speed_kmh=t.get("free_flow_speed_kmh"),
                    congestion_level=t.get("congestion_level"),
                    observed_at=t.get("observed_at"),
                )
            )

    trip_log, rejected = parse_trip_log(payload.get("trip_log"))
    if rejected:
        adapter_notes.append(f"Bỏ {rejected} chuyến trong nhật ký thiếu/sai trường bắt buộc (không tự điền giá trị)")

    reasons = extract_status_reasons(payload.get("data_status", []))
    if adapter_notes:
        reasons["adapter"] = "; ".join(adapter_notes)
    label = payload.get("simulation_label")
    marker = f"{payload.get('schema_version', '')} {payload.get('snapshot_id', '')}".lower()
    is_demo = bool(label) or "demo" in marker or "simulat" in marker

    return EngineInput(
        weather_hourly=weather_hourly,
        areas=areas,
        traffic=traffic_edges,
        data_status=data_status,
        objective_readiness=objective_readiness,
        poi_candidates=poi_candidates,
        snapshot_id=str(payload.get("snapshot_id", "unnamed_snapshot")),
        generated_at=str(payload.get("generated_at", "")),
        data_label=str(label) if label else None,
        is_demo=is_demo,
        data_status_reasons=reasons,
        trip_log=trip_log,
    )



def load_engine_input_from_file(file_path: str | Path) -> EngineInput:
    """Load and parse an engine input snapshot from a JSON file."""
    path = Path(file_path)
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    return load_engine_input_from_dict(payload)
