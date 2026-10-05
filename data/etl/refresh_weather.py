"""Fetch and persist one scheduled Open-Meteo rain forecast vintage."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from data.db.live_observations import save_weather_forecast
from data.etl.extractors.open_meteo import fetch_weather_sample


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = ROOT / "data" / "processed" / "weather_refresh"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--area-id", default="hcmc_demo_point_01")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    sample_path = fetch_weather_sample(args.output_dir)
    dataset = json.loads(sample_path.read_text(encoding="utf-8"))
    stored_rows = save_weather_forecast(dataset, area_id=args.area_id)
    print(f"Stored {stored_rows} hourly Open-Meteo forecast rows for {args.area_id}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
