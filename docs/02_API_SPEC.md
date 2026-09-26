# API specification (draft)

Backend target: FastAPI with Pydantic request/response models. API prefix: `/v1`. These endpoints are proposed for module coordination; implementation and exact schemas remain to be agreed.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Liveness/status of the API service. |
| `GET` | `/v1/coverage` | Available data layers, geographic coverage, update times, and known gaps. |
| `GET` | `/v1/cells?bbox=...` | Map-ready candidate cells/areas for the requested viewport. |
| `POST` | `/v1/recommendations` | Rank waiting/rest locations from the driver origin, preferences, and selected time horizon. |
| `GET` | `/v1/provenance?snapshot_id=...` | Describe data snapshots and their source metadata. |

Recommendation request draft:

```json
{
  "schema_version": "1.0",
  "origin": {"lat": 10.776, "lon": 106.701},
  "start_time": "2026-09-26T09:00:00+07:00",
  "horizon_min": 60,
  "goals": ["maintain_position", "safety_comfort", "rest_spot"],
  "preferences": {
    "max_reposition_km": 3,
    "avoid_heavy_rain": true,
    "prefer_shaded_or_rest_areas": false
  }
}
```

The example coordinates and values are illustrative only. `max_trip_value` must not be presented as an operational recommendation until a legitimate, sufficiently reliable trip-value signal exists. No field should imply access to platform booking, fare, or vehicle-density APIs without verified access.

Response should include `request_id`, `snapshot_id`, `data_as_of`, `status`, ranked recommendations, score explanations, sources/assumptions, and warnings. Exact response schema is pending; keep `contracts/` synchronized when agreed.

