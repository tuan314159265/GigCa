# GigCa ETL (MVP)

This first pipeline is an offline ETL over the checked-in provider samples. It provides a reproducible path from source JSON to the draft Decision Engine input contract while live provider checks are still in progress.

```text
data/samples/*_hcmc.json
        ↓ Extract: read source snapshots
        ↓ Validate: required fields, coordinates, rain units/ranges, route response
        ↓ Transform: normalize fields and derive POI counts/status/readiness
        ↓ Load: data/processed/engine_input_snapshot.json
```

Run from the repository root:

```bash
python3 -m venv .venv
.venv/bin/python -m data.etl.pipeline
```

The default command is offline. To refresh just the weather source through Open-Meteo's official Python client, install its optional dependencies into a repository virtual environment and pass `--refresh-weather`:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r data/etl/requirements.txt
.venv/bin/python -m data.etl.pipeline --refresh-weather
```

Weather requests use a one-hour cache and retry transient errors. Pandas is not required. The POI and routing adapters remain sample-only until their live endpoints and fallback choices are verified.

Optional paths:

```bash
.venv/bin/python -m data.etl.pipeline --samples-dir data/samples --output data/processed/engine_input_snapshot.json
```

The default output is ignored by Git because `data/processed/` is generated data. The pipeline is offline and does not call provider APIs. It marks an expired weather forecast as `stale`; it does not let old sample data look current just because a new ETL run was generated.

## Provider selection and fallback

Provider candidates and the status of the initial live checks are tracked in [`config/source_registry.json`](config/source_registry.json). Select providers per dataset, not as one global winner. A fallback can be enabled only after checking that its fields, meaning, spatial coverage, freshness, license, quota, and attribution meet the same use case. Do not average weather probabilities or substitute route duration for traffic without a separately validated method.

Open-Meteo's official Python client is [`openmeteo-requests`](https://github.com/open-meteo/python-requests). The weather extractor uses that client with caching and retry support; Pandas is optional, so values are normalized directly into GigCa JSON. The free Open-Meteo API is limited to non-commercial use; verify the correct plan before any commercial use.

## Current API check (2026-10-01)

- Open-Meteo forecast: HTTP 200; requested hourly precipitation and precipitation probability were present.
- OSRM public demo: HTTP 200 / `Ok`; one route returned. Its `driving` profile is not verified for motorcycles and does not provide live traffic.
- Overpass main endpoint: HTTP 504 during this check due server overload. A secondary public endpoint timed out. The stored POI sample remains usable for offline ETL only; live POI extraction is not verified.
- Goong, OpenWeather, and TomTom: not live-checked; they remain candidates, not configured backups.

These checks confirm that particular requests responded at the time of checking. They do not establish service-level reliability, full city coverage, commercial-use rights, or accuracy for driver recommendations.

## Persistence direction

The current MVP persists samples and processed snapshots as JSON files; it does not require a database. If the project begins retaining live snapshots, prefer PostgreSQL + PostGIS for normalized area/road/time queries, with provider responses kept in a `JSONB` raw-ingestion table for traceability. Match weather to areas by spatial cell and `valid_time`, and traffic to directed road edges by `edge_id` and `observed_at`; do not require provider feeds to share foreign keys. Keep TTL/retention rules for volatile forecasts and route responses. MongoDB is also capable of geospatial and time-series storage, but the expected spatial joins between areas, POIs, road edges, and observations make PostGIS the simpler first database for this project.
