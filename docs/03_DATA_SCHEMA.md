# Data schema (draft)

Use GeoJSON for map layers and versioned JSON/GeoJSON snapshots as the initial interchange format, as proposed in the plan. Each dataset must include a sidecar manifest or equivalent metadata with:

| Field | Meaning |
|---|---|
| `dataset_id` | Stable dataset identifier. |
| `schema_version` | Version of this data contract. |
| `source` | Provider or generation method, with attribution/link where applicable. |
| `license` | Usage conditions; do not ingest until understood. |
| `coverage` | Geographic and temporal coverage. |
| `collected_at` | When this snapshot was collected, in ISO 8601 with timezone. |
| `valid_time` | Time the observation describes, if different from collection time. |
| `units` | Units for all numeric measurements. |
| `quality` | Known gaps, freshness, and validation notes. |

## Candidate map cell

Draft properties: `cell_id`, geometry, `snapshot_id`, `observed_at`, optional weather observations (precipitation rate, apparent temperature, wind/gust), optional road congestion observations keyed to directed road edges, optional POI/event references, and `data_quality`.

Do not conflate these distinct concepts:

- **Road congestion:** observed or estimated condition on an edge for a time window.
- **Road graph:** nodes and directed edges with distance/time/cost attributes.
- **Demand/booking probability:** requires suitable historical or live trip/request data and a validated model; it cannot be derived just from the share of nearby congested edges.
- **POI/event presence:** context for a location, not proof of passenger demand.

Use explicit `null` or omit an unavailable measure; document which behavior the API selects. Synthetic fixtures must say so in metadata and UI.

## Cafe-density grid and waiting-location candidates

The Engine input may include `areas[].poi_density_grid.cells[]` with `cell_id`, metric `cell_size_m`, polygon geometry, `cafe_poi_count`, `cafe_density_per_km2`, and `cafe_poi_count_within_500m`. The current sample uses 250 m cells inside the available OSM radius. Cell counts describe mapped cafes and must not be treated as booking probability.

`areas[].waiting_location_candidates[]` contains place candidates derived from OSM tags, including parking, schools, places of worship, malls, parks/open land, fuel stations, and rest/transit areas. Every item currently uses `candidate_status="unverified_candidate"` and `permission_to_wait="unknown"`. A POI center or polygon centroid does not identify a legal waiting position or entrance; candidate data alone must not be presented as confirmed safe/allowed waiting spots.
