"""Persist normalized live provider observations without retaining raw bodies."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from typing import Any
from uuid import uuid4

from data.db.connection import connect


TRAFFIC_DATASET_ID = "tomtom_traffic_flow_segment_hcmc"
WEATHER_DATASET_ID = "gigca_hcmc_demo_open_meteo_weather"
DEMO_AREA_ID = "hcmc_demo_point_01"


def _flow_geometry(flow: dict[str, Any]) -> str | None:
    coordinates = flow.get("coordinates", {}).get("coordinate", [])
    points = [
        [item.get("longitude"), item.get("latitude")]
        for item in coordinates
        if isinstance(item, dict)
        and isinstance(item.get("longitude"), (int, float))
        and isinstance(item.get("latitude"), (int, float))
    ]
    if len(points) < 2:
        return None
    return json.dumps({"type": "LineString", "coordinates": points})


def save_traffic_observation(
    latitude: float,
    longitude: float,
    flow: dict[str, Any],
    *,
    fetched_at: datetime | None = None,
    database_url: str | None = None,
) -> int:
    """Save one TomTom flow segment returned for a requested map point."""
    if not isinstance(flow.get("currentSpeed"), (int, float)) or not isinstance(
        flow.get("freeFlowSpeed"), (int, float)
    ):
        raise ValueError("TomTom Flow response is missing current/free-flow speed")
    observed_at = fetched_at or datetime.now(timezone.utc)
    run_id = uuid4()
    geometry = _flow_geometry(flow)
    with connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO etl_run
                       (run_id, started_at, finished_at, status, source_dataset_ids, note)
                   VALUES (%s, %s, %s, 'succeeded', %s, %s)""",
                (
                    run_id,
                    observed_at,
                    observed_at,
                    json.dumps([TRAFFIC_DATASET_ID]),
                    "On-demand TomTom Flow request; normalized observation only, raw body not stored.",
                ),
            )
            cursor.execute(
                """INSERT INTO traffic_flow_observation
                       (provider, fetched_at, query_point, segment_geom,
                        current_speed_kph, free_flow_speed_kph,
                        current_travel_time_s, free_flow_travel_time_s,
                        confidence, road_closed, functional_road_class, openlr, etl_run_id)
                   VALUES ('TomTom', %s,
                           ST_SetSRID(ST_MakePoint(%s, %s), 4326),
                           CASE WHEN %s::text IS NULL THEN NULL
                                ELSE ST_SetSRID(ST_GeomFromGeoJSON(%s::text), 4326) END,
                           %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   RETURNING observation_id""",
                (
                    observed_at,
                    longitude,
                    latitude,
                    geometry,
                    geometry,
                    flow.get("currentSpeed"),
                    flow.get("freeFlowSpeed"),
                    flow.get("currentTravelTime"),
                    flow.get("freeFlowTravelTime"),
                    flow.get("confidence"),
                    flow.get("roadClosure"),
                    flow.get("frc"),
                    flow.get("openlr"),
                    run_id,
                ),
            )
            row = cursor.fetchone()
    return int(row["observation_id"])


