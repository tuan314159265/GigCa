"""Write an Engine input snapshot read from PostgreSQL/PostGIS."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from data.engine_interface import EngineDataInterface


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--area-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--rain-tolerance", choices=("low", "medium", "high"))
    args = parser.parse_args()
    snapshot = EngineDataInterface.from_env().get_engine_input(
        args.area_id, rain_tolerance_level=args.rain_tolerance
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Engine input snapshot written: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
