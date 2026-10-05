#!/usr/bin/env python3
"""Fetch one local TomTom traffic flow and incident snapshot.

The API key is read from API_TOMTOM in the repository .env file and is never
written to sample metadata or printed. Responses are saved under data/raw,
which is intentionally ignored by Git while provider retention terms are being
verified.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
OUTPUT_DIR = ROOT / "data" / "raw" / "tomtom"
FLOW_ENDPOINT = "https://api.tomtom.com/traffic/services/4/flowSegmentData/absolute/10/json"
INCIDENT_ENDPOINT = "https://api.tomtom.com/traffic/services/5/incidentDetails"
DOCS = {
    "flow": "https://docs.tomtom.com/traffic-api/documentation/tomtom-maps/v1/traffic-flow/flow-segment-data",
    "incidents": "https://docs.tomtom.com/traffic-api/documentation/tomtom-maps/v1/traffic-incidents/incident-details",
}
POINT = "10.7769,106.7009"  # latitude,longitude
BBOX = "106.69,10.77,106.72,10.79"  # minLon,minLat,maxLon,maxLat
INCIDENT_FIELDS = (
    "{incidents{type,geometry{type,coordinates},properties{"
    "id,iconCategory,magnitudeOfDelay,events{description},startTime,endTime,"
    "from,to,length,delay,timeValidity}}}"
)


def read_api_key() -> str:
    """Read the key from .env without printing or persisting it."""
    if not ENV_PATH.is_file():
        raise RuntimeError("Repository .env file was not found")

    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, value = stripped.split("=", 1)
        if name.strip() == "API_TOMTOM":
            key = value.strip().strip("\"'")
            if key:
                return key
            break
    raise RuntimeError("API_TOMTOM is missing or empty in .env")


def get_json(endpoint: str, params: dict[str, str], api_key: str) -> dict:
    query = {**params, "key": api_key}
    request = Request(
        f"{endpoint}?{urlencode(query)}",
        headers={"Accept": "application/json", "User-Agent": "GigCaDataProbe/0.1"},
    )
    try:
        with urlopen(request, timeout=25) as response:
            payload = response.read()
            status = response.status
    except HTTPError as exc:
        # Do not print the URL or provider body: both can contain request data.
        raise RuntimeError(f"TomTom returned HTTP {exc.code}") from None
    except URLError as exc:
        raise RuntimeError(f"TomTom request failed ({type(exc.reason).__name__})") from None

    try:
        decoded = json.loads(payload)
    except json.JSONDecodeError:
        raise RuntimeError("TomTom returned a non-JSON response") from None
    if not isinstance(decoded, dict):
        raise RuntimeError("TomTom response was not a JSON object")
    return {"http_status": status, "body": decoded}


def main() -> int:
    try:
        api_key = read_api_key()
        fetched_at = datetime.now(timezone.utc)
        stamp = fetched_at.strftime("%Y%m%dT%H%M%SZ")

        flow_params = {"point": POINT, "unit": "KMPH", "openLr": "true"}
        incidents_params = {
            "bbox": BBOX,
            "fields": INCIDENT_FIELDS,
            "language": "en-GB",
            "timeValidityFilter": "present",
        }
        flow_result = get_json(FLOW_ENDPOINT, flow_params, api_key)
        incident_result = get_json(INCIDENT_ENDPOINT, incidents_params, api_key)

        records = (
            (
                f"tomtom_flow_segment_hcmc_{stamp}.json",
                {
                    "schema_version": "0.1",
                    "dataset_id": "tomtom_flow_segment_hcmc",
                    "fetched_at": fetched_at.isoformat(),
                    "source": {
                        "provider": "TomTom Traffic API",
                        "endpoint": FLOW_ENDPOINT,
                        "service_version": "4",
                        "documentation": DOCS["flow"],
                        "freshness_note": "Request-time snapshot of provider traffic data; not a continuous stream.",
                    },
                    "request": {"point_lat_lon": POINT, "unit": "KMPH", "openLr": True, "zoom": 10, "style": "absolute"},
                    "http_status": flow_result["http_status"],
                    "response": flow_result["body"],
                },
            ),
            (
                f"tomtom_incidents_hcmc_{stamp}.json",
                {
                    "schema_version": "0.1",
                    "dataset_id": "tomtom_incidents_hcmc",
                    "fetched_at": fetched_at.isoformat(),
                    "source": {
                        "provider": "TomTom Traffic API",
                        "endpoint": INCIDENT_ENDPOINT,
                        "service_version": "5",
                        "documentation": DOCS["incidents"],
                        "freshness_note": "Request-time snapshot of present incidents; not a continuous stream.",
                    },
                    "request": {"bbox_min_lon_lat_max_lon_lat": BBOX, "time_validity_filter": "present"},
                    "http_status": incident_result["http_status"],
                    "response": incident_result["body"],
                },
            ),
        )

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        for filename, document in records:
            path = OUTPUT_DIR / filename
            path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(path.relative_to(ROOT))

        flow = flow_result["body"].get("flowSegmentData", {})
        incidents = incident_result["body"].get("incidents", [])
        print(
            "Flow: HTTP 200; current={} km/h, free-flow={} km/h, confidence={}.".format(
                flow.get("currentSpeed"), flow.get("freeFlowSpeed"), flow.get("confidence")
            )
        )
        print(f"Incidents: HTTP 200; {len(incidents)} records in the test bounding box.")
        print("Saved under data/raw/tomtom/ (local-only, ignored by Git).")
        return 0
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
