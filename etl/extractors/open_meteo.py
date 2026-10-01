"""Fetch and cache the rain forecast with Open-Meteo's official Python client."""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[2]
API_URL = "https://api.open-meteo.com/v1/forecast"
TIMEZONE = "Asia/Ho_Chi_Minh"


def fetch_weather_sample(samples_dir: Path) -> Path:
    """Refresh the local weather sample; dependencies are optional for offline runs."""
    try:
        import openmeteo_requests
        import requests_cache
        from retry_requests import retry
    except ImportError as exc:
        raise RuntimeError(
            "Live weather extraction dependencies are missing. Install with "
            ".venv/bin/python -m pip install -r etl/requirements.txt"
        ) from exc

    output_path = samples_dir / "open_meteo_weather_hcmc.json"
    existing: dict[str, Any] = {}
    if output_path.exists():
        existing = json.loads(output_path.read_text(encoding="utf-8"))
    location = existing.get("requested_location", {"latitude": 10.7769, "longitude": 106.7009})
    latitude = location.get("latitude", 10.7769)
    longitude = location.get("longitude", 106.7009)

    cache_path = ROOT / ".cache" / "open_meteo"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_session = requests_cache.CachedSession(str(cache_path), expire_after=3600)
    retry_session = retry(cache_session, retries=5, backoff_factor=0.2)
    client = openmeteo_requests.Client(session=retry_session)
    response = client.weather_api(
        API_URL,
        params={
            "latitude": latitude,
            "longitude": longitude,
            "hourly": ["precipitation", "precipitation_probability"],
            "forecast_days": 2,
            "timezone": TIMEZONE,
            "precipitation_unit": "mm",
        },
    )[0]

    hourly_response = response.Hourly()
    if hourly_response is None:
        raise RuntimeError("Open-Meteo response is missing the requested hourly variables")
    try:
        precipitation_values = hourly_response.Variables(0).ValuesAsNumpy().tolist()
        probability_values = hourly_response.Variables(1).ValuesAsNumpy().tolist()
    except (AttributeError, IndexError, TypeError) as exc:
        raise RuntimeError("Open-Meteo response is missing the requested hourly variables") from exc
    count = min(len(precipitation_values), len(probability_values))
    if count == 0:
        raise RuntimeError("Open-Meteo returned no hourly precipitation values")

    start_epoch = hourly_response.Time()
    interval_seconds = hourly_response.Interval()

    def finite_or_none(value: Any) -> float | None:
        number = float(value)
        return number if math.isfinite(number) else None

    hourly = []
    for index in range(count):
        local_time = datetime.fromtimestamp(
            start_epoch + index * interval_seconds, tz=timezone.utc
        ).astimezone(ZoneInfo(TIMEZONE))
        hourly.append(
            {
                "valid_time": local_time.isoformat(timespec="minutes"),
                "precipitation_mm": finite_or_none(precipitation_values[index]),
                "precipitation_probability_pct": finite_or_none(probability_values[index]),
            }
        )

    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    dataset = {
        "schema_version": "1.0",
        "dataset_id": "gigca_hcmc_demo_open_meteo_weather",
        "generated_at": generated_at,
        "requested_location": {"latitude": latitude, "longitude": longitude},
        "source": {
            "provider": "Open-Meteo",
            "endpoint": API_URL,
            "documentation": "https://open-meteo.com/en/docs",
            "license": "CC BY 4.0; free API is non-commercial only; confirm plan for commercial use",
            "attribution": "Weather data by Open-Meteo.com",
            "timezone": TIMEZONE,
            "provider_location": {
                "latitude": response.Latitude(),
                "longitude": response.Longitude(),
                "elevation_m": response.Elevation(),
            },
            "hourly_units": {
                "time": "iso8601",
                "precipitation_mm": "mm",
                "precipitation_probability_pct": "%",
            },
        },
        "hourly": hourly,
        "limitations": [
            "Forecast grid coordinates may differ from requested coordinates.",
            "Forecast values are not guaranteed observations at every street.",
        ],
    }
    samples_dir.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(dataset, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return output_path
