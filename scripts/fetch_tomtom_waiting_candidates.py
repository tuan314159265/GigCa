#!/usr/bin/env python3
"""Fetch unverified parking/school/church/mall POI candidates from TomTom Search."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "data" / "raw" / "tomtom_search" / "tomtom_waiting_candidates_hcmc.json"
API_ENDPOINT = "https://api.tomtom.com/search/2/poiSearch"
SEARCHES = {
    "parking": "parking",
    "school": "school",
    "church": "church",
    "shopping_center": "mall",
}
VERIFICATION_NEEDED = [
    "public_or_owner_access",
    "motorcycle_access",
    "waiting_or_parking_permission",
    "opening_hours",
    "exact_entrance_or_staging_point",
]


def read_api_key() -> str:
    env_path = ROOT / ".env"
    if not env_path.is_file():
        raise RuntimeError("Thiếu file .env chứa API_TOMTOM.")
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, value = stripped.split("=", 1)
        if name.strip() == "API_TOMTOM":
            key = value.strip().strip("\"'")
            if key:
                return key
    raise RuntimeError("API_TOMTOM chưa được cấu hình trong .env.")


def get_json(query: str, lat: float, lon: float, radius_m: int, key: str) -> dict:
    params = urlencode(
        {
            "lat": lat,
            "lon": lon,
            "radius": radius_m,
            "limit": 100,
            "language": "vi-VN",
            "key": key,
        }
    )
    request = Request(
        f"{API_ENDPOINT}/{query}.json?{params}",
        headers={"Accept": "application/json", "User-Agent": "GigCaPOISample/0.1"},
    )
    try:
        with urlopen(request, timeout=25) as response:
            payload = response.read()
    except HTTPError as exc:
        raise RuntimeError(f"TomTom POI Search HTTP {exc.code} for category {query}.") from None
    except URLError as exc:
        raise RuntimeError(f"TomTom POI Search network error ({type(exc.reason).__name__}) for category {query}.") from None
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        raise RuntimeError(f"TomTom returned invalid JSON for category {query}.") from None
    if not isinstance(data, dict):
        raise RuntimeError(f"TomTom response for category {query} is not an object.")
    return data


def parse_args() -> object:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lat", type=float, default=10.7769)
    parser.add_argument("--lon", type=float, default=106.7009)
    parser.add_argument("--radius-m", type=int, default=1500)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if not -90 <= args.lat <= 90 or not -180 <= args.lon <= 180:
        parser.error("Coordinates are outside WGS84 bounds")
    if not 100 <= args.radius_m <= 5000:
        parser.error("--radius-m must be 100..5000")
    return args


def main() -> int:
    args = parse_args()
    try:
        api_key = read_api_key()
        candidates: list[dict] = []
        category_counts: dict[str, int] = {}
        truncated_categories: list[str] = []
        fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        for poi_type, query in SEARCHES.items():
            response = get_json(query, args.lat, args.lon, args.radius_m, api_key)
            results = response.get("results", [])
            category_counts[poi_type] = len(results)
            if len(results) >= 100:
                truncated_categories.append(poi_type)
            for item in results:
                position = item.get("position") or {}
                poi = item.get("poi") or {}
                address = item.get("address") or {}
                if position.get("lat") is None or position.get("lon") is None:
                    continue
                candidate_id = item.get("id")
                if not candidate_id:
                    continue
                candidates.append(
                    {
                        "candidate_id": f"tomtom_{candidate_id}",
                        "source_provider": "TomTom Search API",
                        "source_id": candidate_id,
                        "name": poi.get("name") or address.get("freeformAddress"),
                        "poi_type": poi_type,
                        "role": "waiting_location_candidate",
                        "candidate_status": "unverified_candidate",
                        "permission_to_wait": "unknown",
                        "latitude": position["lat"],
                        "longitude": position["lon"],
                        "point_method": "provider_poi_coordinate",
                        "area_m2": None,
                        "categories": poi.get("categories", []),
                        "address": address.get("freeformAddress"),
                        "verification_needed": VERIFICATION_NEEDED,
                    }
                )
    except (OSError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    dataset = {
        "schema_version": "1.0",
        "dataset_id": "gigca_hcmc_demo_tomtom_waiting_location_candidates",
        "generated_at": fetched_at,
        "requested_location": {"latitude": args.lat, "longitude": args.lon},
        "coverage": {"radius_m": args.radius_m, "result_limit_per_category": 100},
        "source": {
            "provider": "TomTom Search API",
            "endpoint": API_ENDPOINT,
            "documentation": "https://docs.tomtom.com/search-api/documentation/search-service/poi-search",
            "attribution": "© TomTom",
            "terms_status": "Check account plan terms before redistribution or production retention.",
            "query_categories": SEARCHES,
        },
        "category_counts": category_counts,
        "truncated_categories": truncated_categories,
        "candidates": candidates,
        "candidate_policy": {
            "candidate_status": "unverified_candidate",
            "permission_to_wait": "unknown",
            "verification_needed": VERIFICATION_NEEDED,
            "note": "Search results identify nearby place candidates; they do not prove access, motorcycle entry, permission to wait/park, or a safe staging position.",
        },
        "limitations": [
            "Search result limits can truncate dense categories; inspect truncated_categories and do not treat results as complete coverage.",
            "Candidate coordinates may represent POI locations or entrances according to provider data; verify exact staging point before use.",
            "This is not an availability feed, ride-hailing demand signal, or confirmation that a driver may wait there.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(dataset, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.output.relative_to(ROOT) if args.output.is_relative_to(ROOT) else args.output}")
    print("Results by type: " + ", ".join(f"{kind}={count}" for kind, count in category_counts.items()))
    print(f"Candidates: {len(candidates)}; categories at result limit: {', '.join(truncated_categories) or 'none'}")
    print("Every result remains unverified; permission to wait is unknown.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
