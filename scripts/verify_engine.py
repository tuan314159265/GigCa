#!/usr/bin/env python3
"""Run the Decision Engine verification suite."""

import sys
from pathlib import Path

if sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.src.verify import run_verification

if __name__ == "__main__":
    raise SystemExit(run_verification())
