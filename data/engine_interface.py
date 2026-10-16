"""Read normalized PostGIS data as the versioned Decision Engine input contract.

Usage::

    from data.engine_interface import EngineDataInterface

    snapshot = EngineDataInterface.from_env().get_engine_input("hcmc_demo_point_01")

This adapter returns the existing ``contracts/engine_input.schema.json`` shape.
It does not score locations or infer passenger demand from POIs or traffic.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from data.db.connection import connect, database_url


class EngineDataInterface:
    """Query PostgreSQL and map rows to Engine input snapshot v0.1."""

    def __init__(self, url: str | None = None):
        self._url = database_url(url)

    @classmethod
    def from_env(cls) -> "EngineDataInterface":
        """Create an interface using ``GIGCA_DATABASE_URL``."""
        return cls()

    def get_engine_input(
        self,
        area_id: str,
        *,
        rain_tolerance_level: str | None = None,
        now: datetime | None = None,
        forecast_hours: int = 48,
    ) -> dict[str, Any]:
        """Return one Engine contract snapshot for ``area_id``.

        ``now`` is injectable for deterministic caller behavior. ``forecast_hours``
        limits valid forecast timestamps returned, while stale rows are still
        represented in data_status with an empty hourly list.
        """
        if rain_tolerance_level not in (None, "low", "medium", "high"):
            raise ValueError("rain_tolerance_level must be low, medium, high, or None")
        if not 1 <= forecast_hours <= 240:
            raise ValueError("forecast_hours must be between 1 and 240")
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        current = current.astimezone(timezone.utc)
        traffic_max_age = timedelta(minutes=30)  # Must match Engine TRAFFIC_CFG.max_age_min.

        with connect(self._url) as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT area_id, spatial_scope, timezone_name, source_dataset_id,
                          ST_Y(representative_point) AS latitude,
                          ST_X(representative_point) AS longitude,
                          ST_AsGeoJSON(coverage) AS coverage_geojson
                   FROM area WHERE area_id = %s""",
                (area_id,),
            )
            area = cursor.fetchone()
            if not area:
                raise KeyError(f"Unknown area_id: {area_id}")

            cursor.execute(
                """SELECT provider, source_dataset_id, issued_at, valid_at, fetched_at,
                          precipitation_probability_pct, precipitation_mm,
                          ST_Y(provider_location) AS latitude, ST_X(provider_location) AS longitude
                   FROM weather_forecast
                   WHERE area_id = %s
                   ORDER BY issued_at DESC, fetched_at DESC, valid_at ASC""",
                (area_id,),
            )
            weather_rows = cursor.fetchall()

            cursor.execute(
                """SELECT p.category, count(*)::integer AS feature_count,
                          array_agg(DISTINCT p.source_dataset_id) AS source_dataset_ids
                   FROM poi_feature p, area a
                   WHERE a.area_id = %s AND p.is_current
                     AND (a.coverage IS NULL OR ST_Intersects(a.coverage, p.geom))
                   GROUP BY p.category ORDER BY p.category""",
                (area_id,),
            )
            poi_count_rows = cursor.fetchall()
            poi_counts = {row["category"]: row["feature_count"] for row in poi_count_rows}
            poi_source_ids = list(dict.fromkeys(
                source_id for row in poi_count_rows for source_id in row["source_dataset_ids"]
            ))

            cursor.execute(
                """SELECT cell_id, row_number, column_number, cell_size_m, cell_area_km2,
                          cafe_poi_count, cafe_density_per_km2, cafe_poi_count_within_500m,
                          cafe_count_500m_status,
                          ST_Y(center) AS center_latitude, ST_X(center) AS center_longitude,
                          ST_AsGeoJSON(geom) AS geometry_geojson, source_dataset_id
                   FROM poi_grid_cell WHERE parent_area_id = %s ORDER BY row_number, column_number""",
                (area_id,),
            )
            grid_rows = cursor.fetchall()

            cursor.execute(
                """SELECT c.candidate_id, c.source_id, c.osm_type, c.osm_id, c.name, c.poi_type, c.role,
                          candidate_status, permission_to_wait, latitude, longitude, point_method,
                          area_m2, verification_needed, categories, address, tags, c.source_dataset_id
                   FROM waiting_location_candidate c, area a
                   WHERE a.area_id = %s AND c.is_current
                     AND (a.coverage IS NULL OR ST_Intersects(a.coverage, c.geom))
                   ORDER BY poi_type, name NULLS LAST, candidate_id""",
                (area_id,),
            )
            candidate_rows = cursor.fetchall()

            cursor.execute(
                """SELECT destination_id, profile, route_distance_m, route_duration_s,
                          fetched_at, source_dataset_id
                   FROM route_observation
                   WHERE area_id = %s AND fetched_at >= %s
                   ORDER BY fetched_at DESC LIMIT 100""",
                (area_id, current - timedelta(days=7)),
            )
            route_rows = cursor.fetchall()

            cursor.execute(
                """SELECT t.provider, t.openlr, t.fetched_at,
                          t.current_speed_kph, t.free_flow_speed_kph,
                          ST_AsGeoJSON(t.segment_geom) AS segment_geojson,
                          r.source_dataset_ids
                   FROM traffic_flow_observation t
                   JOIN etl_run r ON r.run_id = t.etl_run_id
                   CROSS JOIN area a
                   WHERE a.area_id = %s
                     AND t.fetched_at >= %s
                     AND (
                       a.coverage IS NULL
                       OR (t.segment_geom IS NOT NULL AND ST_Intersects(a.coverage, t.segment_geom))
                       OR ST_Intersects(a.coverage, t.query_point)
                     )
                   ORDER BY t.fetched_at DESC
                   LIMIT 500""",
                (area_id, current - timedelta(hours=24)),
            )
            traffic_rows = cursor.fetchall()

            cursor.execute(
                """SELECT source_dataset_ids FROM etl_run
                   WHERE status = 'succeeded' ORDER BY finished_at DESC NULLS LAST LIMIT 1"""
            )
            run = cursor.fetchone()

        latest_issue = weather_rows[0]["issued_at"] if weather_rows else None
        latest_weather = [row for row in weather_rows if row["issued_at"] == latest_issue]
        latest_weather.sort(key=lambda row: row["valid_at"])
        forecast_end = current + timedelta(hours=forecast_hours)
        hourly = [
            {
                "valid_time": _iso(row["valid_at"]),
                "precipitation_mm": _number(row["precipitation_mm"]),
                "precipitation_probability_pct": _number(row["precipitation_probability_pct"]),
            }
            for row in latest_weather
            if current - timedelta(hours=1) <= row["valid_at"] <= forecast_end
        ]
        latest_fetch = max((row["fetched_at"] for row in latest_weather), default=None)
        if not latest_weather:
            weather_status = "missing"
            weather_reason = "No rain forecast has been loaded for this area."
        elif not hourly:
            weather_status = "stale"
            weather_reason = f"Latest forecast issued at {_iso(latest_issue)} has no valid times in the requested horizon."
        elif latest_fetch and current - latest_fetch > timedelta(hours=6):
            weather_status = "stale"
            weather_reason = f"Latest forecast was fetched at {_iso(latest_fetch)}; refresh before using it live."
        else:
            weather_status = "partial"
            weather_reason = "Rain forecast is available for one provider grid location, not as a city-wide observation."

        cells = []
        for row in grid_rows:
            cell = {
                "cell_id": row["cell_id"],
                "row": row["row_number"],
                "column": row["column_number"],
                "cell_size_m": row["cell_size_m"],
                "cell_area_km2": _number(row["cell_area_km2"]),
                "cafe_poi_count": row["cafe_poi_count"],
                "cafe_density_per_km2": _number(row["cafe_density_per_km2"]),
                "cafe_poi_count_within_500m": row["cafe_poi_count_within_500m"],
                "cafe_count_500m_status": row["cafe_count_500m_status"],
                "center": {"latitude": row["center_latitude"], "longitude": row["center_longitude"]},
                "geometry": _json_value(row["geometry_geojson"]),
            }
            cells.append(cell)

        candidates = []
        for row in candidate_rows:
            item = {
                "candidate_id": row["candidate_id"],
                "source_provider": "OpenStreetMap",
                "source_id": row["source_id"],
                "osm_type": row["osm_type"],
                "osm_id": row["osm_id"],
                "name": row["name"],
                "poi_type": row["poi_type"],
                "role": row["role"],
                "candidate_status": row["candidate_status"],
                "permission_to_wait": row["permission_to_wait"],
                "latitude": row["latitude"],
                "longitude": row["longitude"],
                "point_method": row["point_method"],
                "area_m2": _number(row["area_m2"]),
                "verification_needed": _json_value(row["verification_needed"]),
                "categories": _json_value(row["categories"]),
                "address": row["address"],
                "tags": _json_value(row["tags"]),
            }
            candidates.append(item)

        routes = [
            {
                "destination_id": row["destination_id"],
                "profile": row["profile"],
                "route_distance_m": _number(row["route_distance_m"]),
                "route_duration_s": _number(row["route_duration_s"]),
            }
            for row in route_rows
        ]
        traffic = []
        seen_segments: set[tuple[str, str]] = set()
        traffic_source_ids: list[str] = []
        for row in traffic_rows:
            geometry = _json_value(row["segment_geojson"])
            identity_value = row["openlr"] or json.dumps(
                geometry, sort_keys=True, separators=(",", ":")
            ) if geometry is not None else row["openlr"] or _iso(row["fetched_at"])
            segment_identity = (str(row["provider"]), str(identity_value))
            if segment_identity in seen_segments:
                continue
            seen_segments.add(segment_identity)
            geometry_hash = hashlib.sha256(
                f"{row['provider']}:{identity_value}".encode("utf-8")
            ).hexdigest()[:12]
            traffic.append({
                # Engine currently uses edge_id as a display label. This stable ID intentionally
                # says “provider segment” and does not pretend to be a named or graph-matched road.
                "edge_id": f"edge_{str(row['provider']).lower()}_segment_{geometry_hash}",
                "current_speed_kmh": _number(row["current_speed_kph"]),
                "free_flow_speed_kmh": _number(row["free_flow_speed_kph"]),
                "observed_at": _iso(row["fetched_at"]),
            })
            run_dataset_ids = row["source_dataset_ids"] or []
            if isinstance(run_dataset_ids, str):
                run_dataset_ids = json.loads(run_dataset_ids)
            traffic_source_ids.extend(
                str(value) for value in run_dataset_ids
                if value and any(token in str(value).lower() for token in ("traffic", "tomtom", "flow"))
            )
        traffic_source = next(iter(dict.fromkeys(traffic_source_ids)), None)
        fresh_traffic = [
            item for item in traffic
            if _parse_iso(item["observed_at"]) >= current - traffic_max_age
        ]
        if fresh_traffic:
            traffic_status = "partial"
            traffic_reason = (
                f"{len(fresh_traffic)} fresh provider segment(s) intersect this sample area; "
                "coverage is partial and segments are not matched to route-graph edges."
            )
        elif traffic:
            traffic_status = "stale"
            traffic_reason = "Traffic rows exist, but all are older than Engine's 30-minute freshness window."
        else:
            traffic_status = "missing"
            traffic_reason = "No traffic observations are stored for this area."
        density_source = grid_rows[0]["source_dataset_id"] if grid_rows else None
        candidate_source = candidate_rows[0]["source_dataset_id"] if candidate_rows else None
        route_source = route_rows[0]["source_dataset_id"] if route_rows else None
        weather_source = latest_weather[0]["source_dataset_id"] if latest_weather else None
        poi_source = poi_source_ids[0] if poi_source_ids else area["source_dataset_id"]

        data_status = [
            _status("weather", weather_status, weather_reason, weather_source),
            _status("poi", "partial" if poi_counts else "missing",
                    "Mapped POIs are a local sample; their presence does not show passenger demand or legal waiting access."
                    if poi_counts else "No POI features are available for this area.", poi_source),
            _status("poi_density_grid", "partial" if cells else "missing",
                    "Cafe counts describe mapped OSM features by cell, not booking demand."
                    if cells else "No cafe density grid is available for this area.", density_source),
            _status("waiting_location_candidates", "partial" if candidates else "missing",
                    "Candidates are unverified for public access, vehicle access, and permission to wait."
                    if candidates else "No waiting-location candidates are available for this area.", candidate_source),
            _status("routing", "partial" if routes else "missing",
                    "Route summaries are short-lived samples; profile suitability and live traffic are unverified."
                    if routes else "No recent route summaries are available for this area.", route_source),
            _status("traffic", traffic_status, traffic_reason, traffic_source),
            _status("road_incidents", "not_integrated", "Incident observations are not exposed in Engine contract v0.1."),
            _status("verified_waiting_places", "missing", "Candidate POIs have not been verified as legal waiting places."),
            _status("events", "missing", "No event source has been verified."),
            _status("vehicle_density", "missing", "No licensed vehicle-supply feed is available."),
            _status("booking_and_destinations", "missing", "No booking-rate or destination data is available."),
            _status("trip_value", "missing", "No licensed fare or trip-value data is available."),
        ]
        safety_has_input = weather_status == "partial" or traffic_status == "partial"
        safety_status = "partial" if safety_has_input else "insufficient_data"
        objectives = [
            {"objective": "max_trip_value", "status": "insufficient_data",
             "blocking_datasets": ["booking_and_destinations", "trip_value"],
             "reason": "No booking, destination, or fare data is available."},
            {"objective": "maintain_position", "status": "insufficient_data",
             "blocking_datasets": ["booking_and_destinations"],
             "reason": "POIs and a route sample do not estimate next-trip opportunity."},
            {"objective": "rest_spot", "status": "partial" if candidates else "insufficient_data",
             "blocking_datasets": ["verified_waiting_places"],
             "reason": "POIs are unverified candidates, not confirmed places to stop or park."},
            {"objective": "safety_comfort", "status": safety_status,
             "blocking_datasets": (["traffic"] if traffic_status != "partial" else []) + ["road_incidents"] + (["weather"] if weather_status in ("missing", "stale") else []),
             "reason": "Traffic samples, when present, cover only provider segments; incidents and route-wide traffic matching are unavailable."},
        ]
        source_ids = list(dict.fromkeys(
            [value for value in (
                *(run["source_dataset_ids"] if run else []), weather_source, *poi_source_ids,
                density_source, candidate_source, route_source, *traffic_source_ids,
            ) if value]
        ))
        result: dict[str, Any] = {
            "schema_version": "0.1",
            "snapshot_id": f"{area_id}_{uuid4().hex[:12]}",
            "generated_at": _iso(current),
            "source_dataset_ids": source_ids,
            "data_status": data_status,
            "objective_readiness": objectives,
            "traffic": traffic,
            "areas": [{
                "area_id": area["area_id"],
                "spatial_scope": area["spatial_scope"],
                "representative_point": {"latitude": area["latitude"], "longitude": area["longitude"]},
                "weather": {
                    "provider_grid_location": {
                        "latitude": latest_weather[0]["latitude"] if latest_weather else area["latitude"],
                        "longitude": latest_weather[0]["longitude"] if latest_weather else area["longitude"],
                        "elevation_m": None,
                    },
                    "hourly": hourly,
                },
                "poi_counts_by_category": poi_counts,
                "poi_density_grid": {
                    "cell_size_m": cells[0]["cell_size_m"] if cells else None,
                    "source_dataset_id": density_source,
                    "cells": cells,
                },
                "waiting_location_candidates": candidates,
                "routing_samples": routes,
            }],
            "limitations": [
                "Snapshot is assembled from the latest normalized database rows; it does not fetch provider APIs.",
                "Freshness is evaluated at snapshot generation time; stale or missing data must not be treated as zero.",
                "POI density is mapped cafe presence, not customer demand or probability of a booking.",
                "Waiting-location candidates are unverified; map coordinates do not establish legal stopping access.",
                "OSRM driving route summaries are not live traffic or verified motorcycle travel times.",
                "Traffic observations are provider segments, not route-wide or map-matched road-edge coverage.",
                "Traffic confidence and incidents are stored outside the Engine TrafficEdge fields and are not scored.",
            ],
        }
        if rain_tolerance_level is not None:
            result["driver_preferences"] = {"rain_tolerance_level": rain_tolerance_level}
        return result


def _status(dataset: str, status: str, reason: str, source: str | None = None) -> dict[str, str]:
    result = {"dataset": dataset, "status": status, "reason": reason}
    if source:
        result["source_dataset_id"] = source
    return result


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _number(value: Any) -> int | float | None:
    if value is None:
        return None
    number = float(value)
    return int(number) if number.is_integer() else number


def _parse_iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(timezone.utc)


def _json_value(value: Any) -> Any:
    if isinstance(value, str):
        import json
        return json.loads(value)
    return value
