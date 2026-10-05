#!/usr/bin/env python3
"""Fetch HCMC POI context, cafe density cells, and unverified waiting candidates."""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "data" / "samples"
DEFAULT_OVERPASS_URL = "https://overpass-api.de/api/interpreter"
USER_AGENT = "GigCaPOISpatialDemo/0.1 (OpenStreetMap sample; non-commercial class project)"
METERS_PER_LAT_DEGREE = 110_574.0
METERS_PER_LON_DEGREE_AT_EQUATOR = 111_320.0
OPEN_LAND_TYPES = {"grass", "meadow", "greenfield", "brownfield", "recreation_ground"}
MIN_OPEN_AREA_M2 = 2_500
NEARBY_CAFE_RADIUS_M = 500


def fetch_overpass(query: str, endpoint: str, timeout: int = 90) -> dict[str, Any]:
    body = urlencode({"data": query}).encode("utf-8")
    request = Request(
        endpoint,
        data=body,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = response.read()
    except HTTPError as exc:
        raise RuntimeError(f"Overpass trả HTTP {exc.code}; chưa ghi sample.") from None
    except URLError as exc:
        raise RuntimeError(f"Không kết nối được Overpass ({type(exc.reason).__name__}); chưa ghi sample.") from None
    except TimeoutError:
        raise RuntimeError("Overpass timeout; chưa ghi sample.") from None
    try:
        decoded = json.loads(payload)
    except json.JSONDecodeError:
        raise RuntimeError("Overpass trả JSON không hợp lệ; chưa ghi sample.") from None
    if not isinstance(decoded, dict) or not isinstance(decoded.get("elements"), list):
        raise RuntimeError("Overpass response thiếu elements; chưa ghi sample.")
    return decoded


def bounds_for(lat: float, lon: float, extent_m: int) -> tuple[float, float, float, float]:
    m_per_lon = METERS_PER_LON_DEGREE_AT_EQUATOR * math.cos(math.radians(lat))
    dlat = extent_m / METERS_PER_LAT_DEGREE
    dlon = extent_m / m_per_lon
    return lat - dlat, lon - dlon, lat + dlat, lon + dlon


def build_poi_query(bounds: tuple[float, float, float, float]) -> str:
    south, west, north, east = bounds
    bbox = f"({south:.7f},{west:.7f},{north:.7f},{east:.7f})"
    filters = (
        '["amenity"~"^(cafe|parking|parking_space|school|place_of_worship|marketplace|fuel|bus_station|university|college)$"]',
        '["shop"~"^(mall|coffee)$"]',
        '["building"~"^(school|university|college|church|retail)$"]',
        '["leisure"~"^(park|recreation_ground)$"]',
        '["highway"="rest_area"]',
        '["landuse"~"^(retail|grass|meadow|greenfield|brownfield)$"]',
    )
    lines = ["[out:json][timeout:75];", "("]
    for tag_filter in filters:
        lines.append(f"  nwr{bbox}{tag_filter};")
    lines.extend((");", "out center tags;"))
    return "\n".join(lines)


def build_open_area_query(bounds: tuple[float, float, float, float]) -> str:
    south, west, north, east = bounds
    bbox = f"({south:.7f},{west:.7f},{north:.7f},{east:.7f})"
    lines = [
        "[out:json][timeout:75];",
        "(",
        f'  way{bbox}["landuse"~"^(grass|meadow|greenfield|brownfield)$"];',
        f'  way{bbox}["leisure"~"^(park|recreation_ground)$"];',
        ");",
        "out geom tags;",
    ]
    return "\n".join(lines)


def feature_point(element: dict[str, Any]) -> tuple[float, float, str] | None:
    if element.get("type") == "node" and element.get("lat") is not None and element.get("lon") is not None:
        return float(element["lat"]), float(element["lon"]), "node_coordinate"
    center = element.get("center") or {}
    if center.get("lat") is not None and center.get("lon") is not None:
        return float(center["lat"]), float(center["lon"]), "osm_center_approximation"
    return None


def metric_xy(lat: float, lon: float, origin_lat: float, origin_lon: float) -> tuple[float, float]:
    x = (lon - origin_lon) * METERS_PER_LON_DEGREE_AT_EQUATOR * math.cos(math.radians(origin_lat))
    y = (lat - origin_lat) * METERS_PER_LAT_DEGREE
    return x, y


def polygon_area_centroid(geometry: list[dict[str, Any]], reference_lat: float) -> tuple[float, float, float] | None:
    if len(geometry) < 4:
        return None
    points = [(float(point["lon"]), float(point["lat"])) for point in geometry if "lon" in point and "lat" in point]
    if len(points) < 4 or points[0] != points[-1]:
        return None
    scale_x = METERS_PER_LON_DEGREE_AT_EQUATOR * math.cos(math.radians(reference_lat))
    points_xy = [(lon * scale_x, lat * METERS_PER_LAT_DEGREE) for lon, lat in points]
    twice_area = 0.0
    centroid_x = 0.0
    centroid_y = 0.0
    for (x1, y1), (x2, y2) in zip(points_xy, points_xy[1:]):
        cross = x1 * y2 - x2 * y1
        twice_area += cross
        centroid_x += (x1 + x2) * cross
        centroid_y += (y1 + y2) * cross
    if abs(twice_area) < 1e-6:
        return None
    area = abs(twice_area) / 2
    cx = centroid_x / (3 * twice_area)
    cy = centroid_y / (3 * twice_area)
    return area, cy / METERS_PER_LAT_DEGREE, cx / scale_x


def classify(tags: dict[str, Any]) -> tuple[str, str] | None:
    amenity = tags.get("amenity")
    if amenity == "cafe" or tags.get("shop") == "coffee":
        return "cafe", "activity_anchor"
    if amenity in {"parking", "parking_space"} or tags.get("parking"):
        return "parking", "waiting_location_candidate"
    if amenity == "place_of_worship" or tags.get("building") in {"church", "chapel"}:
        religion = str(tags.get("religion", "")).lower()
        return ("church" if religion in {"christian", "catholic", "protestant", "orthodox"} or tags.get("building") in {"church", "chapel"} else "place_of_worship"), "waiting_location_candidate"
    if amenity in {"school", "university", "college"} or tags.get("building") in {"school", "university", "college"}:
        return "school", "waiting_location_candidate"
    if tags.get("shop") == "mall" or tags.get("building") == "retail" or tags.get("landuse") == "retail":
        return "shopping_center", "waiting_location_candidate"
    if amenity == "fuel":
        return "fuel_station", "waiting_location_candidate"
    if amenity == "bus_station" or tags.get("highway") == "rest_area":
        return "transit_or_rest_area", "waiting_location_candidate"
    if tags.get("leisure") in {"park", "recreation_ground"}:
        return "park", "waiting_location_candidate"
    if tags.get("landuse") in OPEN_LAND_TYPES:
        return "open_land", "waiting_location_candidate"
    if amenity == "marketplace":
        return "market", "activity_anchor"
    return None


def normalize_elements(elements: list[dict[str, Any]], *, open_areas: list[dict[str, Any]], center_lat: float, center_lon: float) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    combined: dict[str, dict[str, Any]] = {}
    open_area_map: dict[str, dict[str, Any]] = {}
    for element in open_areas:
        tags = element.get("tags") or {}
        metrics = polygon_area_centroid(element.get("geometry") or [], center_lat)
        if not metrics:
            continue
        area_m2, lat, lon = metrics
        if area_m2 < MIN_OPEN_AREA_M2:
            continue
        key = f"{element.get('type')}:{element.get('id')}"
        open_area_map[key] = {"area_m2": round(area_m2, 1), "latitude": lat, "longitude": lon, "point_method": "polygon_centroid", "tags": tags}

    for element in elements:
        tags = element.get("tags") or {}
        classification = classify(tags)
        if not classification:
            continue
        point = feature_point(element)
        key = f"{element.get('type')}:{element.get('id')}"
        if key in open_area_map:
            area = open_area_map[key]
            point = (area["latitude"], area["longitude"], area["point_method"])
        if not point:
            continue
        lat, lon, point_method = point
        category, role = classification
        combined[key] = {
            "candidate_id": f"osm_{element.get('type')}_{element.get('id')}",
            "osm_type": element.get("type"),
            "osm_id": element.get("id"),
            "name": tags.get("name"),
            "poi_type": category,
            "role": role,
            "latitude": lat,
            "longitude": lon,
            "point_method": point_method,
            "area_m2": open_area_map.get(key, {}).get("area_m2"),
            "tags": tags,
        }

    for key, area in open_area_map.items():
        if key in combined:
            continue
        osm_type, osm_id = key.split(":", 1)
        tags = area["tags"]
        category, role = classify(tags) or ("open_land", "waiting_location_candidate")
        combined[key] = {
            "candidate_id": f"osm_{osm_type}_{osm_id}",
            "osm_type": osm_type,
            "osm_id": int(osm_id),
            "name": tags.get("name"),
            "poi_type": category,
            "role": role,
            "latitude": area["latitude"],
            "longitude": area["longitude"],
            "point_method": area["point_method"],
            "area_m2": area["area_m2"],
            "tags": tags,
        }

    all_places = sorted(combined.values(), key=lambda item: (item["poi_type"], str(item.get("name") or "")))
    candidates = [
        {
            **place,
            "source_provider": "OpenStreetMap via Overpass API",
            "source_id": f"{place['osm_type']}:{place['osm_id']}",
            "candidate_status": "unverified_candidate",
            "permission_to_wait": "unknown",
            "verification_needed": ["public_or_owner_access", "motorcycle_access", "waiting_or_parking_permission", "opening_hours", "exact_entrance_or_staging_point"],
        }
        for place in all_places
        if place["role"] == "waiting_location_candidate"
    ]
    return all_places, candidates


def make_grid(places: list[dict[str, Any]], center_lat: float, center_lon: float, extent_m: int, cell_size_m: int, *, circular_coverage_radius_m: int | None = None) -> list[dict[str, Any]]:
    cafe_points = [place for place in places if place["poi_type"] == "cafe"]
    count_per_side = (2 * extent_m) // cell_size_m
    west = center_lon - extent_m / (METERS_PER_LON_DEGREE_AT_EQUATOR * math.cos(math.radians(center_lat)))
    south = center_lat - extent_m / METERS_PER_LAT_DEGREE
    cells = []
    for row in range(count_per_side):
        for col in range(count_per_side):
            min_x = -extent_m + col * cell_size_m
            min_y = -extent_m + row * cell_size_m
            center_x = min_x + cell_size_m / 2
            center_y = min_y + cell_size_m / 2
            if circular_coverage_radius_m is not None:
                far_x = max(abs(min_x), abs(min_x + cell_size_m))
                far_y = max(abs(min_y), abs(min_y + cell_size_m))
                if math.hypot(far_x, far_y) > circular_coverage_radius_m:
                    continue
            center_cell_lat = center_lat + center_y / METERS_PER_LAT_DEGREE
            center_cell_lon = center_lon + center_x / (METERS_PER_LON_DEGREE_AT_EQUATOR * math.cos(math.radians(center_lat)))
            inside = 0
            nearby = 0
            neighborhood_covered = circular_coverage_radius_m is None or math.hypot(center_x, center_y) + NEARBY_CAFE_RADIUS_M <= circular_coverage_radius_m
            for cafe in cafe_points:
                x, y = metric_xy(cafe["latitude"], cafe["longitude"], center_lat, center_lon)
                if min_x <= x < min_x + cell_size_m and min_y <= y < min_y + cell_size_m:
                    inside += 1
                if neighborhood_covered and math.hypot(x - center_x, y - center_y) <= NEARBY_CAFE_RADIUS_M:
                    nearby += 1
            cell_west = west + col * cell_size_m / (METERS_PER_LON_DEGREE_AT_EQUATOR * math.cos(math.radians(center_lat)))
            cell_south = south + row * cell_size_m / METERS_PER_LAT_DEGREE
            cell_east = cell_west + cell_size_m / (METERS_PER_LON_DEGREE_AT_EQUATOR * math.cos(math.radians(center_lat)))
            cell_north = cell_south + cell_size_m / METERS_PER_LAT_DEGREE
            cells.append(
                {
                    "cell_id": f"hcmc_{cell_size_m}m_r{row:02d}_c{col:02d}",
                    "row": row,
                    "column": col,
                    "center": {"latitude": center_cell_lat, "longitude": center_cell_lon},
                    "cell_size_m": cell_size_m,
                    "cell_area_km2": round((cell_size_m * cell_size_m) / 1_000_000, 4),
                    "cafe_poi_count": inside,
                    "cafe_density_per_km2": round(inside / ((cell_size_m * cell_size_m) / 1_000_000), 2),
                    "cafe_poi_count_within_500m": nearby if neighborhood_covered else None,
                    "cafe_count_500m_status": "full_coverage" if neighborhood_covered else "partial_coverage",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[[cell_west, cell_south], [cell_east, cell_south], [cell_east, cell_north], [cell_west, cell_north], [cell_west, cell_south]]],
                    },
                }
            )
    return cells


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lat", type=float, default=10.7769, help="Center latitude; default is central HCMC")
    parser.add_argument("--lon", type=float, default=106.7009, help="Center longitude; default is central HCMC")
    parser.add_argument("--extent-m", type=int, default=1500, help="Half-width of square extraction coverage in meters")
    parser.add_argument("--cell-size-m", type=int, default=500, help="Square grid cell edge length in meters")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--overpass-url", default=DEFAULT_OVERPASS_URL)
    parser.add_argument("--input-json", type=Path, help="Build grid/candidates from an existing normalized OSM POI sample instead of making live Overpass requests")
    args = parser.parse_args()
    if not -90 <= args.lat <= 90 or not -180 <= args.lon <= 180:
        parser.error("Coordinates are outside WGS84 bounds")
    if not 250 <= args.extent_m <= 10_000 or args.extent_m % args.cell_size_m:
        parser.error("--extent-m must be 500..10000 and divisible by --cell-size-m")
    if not 100 <= args.cell_size_m <= 2000:
        parser.error("--cell-size-m must be 100..2000")
    return args


