#!/usr/bin/env python3
"""Fetch one OSRM Table matrix from the demo point to the OSM waiting candidates.

The demo server is best-effort. This records ``driving`` route summaries only;
it does not claim a motorcycle profile, current traffic, or legal wait access.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CANDIDATES = ROOT / "data" / "samples" / "osm_waiting_candidates_hcmc.json"
DEFAULT_WEATHER = ROOT / "data" / "samples" / "open_meteo_weather_hcmc.json"
DEFAULT_OUTPUT = ROOT / "data" / "samples" / "osrm_waiting_candidate_routes_hcmc.json"
TABLE_URL = "https://router.project-osrm.org/table/v1/driving"
DOCS_URL = "https://project-osrm.org/docs/v26.4.0/http#table-service"


class FetchError(RuntimeError):
    pass


def load_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FetchError(f"Cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise FetchError(f"Expected a JSON object: {path}")
    return value


def fetch_routes(candidates_path: Path, weather_path: Path, output_path: Path) -> int:
    candidates_doc = load_object(candidates_path)
    weather_doc = load_object(weather_path)
    candidates = candidates_doc.get("candidates")
    origin = weather_doc.get("requested_location")
    if not isinstance(candidates, list) or not candidates:
        raise FetchError("Candidate sample must contain a non-empty candidates array.")
    if not isinstance(origin, dict) or not all(k in origin for k in ("latitude", "longitude")):
        raise FetchError("Weather sample is missing requested_location coordinates.")

    # Keep only distinct, valid candidate coordinates. Coordinates use OSRM's lon,lat order.
    unique: dict[tuple[float, float], dict[str, Any]] = {}
    for item in candidates:
        try:
            key = (float(item["longitude"]), float(item["latitude"]))
            candidate_id = str(item["candidate_id"])
        except (KeyError, TypeError, ValueError):
            continue
        unique.setdefault(key, {"candidate_id": candidate_id, "longitude": key[0], "latitude": key[1]})
    destinations = list(unique.values())
    if not destinations:
        raise FetchError("No candidate has valid coordinates.")
    if len(destinations) > 99:
        raise FetchError(f"Refusing {len(destinations)} destinations in one public demo request; split it first.")

    coordinates = [(float(origin["longitude"]), float(origin["latitude"]))]
    coordinates.extend((d["longitude"], d["latitude"]) for d in destinations)
    coord_text = ";".join(f"{lon:.7f},{lat:.7f}" for lon, lat in coordinates)
    query = urlencode({
        "sources": "0",
        "destinations": ";".join(str(i) for i in range(1, len(coordinates))),
        "annotations": "distance,duration",
    })
    request = Request(
        f"{TABLE_URL}/{coord_text}?{query}",
        headers={"User-Agent": "GigCa-MVP-data-research/0.1"},
    )
    try:
        with urlopen(request, timeout=45) as response:
            result = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise FetchError(f"OSRM Table request failed: {exc}") from exc
    if result.get("code") != "Ok":
        raise FetchError(f"OSRM Table returned {result.get('code')}: {result.get('message', 'no message')}")
    distances = result.get("distances")
    durations = result.get("durations")
    if not distances or not durations or len(distances[0]) != len(destinations) or len(durations[0]) != len(destinations):
        raise FetchError("OSRM response did not contain a complete distance and duration matrix; no sample written.")

    routes = []
    unreachable = 0
    for index, destination in enumerate(destinations):
        distance = distances[0][index]
        duration = durations[0][index]
        if distance is None or duration is None:
            unreachable += 1
        routes.append({
            "destination_id": destination["candidate_id"],
            "profile": "driving",
            "route_distance_m": distance,
            "route_duration_s": duration,
        })

    output = {
        "schema_version": "1.0",
        "dataset_id": "gigca_hcmc_demo_osrm_waiting_candidate_routes",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "request": {
            "origin": {"latitude": float(origin["latitude"]), "longitude": float(origin["longitude"])},
            "profile": "driving",
            "service": "table",
            "candidate_count": len(destinations),
        },
        "source": {
            "provider": "OSRM public demo server",
            "endpoint": TABLE_URL,
            "documentation": DOCS_URL,
            "license": "Route data based on OpenStreetMap; attribute © OpenStreetMap contributors and OSRM. Check public demo usage policy before production use.",
            "attribution": "Routing by OSRM; map data © OpenStreetMap contributors",
            "profile": "driving",
        },
        "routes": routes,
        "limitations": [
            "One table request from the fixed demo point; route durations/distances describe fastest driving-profile routes, not motorcycle-verified routes.",
            "The public demo server is best-effort, may be rate-limited or withdrawn, and is not a production dependency.",
            "Mapped candidate coordinates may be POI centers, not entrances or permitted waiting locations.",
            f"{unreachable} candidate routes were unreachable; their null measures must stay missing.",
            "This route table is not traffic-aware and does not estimate demand or booking probability.",
        ],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(routes)} route samples ({unreachable} unreachable): {output_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--weather", type=Path, default=DEFAULT_WEATHER)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    try:
        return fetch_routes(args.candidates, args.weather, args.output)
    except FetchError as exc:
        print(f"OSRM route extraction failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
