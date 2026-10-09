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
    DriverProfile,
    EngineInput,
    ObjectiveKey,
    ObjectiveStatus,
    PoiCandidate,
    RoutingSample,
    TrafficEdge,
    TripRecord,
    WaitSpell,
    WeatherHour,
)

# Fields whose meaning is defined by the ride platform and cannot be verified from the driver's side (no API, no
# audit trail; "net" depends on commission/bonus/surge/vehicle type; scales like demand_index are the platform's own).
# They are NEVER read by the engine: the adapter removes them and reports how many it removed.
UNRELIABLE_MARKET_FIELDS = frozenset({
    "gross_fare_vnd", "net_value_vnd", "avg_duration_min", "avg_trip_distance_km", "long_trip_rate_pct",
    "demand_index", "booking_rate", "request_count", "vehicle_density", "dropoff_count",
    "favorable_dropoff_pct", "avg_next_wait_min",
})
_WAIT_END = ("trip", "offline", "moved")


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


def _strip_unreliable(block: Any) -> tuple[dict[str, Any] | None, int]:
    """Remove platform-defined fields from a trip_value / destination_distribution block.

    Returns (remaining block or None when nothing usable is left, number of fields removed)."""
    if not isinstance(block, dict):
        return None, 0
    removed = [k for k in block if k in UNRELIABLE_MARKET_FIELDS]
    kept = {k: v for k, v in block.items() if k not in UNRELIABLE_MARKET_FIELDS and k != "hotspot_features"}
    return (kept or None), len(removed)


def parse_areas(areas_raw: list[dict[str, Any]], dropped: list[int] | None = None) -> list[AreaSample]:
    """Parse areas array into AreaSample instances. `dropped[0]` accumulates how many unreliable fields were removed."""
    areas: list[AreaSample] = []
    for a in areas_raw:
        trip_value, n1 = _strip_unreliable(a.get("trip_value"))
        dest, n2 = _strip_unreliable(a.get("destination_distribution"))
        if dropped is not None:
            dropped[0] += n1 + n2
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
                trip_value=trip_value,
                destination_distribution=dest,
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
            dist = t.get("distance_km")
            dist = None if dist is None else float(dist)
            if dist is not None and (dist != dist or dist <= 0):
                dist = None  # an impossible distance is dropped (the trip itself stays), never defaulted
        except (KeyError, TypeError, ValueError):
            rejected += 1
            continue
        trips.append(TripRecord(
            trip_id=str(t.get("trip_id", f"trip_{i}")), started_at=str(t["started_at"]),
            pickup_lat=lat, pickup_lng=lng, net_vnd=net, duration_min=dur,
            dropoff_lat=d_lat, dropoff_lng=d_lng, distance_km=dist,
        ))
    return trips, rejected


def _positive(raw: dict[str, Any], key: str, allow_zero: bool = False) -> float | None:
    try:
        v = float(raw[key])
    except (KeyError, TypeError, ValueError):
        return None
    if v != v or v in (float("inf"), float("-inf")) or v < 0 or (v == 0 and not allow_zero):
        return None
    return v


def parse_driver_profile(raw: Any) -> tuple[DriverProfile | None, list[str]]:
    """The driver's own tariff/vehicle/goal. Invalid fields become None and are reported; nothing is defaulted."""
    if not isinstance(raw, dict):
        return None, []
    fields = {
        "fare_base_vnd": _positive(raw, "fare_base_vnd", allow_zero=True),
        "fare_per_km_vnd": _positive(raw, "fare_per_km_vnd"),
        "fuel_l_per_100km": _positive(raw, "fuel_l_per_100km"),
        "fuel_price_vnd_per_l": _positive(raw, "fuel_price_vnd_per_l"),
        "target_vnd_per_hour": _positive(raw, "target_vnd_per_hour"),
    }
    bad = [k for k in fields if k in raw and raw[k] is not None and fields[k] is None]
    if all(v is None for v in fields.values()):
        return None, bad
    return DriverProfile(**fields), bad


def parse_wait_spells(raw: Any) -> tuple[list[WaitSpell], int]:
    """Companion-app wait spells. A spell without times, position or a valid end reason is REJECTED and counted."""
    if not isinstance(raw, list):
        return [], 0
    spells: list[WaitSpell] = []
    rejected = 0
    for i, w in enumerate(raw):
        try:
            if not isinstance(w, dict) or not w.get("start") or not w.get("end") or w.get("ended_by") not in _WAIT_END:
                raise ValueError("fields")
            lat, lng = float(w["lat"]), float(w["lng"])
            if not (-90 <= lat <= 90 and -180 <= lng <= 180):
                raise ValueError("range")
        except (KeyError, TypeError, ValueError):
            rejected += 1
            continue
        rain = w.get("rain_mm")
        try:
            rain = None if rain is None else float(rain)
        except (TypeError, ValueError):
            rain = None
        if rain is not None and (rain != rain or rain < 0):
            rain = None  # an impossible rain value is dropped (the spell itself stays), never defaulted
        spells.append(WaitSpell(
            spell_id=str(w.get("spell_id", f"wait_{i}")), start=str(w["start"]), end=str(w["end"]),
            lat=lat, lng=lng, ended_by=w["ended_by"], rain_mm=rain,
        ))
    return spells, rejected


def load_engine_input_from_dict(
    payload: dict[str, Any],
    fallback_pois: list[PoiCandidate] | None = None,
) -> EngineInput:
    """Transform a snapshot payload dictionary into typed EngineInput."""
    data_status = normalize_data_status(payload.get("data_status", []))
    objective_readiness = normalize_objective_readiness(payload.get("objective_readiness", []))

    dropped_fields = [0]
    areas = parse_areas(payload.get("areas", []), dropped_fields)

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

    wait_spells, rejected_spells = parse_wait_spells(payload.get("wait_spells"))
    if rejected_spells:
        adapter_notes.append(f"Bỏ {rejected_spells} đợt chờ thiếu/sai trường bắt buộc (không tự điền giá trị)")
    driver_profile, bad_profile = parse_driver_profile(payload.get("driver_profile"))
    if bad_profile:
        adapter_notes.append(f"Bỏ giá trị không hợp lệ trong hồ sơ tài xế: {', '.join(bad_profile)} (không tự điền giá trị)")
    if dropped_fields[0]:
        adapter_notes.append(
            f"Bỏ {dropped_fields[0]} trường thị trường do sàn định nghĩa (cước gộp/ròng khu vực, chỉ số cầu, tỷ lệ cuốc xa, "
            "tỷ lệ trả khách thuận lợi, thời gian chờ khu vực…) vì không kiểm chứng được — engine chỉ dùng số liệu do tài xế tự cung cấp"
        )

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
        driver_profile=driver_profile,
        wait_spells=wait_spells,
    )



def load_engine_input_from_file(file_path: str | Path) -> EngineInput:
    """Load and parse an engine input snapshot from a JSON file."""
    path = Path(file_path)
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    return load_engine_input_from_dict(payload)