def main() -> int:
    args = parse_args()
    poi_query = "derived from --input-json"
    open_area_query = "not queried"
    source_generated_at = None
    circular_coverage_radius_m = None
    if args.input_json:
        try:
            input_dataset = json.loads(args.input_json.read_text(encoding="utf-8"))
            source = input_dataset["source"]
            center = input_dataset["requested_location"]
            source_generated_at = input_dataset.get("generated_at")
            poi_elements = []
            for poi in input_dataset["pois"]:
                element = {"type": poi["osm_type"], "id": poi["osm_id"], "tags": poi.get("tags", {})}
                if poi["osm_type"] == "node":
                    element.update({"lat": poi["latitude"], "lon": poi["longitude"]})
                else:
                    element["center"] = {"lat": poi["latitude"], "lon": poi["longitude"]}
                poi_elements.append(element)
            args.lat = float(center["latitude"])
            args.lon = float(center["longitude"])
            circular_coverage_radius_m = int(input_dataset["coverage"]["radius_m"])
            args.extent_m = circular_coverage_radius_m
            bounds = bounds_for(args.lat, args.lon, args.extent_m)
            places, candidates = normalize_elements(poi_elements, open_areas=[], center_lat=args.lat, center_lon=args.lon)
            source = {**source, "derivation": f"Normalized from {args.input_json.name}; source sample generated at {source_generated_at}.", "scope": "Existing circular POI sample; cells are retained only when fully inside its source radius."}
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            print(f"Không đọc được OSM sample {args.input_json}: {type(exc).__name__}", file=sys.stderr)
            return 1
    else:
        bounds = bounds_for(args.lat, args.lon, args.extent_m)
        poi_query = build_poi_query(bounds)
        open_area_query = build_open_area_query(bounds)
        try:
            poi_response = fetch_overpass(poi_query, args.overpass_url)
            area_response = fetch_overpass(open_area_query, args.overpass_url)
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        places, candidates = normalize_elements(
            poi_response["elements"],
            open_areas=area_response["elements"],
            center_lat=args.lat,
            center_lon=args.lon,
        )
        source = {
            "provider": "OpenStreetMap via Overpass API",
            "endpoint": args.overpass_url,
            "documentation": "https://wiki.openstreetmap.org/wiki/Overpass_API/Language_Guide",
            "license": "Open Database License (ODbL) 1.0",
            "attribution": "© OpenStreetMap contributors",
            "poi_query": poi_query,
            "open_area_query": open_area_query,
            "scope": "Square WGS84 bbox projected locally to approximate meter-sized cells; not city-wide coverage.",
        }
    cafes = [place for place in places if place["poi_type"] == "cafe"]
    cells = make_grid(places, args.lat, args.lon, args.extent_m, args.cell_size_m, circular_coverage_radius_m=circular_coverage_radius_m)
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    south, west, north, east = bounds
    coverage = {
        "center": {"latitude": args.lat, "longitude": args.lon},
        "bbox": {"south": south, "west": west, "north": north, "east": east},
        "half_width_m": args.extent_m,
        "shape": "circle" if circular_coverage_radius_m is not None else "square_bbox",
        "cell_size_m": args.cell_size_m,
        "cell_count": len(cells),
        "poi_element_count": len(places),
        "cafe_count": len(cafes),
        "waiting_candidate_count": len(candidates),
        "minimum_open_area_candidate_m2": MIN_OPEN_AREA_M2,
    }
    cafe_dataset = {
        "schema_version": "1.0",
        "dataset_id": "gigca_hcmc_demo_osm_cafe_grid",
        "generated_at": generated_at,
        "coverage": coverage,
        "source_generated_at": source_generated_at,
        "source": source,
        "grid_method": {
            "shape": "square",
            "cell_size_m": args.cell_size_m,
            "projection_note": "Local meter approximation using latitude/longitude scale at the sample center; suitable for this small HCMC demo area, not precision surveying.",
            "cafe_poi_count": "Number of OSM cafe POIs whose point falls inside this cell.",
            "cafe_density_per_km2": "cafe_poi_count divided by cell area in square kilometers.",
            "cafe_poi_count_within_500m": "Number of cafe POIs within 500m of the cell center; null where source coverage does not include the full neighborhood.",
        },
        "cells": cells,
        "limitations": [
            "POI count/density describes mapped cafe features, not passenger demand, booking probability, or driver competition.",
            "The square extent is a local sample area and does not represent city-wide data.",
            "Cafe mapping may be incomplete or duplicated where point and building features are separately mapped.",
        ],
    }
    candidate_dataset = {
        "schema_version": "1.0",
        "dataset_id": "gigca_hcmc_demo_osm_waiting_location_candidates",
        "generated_at": generated_at,
        "coverage": coverage,
        "source_generated_at": source_generated_at,
        "source": source,
        "candidate_policy": {
            "candidate_status": "unverified_candidate",
            "permission_to_wait": "unknown",
            "categories": ["parking", "church", "place_of_worship", "school", "shopping_center", "open_land", "park", "fuel_station", "transit_or_rest_area"],
            "open_land_min_area_m2": MIN_OPEN_AREA_M2,
            "note": "OSM tags generate candidates for review only; they do not prove public access, motorcycle access, waiting/parking permission, or suitable operating hours.",
        },
        "candidates": candidates,
        "limitations": [
            "Way/relation point coordinates are approximate centers/centroids, not entrances or curbside waiting points.",
            "School, church, mall, park, fuel-station, and open-land candidates may be private, restricted, crowded, or unsuitable at particular times.",
            "Verify access, permission, hours, and exact safe staging position before showing a place as a confirmed waiting spot.",
        ],
    }
    pois_dataset = {
        "schema_version": "1.0",
        "dataset_id": "gigca_hcmc_demo_osm_poi_spatial_context",
        "generated_at": generated_at,
        "coverage": coverage,
        "source_generated_at": source_generated_at,
        "source": source,
        "pois": places,
        "limitations": [
            "This dataset is a local sample and does not estimate ride-hailing demand.",
            "Area and way coordinates may be approximations; use verified entrances for operational guidance.",
        ],
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "osm_poi_spatial_hcmc.json": pois_dataset,
        "osm_poi_grid_hcmc.json": cafe_dataset,
        "osm_waiting_candidates_hcmc.json": candidate_dataset,
    }
    for filename, dataset in outputs.items():
        path = args.output_dir / filename
        path.write_text(json.dumps(dataset, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}")
    counts = Counter(place["poi_type"] for place in places)
    print(f"POIs: {len(places)}; cafes: {len(cafes)}; grid cells: {len(cells)}; waiting candidates: {len(candidates)}")
    print("Candidate types: " + ", ".join(f"{name}={count}" for name, count in sorted(counts.items())))
    print("Waiting permission remains unknown for every candidate; verify before operational use.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
