"""Load the checked-in, normalized HCMC demo samples into PostGIS.

This loader does not persist provider response bodies or read Git-ignored raw
TomTom files. It is intended for reproducible local/demo data only.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from data.db.connection import connect


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SAMPLES = ROOT / "data" / "samples"
AREA_ID = "hcmc_demo_point_01"


def read_sample(directory: Path, name: str) -> dict[str, Any]:
    path = directory / name
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Could not load sample {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"Expected an object in {path}")
    return value


def parse_time(value: str, timezone_name: str = "Asia/Ho_Chi_Minh") -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo(timezone_name))
    return parsed.astimezone(timezone.utc)


def geojson_polygon(bbox: dict[str, float]) -> str:
    west, south = bbox["west"], bbox["south"]
    east, north = bbox["east"], bbox["north"]
    return json.dumps({
        "type": "Polygon",
        "coordinates": [[[west, south], [east, south], [east, north], [west, north], [west, south]]],
    })


def load_samples(samples_dir: Path = DEFAULT_SAMPLES, database_url: str | None = None) -> str:
    weather = read_sample(samples_dir, "open_meteo_weather_hcmc.json")
    pois = read_sample(samples_dir, "osm_overpass_pois_hcmc.json")
    grid = read_sample(samples_dir, "osm_poi_grid_hcmc.json")
    candidates = read_sample(samples_dir, "osm_waiting_candidates_hcmc.json")
    route = read_sample(samples_dir, "osrm_route_hcmc.json")
    waiting_routes_path = samples_dir / "osrm_waiting_candidate_routes_hcmc.json"
    waiting_routes = read_sample(samples_dir, waiting_routes_path.name) if waiting_routes_path.is_file() else None
    sample_docs = (weather, pois, grid, candidates, route) + ((waiting_routes,) if waiting_routes else ())
    dataset_ids = [str(doc["dataset_id"]) for doc in sample_docs]
    run_id = uuid4()

    weather_location = weather["requested_location"]
    timezone_name = weather.get("source", {}).get("timezone", "Asia/Ho_Chi_Minh")
    coverage = grid.get("coverage", {})
    bbox = coverage.get("bbox")
    coverage_json = geojson_polygon(bbox) if isinstance(bbox, dict) else None
    generated_at = max(parse_time(str(doc["generated_at"])) for doc in sample_docs)

    with connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO etl_run (run_id, started_at, finished_at, status, source_dataset_ids, note) "
                "VALUES (%s, %s, %s, 'succeeded', %s, %s)",
                (run_id, generated_at, datetime.now(timezone.utc), json.dumps(dataset_ids),
                 "Loaded checked-in demo JSON; raw provider payloads were not stored."),
            )
            cursor.execute(
                """INSERT INTO area
                    (area_id, spatial_scope, representative_point, coverage, timezone_name,
                     source_dataset_id, etl_run_id, updated_at)
                    VALUES (%s, 'point_sample', ST_SetSRID(ST_MakePoint(%s, %s), 4326),
                            CASE WHEN %s::text IS NULL THEN NULL ELSE ST_SetSRID(ST_GeomFromGeoJSON(%s::text), 4326) END,
                            %s, %s, %s, now())
                    ON CONFLICT (area_id) DO UPDATE SET
                      representative_point = EXCLUDED.representative_point,
                      coverage = EXCLUDED.coverage,
                      timezone_name = EXCLUDED.timezone_name,
                      source_dataset_id = EXCLUDED.source_dataset_id,
                      etl_run_id = EXCLUDED.etl_run_id,
                      updated_at = now()""",
                (AREA_ID, weather_location["longitude"], weather_location["latitude"],
                 coverage_json, coverage_json, timezone_name, weather["dataset_id"], run_id),
            )
            if coverage_json is not None:
                cursor.execute(
                    """UPDATE poi_feature p SET is_current = false
                       FROM area a WHERE a.area_id = %s AND p.provider = 'OpenStreetMap'
                         AND ST_Intersects(a.coverage, p.geom)""",
                    (AREA_ID,),
                )
                cursor.execute(
                    """UPDATE waiting_location_candidate c SET is_current = false
                       FROM area a WHERE a.area_id = %s AND c.provider = 'OpenStreetMap'
                         AND ST_Intersects(a.coverage, c.geom)""",
                    (AREA_ID,),
                )

            provider_location = weather.get("source", {}).get("provider_location", weather_location)
            issued_at = parse_time(weather["generated_at"], timezone_name)
            fetched_at = issued_at
            for item in weather.get("hourly", []):
                cursor.execute(
                    """INSERT INTO weather_forecast
                        (provider, area_id, provider_location, issued_at, valid_at, fetched_at,
                         precipitation_probability_pct, precipitation_mm, etl_run_id, source_dataset_id)
                        VALUES (%s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326), %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (provider, area_id, issued_at, valid_at, fetched_at) DO NOTHING""",
                    ("Open-Meteo", AREA_ID, provider_location["longitude"], provider_location["latitude"],
                     issued_at, parse_time(item["valid_time"], timezone_name), fetched_at,
                     item.get("precipitation_probability_pct"), item.get("precipitation_mm"),
                     run_id, weather["dataset_id"]),
                )

            poi_generated = parse_time(pois["generated_at"])
            for item in pois.get("pois", []):
                source_feature_id = f"{item.get('osm_type', 'feature')}:{item.get('osm_id', item.get('name', 'unknown'))}"
                cursor.execute(
                    """INSERT INTO poi_feature
                        (provider, source_feature_id, category, subcategory, name, point_method, geom,
                         tags, fetched_at, etl_run_id, source_dataset_id, is_current)
                        VALUES (%s, %s, %s, %s, %s, %s,
                                ST_SetSRID(ST_MakePoint(%s, %s), 4326), %s, %s, %s, %s, true)
                        ON CONFLICT (provider, source_feature_id) DO UPDATE SET
                          category = EXCLUDED.category, subcategory = EXCLUDED.subcategory,
                          name = EXCLUDED.name, point_method = EXCLUDED.point_method,
                          geom = EXCLUDED.geom, tags = EXCLUDED.tags, fetched_at = EXCLUDED.fetched_at,
                          etl_run_id = EXCLUDED.etl_run_id, source_dataset_id = EXCLUDED.source_dataset_id,
                          is_current = true""",
                    ("OpenStreetMap", source_feature_id, item.get("category", "unknown"),
                     item.get("subcategory"), item.get("name"), item.get("point_method"),
                     item["longitude"], item["latitude"], json.dumps(item.get("tags") or {}),
                     poi_generated, run_id, pois["dataset_id"]),
                )

            for cell in grid.get("cells", []):
                center = cell["center"]
                polygon = json.dumps(cell["geometry"])
                cursor.execute(
                    """INSERT INTO poi_grid_cell
                        (cell_id, parent_area_id, row_number, column_number, center, geom,
                         cell_size_m, cell_area_km2, cafe_poi_count, cafe_density_per_km2,
                         cafe_poi_count_within_500m, cafe_count_500m_status, etl_run_id, source_dataset_id)
                        VALUES (%s, %s, %s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326),
                                ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326), %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (cell_id) DO UPDATE SET
                          parent_area_id = EXCLUDED.parent_area_id, row_number = EXCLUDED.row_number,
                          column_number = EXCLUDED.column_number, center = EXCLUDED.center,
                          geom = EXCLUDED.geom, cell_size_m = EXCLUDED.cell_size_m,
                          cell_area_km2 = EXCLUDED.cell_area_km2, cafe_poi_count = EXCLUDED.cafe_poi_count,
                          cafe_density_per_km2 = EXCLUDED.cafe_density_per_km2,
                          cafe_poi_count_within_500m = EXCLUDED.cafe_poi_count_within_500m,
                          cafe_count_500m_status = EXCLUDED.cafe_count_500m_status,
                          etl_run_id = EXCLUDED.etl_run_id, source_dataset_id = EXCLUDED.source_dataset_id""",
                    (cell["cell_id"], AREA_ID, cell.get("row", 0), cell.get("column", 0),
                     center["longitude"], center["latitude"], polygon, cell["cell_size_m"],
                     cell["cell_area_km2"], cell["cafe_poi_count"], cell["cafe_density_per_km2"],
                     cell.get("cafe_poi_count_within_500m"), cell["cafe_count_500m_status"],
                     run_id, grid["dataset_id"]),
                )

            candidate_generated = parse_time(candidates["generated_at"])
            for item in candidates.get("candidates", []):
                cursor.execute(
                    """INSERT INTO waiting_location_candidate
                        (candidate_id, provider, source_id, osm_type, osm_id, name, poi_type, role,
                         candidate_status, permission_to_wait, latitude, longitude, geom, point_method,
                         area_m2, verification_needed, categories, address, tags, fetched_at, etl_run_id,
                         source_dataset_id, is_current)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                                ST_SetSRID(ST_MakePoint(%s, %s), 4326), %s, %s, %s, %s, %s, %s, %s, %s, %s, true)
                        ON CONFLICT (candidate_id) DO UPDATE SET
                          name = EXCLUDED.name, poi_type = EXCLUDED.poi_type,
                          candidate_status = EXCLUDED.candidate_status,
                          permission_to_wait = EXCLUDED.permission_to_wait,
                          latitude = EXCLUDED.latitude, longitude = EXCLUDED.longitude,
                          geom = EXCLUDED.geom, point_method = EXCLUDED.point_method,
                          area_m2 = EXCLUDED.area_m2, verification_needed = EXCLUDED.verification_needed,
                          categories = EXCLUDED.categories, address = EXCLUDED.address, tags = EXCLUDED.tags,
                          fetched_at = EXCLUDED.fetched_at, etl_run_id = EXCLUDED.etl_run_id,
                          source_dataset_id = EXCLUDED.source_dataset_id, is_current = true""",
                    (item["candidate_id"], "OpenStreetMap", item.get("source_id", ""),
                     item.get("osm_type"), str(item["osm_id"]) if item.get("osm_id") is not None else None,
                     item.get("name"), item["poi_type"], item.get("role", "waiting_location_candidate"),
                     item.get("candidate_status", "unverified_candidate"),
                     item.get("permission_to_wait", "unknown"), item["latitude"], item["longitude"],
                     item["longitude"], item["latitude"], item.get("point_method", "unknown"),
                     item.get("area_m2"), json.dumps(item.get("verification_needed") or []),
                     json.dumps(item.get("categories") or []), item.get("address"),
                     json.dumps(item.get("tags") or {}), candidate_generated, run_id,
                     candidates["dataset_id"]),
                )

            route_response = route.get("response", {})
            routes = route_response.get("routes", [])
            request = route.get("request", {})
            if route_response.get("code") == "Ok" and routes:
                result = routes[0]
                cursor.execute(
                    """INSERT INTO route_observation
                        (area_id, destination_id, provider, profile, fetched_at, route_distance_m,
                         route_duration_s, origin, destination, etl_run_id, source_dataset_id)
                        VALUES (%s, %s, %s, %s, %s, %s, %s,
                                ST_SetSRID(ST_MakePoint(%s, %s), 4326),
                                ST_SetSRID(ST_MakePoint(%s, %s), 4326), %s, %s)
                        ON CONFLICT (area_id, destination_id, provider, profile, fetched_at) DO NOTHING""",
                    (AREA_ID, "sample_destination_01", "OSRM", request.get("profile", "driving"),
                     parse_time(route["generated_at"]), result.get("distance"), result.get("duration"),
                     request["origin"]["longitude"], request["origin"]["latitude"],
                     request["destination"]["longitude"], request["destination"]["latitude"],
                    run_id, route["dataset_id"]),
                )

            if waiting_routes:
                candidate_locations = {
                    item["candidate_id"]: item for item in candidates.get("candidates", [])
                }
                route_origin = waiting_routes.get("request", {}).get("origin", weather_location)
                route_profile = waiting_routes.get("request", {}).get("profile", "driving")
                route_fetched_at = parse_time(waiting_routes["generated_at"])
                for item in waiting_routes.get("routes", []):
                    destination = candidate_locations.get(item.get("destination_id"))
                    if destination is None:
                        continue
                    cursor.execute(
                        """INSERT INTO route_observation
                            (area_id, destination_id, provider, profile, fetched_at, route_distance_m,
                             route_duration_s, origin, destination, etl_run_id, source_dataset_id)
                            VALUES (%s, %s, %s, %s, %s, %s, %s,
                                    ST_SetSRID(ST_MakePoint(%s, %s), 4326),
                                    ST_SetSRID(ST_MakePoint(%s, %s), 4326), %s, %s)
                            ON CONFLICT (area_id, destination_id, provider, profile, fetched_at) DO NOTHING""",
                        (AREA_ID, item["destination_id"], "OSRM", item.get("profile", route_profile),
                         route_fetched_at, item.get("route_distance_m"), item.get("route_duration_s"),
                         route_origin["longitude"], route_origin["latitude"],
                         destination["longitude"], destination["latitude"], run_id,
                         waiting_routes["dataset_id"]),
                    )

            cursor.execute("UPDATE etl_run SET status = 'succeeded' WHERE run_id = %s", (run_id,))
    return str(run_id)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples-dir", type=Path, default=DEFAULT_SAMPLES)
    args = parser.parse_args()
    print(f"Loaded sample data in ETL run {load_samples(args.samples_dir)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
