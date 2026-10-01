# GigCa Data Explorer

A small static dashboard for inspecting the current ETL snapshot and source JSON samples. It intentionally has no map and no frontend framework.

## Run locally

From the repository root, create the virtual environment, generate the processed snapshot if needed, and serve the repository over HTTP:

```bash
python3 -m venv .venv
.venv/bin/python -m etl.pipeline
.venv/bin/python -m http.server 8000
```

Open <http://localhost:8000/web/>. The page reads `data/processed/engine_input_snapshot.json`, the three provider samples, and the source registry. Use the refresh button to reload JSON after rerunning ETL.

The dashboard surfaces stale/partial/missing statuses and sample limitations. It does not calculate recommendations or imply that POIs are legal waiting spots. For a fresh Open-Meteo forecast, install `.venv/bin/python -m pip install -r etl/requirements.txt`, run `.venv/bin/python -m etl.pipeline --refresh-weather`, then use the dashboard refresh button.
