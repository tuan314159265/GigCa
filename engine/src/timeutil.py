"""Time helpers. The engine is pure: 'now' always comes from input.generated_at, never the system clock."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone


def parse_iso(value: str | None) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None


def to_local_naive(dt: datetime, utc_offset_min: int) -> datetime:
    """Convert to naive local time. Naive inputs are assumed to already be local (Open-Meteo Asia/Ho_Chi_Minh)."""
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone(timedelta(minutes=utc_offset_min))).replace(tzinfo=None)
    return dt


def parse_local(value: str | None, utc_offset_min: int) -> datetime | None:
    dt = parse_iso(value)
    return to_local_naive(dt, utc_offset_min) if dt else None


def hhmm(dt: datetime) -> str:
    return dt.strftime("%H:%M")


_INTERVAL = re.compile(r"(\d{1,2}):(\d{2})\s*[-–]\s*(\d{1,2}):(\d{2})")
_DAY_TOKEN = re.compile(r"\b(Mo|Tu|We|Th|Fr|Sa|Su|PH|SH)\b")


def is_open_at(opening_hours: str | None, when: datetime | None) -> bool | None:
    """True/False if opening_hours can be evaluated at `when` (local time); None when unknown.

    Supports '24/7' and daily 'HH:MM-HH:MM[, HH:MM-HH:MM]' (overnight ranges allowed). Anything richer
    (weekday-specific rules, holidays) returns None — we never guess.
    """
    if not opening_hours or when is None:
        return None
    text = opening_hours.strip()
    if text.replace(" ", "").lower() == "24/7":
        return True
    stripped = re.sub(r"\bMo\s*-\s*Su\b", "", text)
    if _DAY_TOKEN.search(stripped):
        return None
    pairs = _INTERVAL.findall(stripped)
    if not pairs:
        return None
    now_min = when.hour * 60 + when.minute
    for h1, m1, h2, m2 in pairs:
        start, end = int(h1) * 60 + int(m1), int(h2) * 60 + int(m2)
        if end == start:
            continue
        if start < end and start <= now_min < end:
            return True
        if start > end and (now_min >= start or now_min < end):
            return True
    return False
