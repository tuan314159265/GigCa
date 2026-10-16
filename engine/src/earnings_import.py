"""Earnings text -> trip-log candidates (what an OCR / vision step produces from a screenshot of the driver's own history).

The OCR itself is outside the engine (any OCR or vision model can produce the text); this module turns the text into
`trip_log` entries WITHOUT inventing anything:
- a line is parsed for time (HH:MM), distance (km), amount (đ / k), duration (phút) and a pickup place;
- a candidate becomes a trip only when every required field is present AND the pickup place resolves to coordinates in the
  caller's gazetteer (a table of known place -> lat/lng, e.g. the engine's zone names); otherwise it is returned in
  `needs_input` with the exact missing fields — nothing is defaulted;
- the amount on a screenshot may be the GROSS fare (before the platform's cut), while `net_vnd` must be what the driver got:
  every trip carries `amount_to_confirm=True` and the UI must ask. The result is a proposal, never silently merged.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from engine.src.intake import _NUM, _fold, _money, _to_number

_TIME = re.compile(r"(?<!\d)([01]?\d|2[0-3])[:h]([0-5]\d)(?!\d)")
_KM = re.compile(_NUM + r"\s*km\b")
_MIN = re.compile(r"(\d{1,3})\s*(?:phút|phut|min|')")
_MONEY = re.compile(_NUM + r"\s*(k|nghìn|nghin|ngàn|ngan|đ|d|vnd|đồng|dong)(?![a-zà-ỹ])")
_SPLIT = re.compile(r"\s*(?:→|->|—>|=>|➜|>)\s*")
REQUIRED = ("started_at", "net_vnd", "duration_min", "distance_km", "pickup")


@dataclass
class ImportResult:
    trips: list[dict[str, Any]] = field(default_factory=list)       # ready for payload["trip_log"] after the driver confirms
    needs_input: list[dict[str, Any]] = field(default_factory=list)  # {"line", "missing": [...], "parsed": {...}}
    ignored_lines: int = 0


def _norm_place(s: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", _fold(s)).split())


def parse_earnings_text(text: str, date: str, gazetteer: dict[str, tuple[float, float]], tz: str = "+07:00") -> ImportResult:
    """`date` is YYYY-MM-DD (the screenshot's day, supplied by the caller — never guessed). One trip per non-empty line."""
    gz = {_norm_place(k): v for k, v in gazetteer.items()}
    res = ImportResult()
    n = 0
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        low = _fold(line)
        tm, km, mn, mo = _TIME.search(low), _KM.search(low), _MIN.search(low), _MONEY.search(low)
        if not (tm or km or mo):
            res.ignored_lines += 1  # a header / footer / noise line
            continue
        parsed: dict[str, Any] = {}
        if tm:
            parsed["started_at"] = f"{date}T{int(tm.group(1)):02d}:{tm.group(2)}:00{tz}"
        if km:
            parsed["distance_km"] = _to_number(km.group(1))
        if mn:
            parsed["duration_min"] = float(mn.group(1))
        if mo:
            parsed["net_vnd"] = _money(mo.group(1), mo.group(2))
        head = _SPLIT.split(re.sub(r"^\W*\d{1,2}[:h]\d{2}\W*", "", low), maxsplit=1)[0]
        place = _norm_place(re.split(r"[|·•,;]", head)[0])
        coords = next((v for k, v in gz.items() if k and (k == place or k in place or place in k) and place), None)
        if place:
            parsed["pickup"] = place
        missing = [f for f in REQUIRED if f not in parsed]
        if coords is None and "pickup" in parsed:
            missing.append("pickup_coordinates")
        if missing:
            res.needs_input.append({"line": line, "missing": missing, "parsed": parsed})
            continue
        n += 1
        res.trips.append({
            "trip_id": f"import_{date}_{n:03d}", "started_at": parsed["started_at"],
            "pickup_lat": coords[0], "pickup_lng": coords[1], "net_vnd": parsed["net_vnd"],
            "duration_min": parsed["duration_min"], "distance_km": parsed["distance_km"],
            "amount_to_confirm": True,  # the amount may be gross (before platform fees): the driver must confirm it is net
        })
    return res
