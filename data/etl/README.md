# GigCa ETL (MVP)

This first pipeline is an offline ETL over the checked-in provider samples. It provides a reproducible path from source JSON to the draft Decision Engine input contract while live provider checks are still in progress.

```text
data/samples/*_hcmc.json
        ↓ Extract: read source snapshots
        ↓ Validate: required fields, coordinates, rain units/ranges, route response
        ↓ Transform: normalize fields and derive POI counts, cafe-density grid, waiting candidates/status/readiness
        ↓ Load: data/processed/engine_input_snapshot.json
```

Run from the repository root:

```bash
python3 -m venv .venv
.venv/bin/python -m data.etl.pipeline
```

The default command is offline. When the OSM cafe-grid and waiting-candidate samples exist, it adds their cells/candidates to the Engine input and marks them `partial`. TomTom POI candidates are kept under ignored `data/raw/tomtom_search/` while account retention/sharing terms are unverified; only opt in with `--include-local-tomtom-candidates`, and do not share that generated snapshot until terms are confirmed. To refresh just the weather source through Open-Meteo's official Python client, install its optional dependencies into a repository virtual environment and pass `--refresh-weather`:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r data/etl/requirements.txt
.venv/bin/python -m data.etl.pipeline --refresh-weather
```

Weather requests use a one-hour cache and retry transient errors. Pandas is not required. The POI spatial builder is [`../../scripts/fetch_poi_spatial_data.py`](../../scripts/fetch_poi_spatial_data.py). It derives the grid from cached POIs offline or requests expanded OSM POIs from Overpass. The current cached cafe grid comes from the 2026-09-26 POI sample; expanded live queries timed out on 2026-10-02. Candidates remain unverified until access and waiting permission are checked. Routing remains a route sample, not a verified motorcycle graph.

Optional paths:

```bash
.venv/bin/python -m data.etl.pipeline --samples-dir data/samples --output data/processed/engine_input_snapshot.json
```

The default output is ignored by Git because `data/processed/` is generated data. The pipeline is offline and does not call provider APIs. It marks an expired weather forecast as `stale`; it does not let old sample data look current just because a new ETL run was generated.

## Provider selection and fallback

Provider candidates and the status of the initial live checks are tracked in [`config/source_registry.json`](config/source_registry.json). Select providers per dataset, not as one global winner. A fallback can be enabled only after checking that its fields, meaning, spatial coverage, freshness, license, quota, and attribution meet the same use case. Do not average weather probabilities or substitute route duration for traffic without a separately validated method.

Open-Meteo's official Python client is [`openmeteo-requests`](https://github.com/open-meteo/python-requests). The weather extractor uses that client with caching and retry support; Pandas is optional, so values are normalized directly into GigCa JSON. The free Open-Meteo API is limited to non-commercial use; verify the correct plan before any commercial use.

## Current API check (2026-10-02)

- Open-Meteo forecast: HTTP 200; requested hourly precipitation and precipitation probability were present.
- OSRM public demo: HTTP 200 / `Ok`; one route returned. Its `driving` profile is not verified for motorcycles and does not provide live traffic.
- Overpass main endpoint: HTTP 504 during this check due server overload. A secondary public endpoint timed out. The stored POI sample remains usable for offline ETL only; live POI extraction is not verified.
- TomTom Traffic API key: HTTP 200 for Flow Segment Data v4 and Incident Details v5 at one central-HCMC test point/bounding box. A later fetch returned current speed 6 km/h, free-flow speed 27 km/h, confidence 1.0, and 40 incident records; earlier requests returned different values. This is a live request/response snapshot, not a continuous stream. TomTom says Traffic Flow and Incident products update about once per minute, but the app only sees new values when it polls. Local responses are in ignored `data/raw/tomtom/`; refresh with `python3 scripts/fetch_tomtom_traffic.py`. This does not verify citywide coverage or production suitability. TomTom docs recommend Orbis endpoints for new integrations; check those before implementation.
- Goong and OpenWeather: not live-checked; they remain candidates, not configured backups.

These checks confirm that particular requests responded at the time of checking. They do not establish service-level reliability, full city coverage, commercial-use rights, or accuracy for driver recommendations.

## Persistence and Engine interface

The offline JSON pipeline remains available. For database-backed handoff, use PostgreSQL + PostGIS with migrations and the normalized sample loader in [`../db/README.md`](../db/README.md). `data.engine_interface.EngineDataInterface` returns the shared Engine input contract from persisted rows, including recent traffic observations as top-level `traffic[]` records. Traffic is `partial` when recent provider segments exist because they are not map-matched to route edges; incidents remain outside the Engine input type.

## Live refresh cadence (MVP)

- **Traffic Flow:** fetched on demand by `GET /api/traffic`. Identical map requests use a 45-second in-process cache. On an upstream fetch, the server writes one normalized `traffic_flow_observation` and `etl_run` when `GIGCA_DATABASE_URL` is configured. It does not store the raw TomTom response. If the database is absent/unavailable, the map response still works and includes `persistence.status` so the observation is not silently assumed to be saved. This endpoint requests the segment nearest one coordinate; it is not citywide traffic coverage.
- **Rain forecast:** refresh as a scheduled batch, independent of driver requests. With the database initialized and extractor dependencies installed, run from the repo root:

  ```sh
  .venv/bin/python -m data.etl.refresh_weather --area-id hcmc_demo_point_01
  ```

  The job writes its fetched JSON under ignored `data/processed/weather_refresh/` and appends normalized hourly rows to `weather_forecast`; it does not overwrite the checked-in sample or store raw provider bodies in PostGIS. Run it about once an hour for this MVP. The existing extractor cache also expires after one hour. Schedule the command with cron/systemd and configure `GIGCA_DATABASE_URL` plus database credentials in that job's environment; do not put secrets in the crontab or repository.

Traffic observations are request-triggered, not a background stream. Weather snapshots are time-triggered. Kafka is not part of this MVP pipeline.
