"""Bridge the Data contract snapshot into the current Decision Engine adapter.

The Engine branch currently reads POIs from a top-level ``pois`` array, while
the shared Data contract puts unverified stops under each area's
``waiting_location_candidates``. This bridge passes those candidates through
the Engine's explicit ``fallback_pois`` hook without marking them verified or
adding fields to the shared JSON contract.

The ``engine`` package must be available in the Python environment (for example,
after the Engine branch is merged into the integration branch).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def load_for_engine(
    snapshot: dict[str, Any],
    *,
    traffic_edges: list[dict[str, Any]] | None = None,
    trip_log: list[dict[str, Any]] | None = None,
):
    """Convert a Data contract snapshot to the Engine's typed ``EngineInput``.

    Existing top-level ``pois`` remain authoritative if present. Otherwise,
    area-scoped waiting candidates are supplied through the Engine's fallback
    parameter. ``traffic_edges`` is an optional Engine-runtime extension because
    contract 0.1 has no traffic field; callers must pass normalized observations
    with a real segment identity and fetch time. ``trip_log`` is likewise an optional runtime extension: the driver's own
    completed trips, used by the Engine's personal model for the earning lenses when no market fare data exists. No mock fares or booking data
    are synthesized here.
    """
    try:
        from engine.src.adapter import load_engine_input_from_dict
        from engine.src.types import PoiCandidate
    except ImportError as exc:
        raise RuntimeError(
            "Decision Engine code is not available. Merge/checkout the Engine package before calling this bridge."
        ) from exc

    fallback_pois: list[PoiCandidate] = []
    if not isinstance(snapshot.get("pois"), list):
        for area in snapshot.get("areas", []):
            for item in area.get("waiting_location_candidates", []):
                tags = item.get("tags") or {}
                fallback_pois.append(
                    PoiCandidate(
                        poi_id=str(item.get("candidate_id", "")),
                        name=item.get("name") or str(item.get("candidate_id", "Ứng viên OSM")),
                        latitude=float(item["latitude"]),
                        longitude=float(item["longitude"]),
                        category=str(item.get("poi_type", "unknown")),
                        subcategory=None,
                        verified=item.get("candidate_status") == "verified",
                        parking_allowed=item.get("permission_to_wait") == "allowed",
                        opening_hours=_tag_string(tags, "opening_hours"),
                        tags={str(key): str(value) for key, value in tags.items() if value is not None},
                    )
                )

    runtime_payload = dict(snapshot)
    if trip_log:
        # Driver-contributed trip log (not part of contract 0.1): started_at, pickup_lat/lng, net_vnd, duration_min,
        # optional dropoff_lat/lng. The Engine rejects incomplete rows and never fills in missing fields.
        runtime_payload["trip_log"] = trip_log
    if traffic_edges:
        runtime_payload["traffic"] = traffic_edges
        statuses = [dict(item) for item in snapshot.get("data_status", []) if isinstance(item, dict)]
        traffic_status = next((item for item in statuses if item.get("dataset") == "traffic"), None)
        if traffic_status:
            traffic_status.update({
                "status": "partial",
                "reason": "One or a few provider segments only; no road-graph matching or citywide coverage.",
            })
        else:
            statuses.append({
                "dataset": "traffic",
                "status": "partial",
                "reason": "One or a few provider segments only; no road-graph matching or citywide coverage.",
            })
        runtime_payload["data_status"] = statuses

    return load_engine_input_from_dict(runtime_payload, fallback_pois=fallback_pois)


def tomtom_flow_to_engine_edge(document: dict[str, Any]) -> dict[str, Any]:
    """Normalize a local TomTom Flow Segment JSON sample for Engine runtime use.

    The ID is a stable hash of the returned segment geometry, not a street name
    or a claim that the provider segment has been matched to GigCa's route graph.
    """
    if document.get("http_status") != 200:
        raise ValueError("TomTom flow sample must have HTTP 200")
    flow = document.get("response", {}).get("flowSegmentData", {})
    current_speed = flow.get("currentSpeed")
    free_flow_speed = flow.get("freeFlowSpeed")
    fetched_at = document.get("fetched_at")
    if current_speed is None or free_flow_speed is None or not fetched_at:
        raise ValueError("TomTom flow sample is missing speed fields or fetched_at")
    coordinates = flow.get("coordinates", {}).get("coordinate", [])
    identity = flow.get("openlr") or json.dumps(coordinates, sort_keys=True, separators=(",", ":"))
    segment_hash = hashlib.sha256(str(identity).encode("utf-8")).hexdigest()[:12]
    return {
        "edge_id": f"tomtom_segment_{segment_hash}",
        "current_speed_kmh": float(current_speed),
        "free_flow_speed_kmh": float(free_flow_speed),
        "observed_at": str(fetched_at),
    }


def _tag_string(tags: dict[str, Any], name: str) -> str | None:
    value = tags.get(name)
    return None if value is None else str(value)
