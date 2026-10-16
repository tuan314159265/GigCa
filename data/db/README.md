# PostgreSQL/PostGIS MVP

The database stores normalized data by grain. It is an operational spatial database for the MVP, not a star-schema warehouse. `data/engine_interface.py` is the Engine-facing adapter and emits the JSON shape in `contracts/engine_input.schema.json` (schema `0.1`). Engine code can import it directly:

```python
from data.engine_interface import EngineDataInterface

source = EngineDataInterface.from_env()
snapshot = source.get_engine_input(
    "hcmc_demo_point_01",
    rain_tolerance_level="medium",  # optional driver preference
)
```

The returned snapshot contains rain probability and precipitation, cafe counts/density by grid cell, unverified waiting-place candidates, recent route summaries, and recent traffic segments in the Engine's top-level `traffic[]` shape. Traffic is marked `partial` because the observations are not map-matched or route-wide; stale/empty traffic is marked `stale`/`missing`. Incident observations remain `not_integrated` until the Engine has an incident input type and scorer.

## Local setup

For local development, the repository includes a PostGIS container in `compose.yaml`. Set a local password (never commit it), then start the service and apply the migrations:

Fish:

```fish
python -m pip install -r data/db/requirements.txt
set -gx POSTGRES_PASSWORD 'choose-a-local-password'
docker compose up -d postgis
set -gx GIGCA_DATABASE_URL "postgresql://gigca:$POSTGRES_PASSWORD@localhost:5432/gigca"
python -m data.db.migrate
python -m data.db.load_samples
```

Bash/Zsh:

```sh
python -m pip install -r data/db/requirements.txt
export POSTGRES_PASSWORD='choose-a-local-password'
docker compose up -d postgis
export GIGCA_DATABASE_URL="postgresql://gigca:${POSTGRES_PASSWORD}@localhost:5432/gigca"
python -m data.db.migrate
python -m data.db.load_samples
```

When copying commands from a terminal example, omit the shell prompt character (`$`). If `docker compose up` reports that it cannot connect to the Docker daemon, start Docker Desktop/the Docker service first; that is separate from shell variable syntax.

For a remote database, set `GIGCA_DATABASE_URL` to its connection string instead. The first migration needs permission to enable the PostGIS extension. The compose file binds the database port to localhost and stores its data in the Docker volume `gigca_postgis_data`.

To export a snapshot for manual inspection:

```sh
python -m data.db.export_snapshot \
  --area-id hcmc_demo_point_01 \
  --output data/processed/db_engine_input_snapshot.json
```

The sample loader reads only the checked-in JSON samples. It does not store provider response bodies, read ignored TomTom raw files, or fetch APIs. It creates one demo area named `hcmc_demo_point_01`. Real ETL extractors should write normalized rows and an `etl_run` record using the same table grains.

Live MVP writes use `data.db.live_observations`: the web server stores normalized TomTom Flow rows on upstream `/api/traffic` fetches when the database is configured; `python -m data.etl.refresh_weather` stores each scheduled Open-Meteo forecast vintage. Neither path stores raw provider response bodies. The weather refresh expects the demo area to have been initialized with `python -m data.db.load_samples`.

## Tables and row grains

| Table | Grain / use |
|---|---|
| `etl_run` | One extraction, sample load, or retention run; holds source dataset IDs and run state. |
| `provider_payload` | Optional provider response metadata/body. Body insert is rejected unless `terms_verified` is true; set a provider-specific expiry. |
| `area` | One configured Engine query area and its representative point/coverage. |
| `weather_forecast` | One provider forecast vintage, area, and valid hour; keeps issue, fetch, and valid times separately. |
| `poi_feature` | One deduplicated source POI feature. |
| `poi_grid_cell` | One cafe-density grid cell in one area. |
| `waiting_location_candidate` | One mapped candidate place; access and permission remain unverified. |
| `route_observation` | One route summary. Geometry and raw payload are omitted by the demo loader. |
| `traffic_flow_observation` | One returned road segment at one flow poll time. |
| `traffic_incident_observation` | One provider incident in one poll. |
| `traffic_flow_hourly_summary` | One hour, provider, and coarse geohash area after compaction. |
| `traffic_incident_daily_summary` | One day/provider/category/severity group after compaction. |

Each observation references its producing `etl_run` by foreign key. Times are stored as `TIMESTAMPTZ`; spatial columns use SRID 4326 and have GiST indexes where queried spatially.

## Cleanup and retention

Run `python -m data.db.retention` on a schedule after applying migrations. It compacts traffic-flow details older than 30 days into hourly median summaries, compacts incident observations older than 30 days into daily summaries, then deletes the detail. Summaries are retained for 365 days. Route summaries are deleted after 7 days, weather vintages after their valid and issue times are both more than 30 days old, and provider payloads only when their explicit `expires_at` has passed. These are project defaults; provider terms can require shorter retention or prohibit storage entirely. Rain rollups are not created in this MVP.

The cleanup command is not scheduled automatically by this repository; the database owner should schedule it only after checking source terms and choosing the poll cadence.
