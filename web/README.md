# GigCa Data Explorer

A local data explorer for inspecting ETL snapshots and live map layers.

## Run locally

From the repository root, create the virtual environment, generate the processed snapshot if needed, and start the local web server:

```bash
python3 -m venv .venv
.venv/bin/python -m data.etl.pipeline
.venv/bin/python -m web.server
```

Open <http://localhost:8000/web/>. The server serves the local snapshot dashboard and same-origin API proxies for TomTom map tiles, motorcycle routing, POI search, and traffic flow/incidents. Traffic is requested on demand with a 45-second in-process cache; when `GIGCA_DATABASE_URL` is configured, each upstream Flow fetch is stored as a normalized observation in PostGIS. The rain layer reads the latest scheduled forecast stored in PostGIS; refresh it with `python -m data.etl.refresh_weather` (see [`../data/etl/README.md`](../data/etl/README.md)). TomTom credentials are read from the root `.env` file on the server and are not sent to browser JavaScript. Configure `API_TOMTOM` in `.env` before starting the server.

The map starts around the HCMC demo point. Toggle live cafe POIs, the static cafe-density grid, OSM/TomTom waiting-location candidates, traffic/incidents, and rain layers; pick a route origin and destination by clicking the map, then calculate a TomTom motorcycle route. The displayed rain marker is a forecast at one coordinate, not a rain overlay covering the map. Waiting candidates include parking, schools, churches, and malls; the local TomTom response is read from ignored `data/raw/tomtom_search/`. These markers are unverified and do not indicate that stopping or parking is allowed. OSM open-land candidates are supported by the extractor, but the latest Overpass query timed out, so they are not present in the current sample. Traffic values are provider snapshots from the time of the request.

The map uses Leaflet from the unpkg CDN and TomTom map tiles through the local proxy, so the browser needs internet access. The local server binds to `127.0.0.1` by default. Set `GIGCA_WEB_HOST` or `GIGCA_WEB_PORT` only when you intentionally need another bind address or port.

The dashboard also reads `data/processed/engine_input_snapshot.json`, local provider sample files, and the source registry. Use the refresh button to reload these JSON samples and the live map data. For a fresh local Open-Meteo sample, install `.venv/bin/python -m pip install -r data/etl/requirements.txt`, run `.venv/bin/python -m data.etl.pipeline --refresh-weather`, then use the refresh button.