def save_weather_forecast(
    dataset: dict[str, Any],
    *,
    area_id: str = DEMO_AREA_ID,
    database_url: str | None = None,
) -> int:
    """Append one fetched hourly rain forecast vintage for a configured area."""
    location = dataset.get("requested_location") or {}
    provider_location = dataset.get("source", {}).get("provider_location") or location
    if not all(isinstance(location.get(k), (int, float)) for k in ("latitude", "longitude")):
        raise ValueError("Weather dataset has no numeric requested_location")
    if not all(isinstance(provider_location.get(k), (int, float)) for k in ("latitude", "longitude")):
        raise ValueError("Weather dataset has no numeric provider_location")
    fetched_at = datetime.fromisoformat(
        str(dataset["generated_at"]).replace("Z", "+00:00")
    ).astimezone(timezone.utc)
    run_id = uuid4()
    dataset_id = str(dataset.get("dataset_id") or WEATHER_DATASET_ID)
    timezone_name = dataset.get("source", {}).get("timezone", "Asia/Ho_Chi_Minh")
    with connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT 1 FROM area WHERE area_id = %s
                   AND ST_DWithin(
                     representative_point::geography,
                     ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
                     1000
                   )""",
                (area_id, location["longitude"], location["latitude"]),
            )
            if cursor.fetchone() is None:
                raise RuntimeError(
                    f"Area {area_id!r} is not initialized near this weather location; "
                    "load the demo samples first."
                )
            cursor.execute(
                """INSERT INTO etl_run
                       (run_id, started_at, finished_at, status, source_dataset_ids, note)
                   VALUES (%s, %s, %s, 'succeeded', %s, %s)""",
                (
                    run_id,
                    fetched_at,
                    datetime.now(timezone.utc),
                    json.dumps([dataset_id]),
                    "Scheduled Open-Meteo forecast refresh; normalized hourly rows only.",
                ),
            )
            for item in dataset.get("hourly", []):
                valid_at = datetime.fromisoformat(
                    str(item["valid_time"]).replace("Z", "+00:00")
                )
                if valid_at.tzinfo is None:
                    from zoneinfo import ZoneInfo

                    valid_at = valid_at.replace(tzinfo=ZoneInfo(timezone_name))
                cursor.execute(
                    """INSERT INTO weather_forecast
                           (provider, area_id, provider_location, issued_at, valid_at, fetched_at,
                            precipitation_probability_pct, precipitation_mm, etl_run_id, source_dataset_id)
                       VALUES ('Open-Meteo', %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326),
                               %s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (provider, area_id, issued_at, valid_at, fetched_at) DO NOTHING""",
                    (
                        area_id,
                        provider_location["longitude"],
                        provider_location["latitude"],
                        fetched_at,
                        valid_at.astimezone(timezone.utc),
                        fetched_at,
                        item.get("precipitation_probability_pct"),
                        item.get("precipitation_mm"),
                        run_id,
                        dataset_id,
                    ),
                )
            cursor.execute("UPDATE etl_run SET status = 'succeeded' WHERE run_id = %s", (run_id,))
            cursor.execute(
                "SELECT count(*) AS row_count FROM weather_forecast WHERE etl_run_id = %s",
                (run_id,),
            )
            return int(cursor.fetchone()["row_count"])


def read_scheduled_weather(
    latitude: float,
    longitude: float,
    *,
    max_area_distance_m: int = 10_000,
    database_url: str | None = None,
) -> dict[str, Any]:
    """Read the latest scheduled forecast vintage for the nearest configured area."""
    with connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """WITH nearest_area AS (
                   SELECT area_id
                   FROM area
                   WHERE ST_DWithin(
                     representative_point::geography,
                     ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
                     %s
                   )
                   ORDER BY ST_Distance(
                     representative_point::geography,
                     ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography
                   )
                   LIMIT 1
               ), latest_vintage AS (
                   SELECT max(w.issued_at) AS issued_at
                   FROM weather_forecast w JOIN nearest_area a USING (area_id)
               )
               SELECT w.provider, w.issued_at, w.fetched_at, w.valid_at,
                      w.precipitation_probability_pct, w.precipitation_mm,
                      ST_Y(w.provider_location) AS provider_latitude,
                      ST_X(w.provider_location) AS provider_longitude
               FROM weather_forecast w
               JOIN nearest_area a USING (area_id)
               JOIN latest_vintage v USING (issued_at)
               ORDER BY w.valid_at""",
            (longitude, latitude, max_area_distance_m, longitude, latitude),
        )
        rows = cursor.fetchall()
    if not rows:
        raise RuntimeError("No scheduled rain forecast is stored near this map location.")
    fetched_at = max(row["fetched_at"] for row in rows)
    return {
        "provider": rows[0]["provider"],
        "fetched_at": fetched_at.astimezone(timezone.utc).isoformat(timespec="seconds"),
        "data_status": "stale" if datetime.now(timezone.utc) - fetched_at > timedelta(hours=6) else "available",
        "requested_location": {"latitude": latitude, "longitude": longitude},
        "provider_location": {
            "latitude": rows[0]["provider_latitude"],
            "longitude": rows[0]["provider_longitude"],
        },
        "hourly": [
            {
                "valid_time": row["valid_at"].isoformat(timespec="minutes"),
                "precipitation_probability_pct": (
                    float(row["precipitation_probability_pct"])
                    if row["precipitation_probability_pct"] is not None else None
                ),
                "precipitation_mm": (
                    float(row["precipitation_mm"]) if row["precipitation_mm"] is not None else None
                ),
            }
            for row in rows
        ],
    }
