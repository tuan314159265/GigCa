"""Time-anchored rain analysis.

Fixes the naive 'take the first N list items' approach:
- the window is [now, now+horizon] where now = input.generated_at converted to local time;
- each forecast value is mapped to the hour it really describes (config weather.slot_convention);
- coverage of the horizon is measured, and missing coverage is reported instead of being read as 'good weather'.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from engine.src.timeutil import hhmm, parse_local
from engine.src.types import RainFlag, WeatherHour

SIGNAL_NOW = "TRU_MUA_NGAY"
SIGNAL_BEFORE = "DI_CHUYEN_TRUOC_KHI_MUA"
SIGNAL_OK = "THOI_TIET_THUAN_LOI"
SIGNAL_UNKNOWN = "KHONG_DU_DU_BAO"


@dataclass(frozen=True)
class WeatherAnalysis:
    flags: list[RainFlag] = field(default_factory=list)
    signal: str = SIGNAL_UNKNOWN
    first_exceed_min: int | None = None
    first_exceed_window: str | None = None
    peak_flag: RainFlag | None = None
    safe_window_min: int | None = None
    covered_min: int = 0
    coverage_ratio: float = 0.0
    heavy: bool = False
    anchored: bool = True
    warnings: list[str] = field(default_factory=list)


def _clean(value: float | None, lo: float, hi: float | None) -> float | None:
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v != v or v < lo or (hi is not None and v > hi):
        return None
    return v


def analyze_weather(
    hours: list[WeatherHour],
    now_local: datetime | None,
    horizon_min: int,
    thr_prob: float,
    thr_mm: float,
    cfg: dict[str, Any],
    utc_offset_min: int,
) -> WeatherAnalysis:
    warnings: list[str] = []
    preceding = cfg["slot_convention"] == "preceding_hour"
    slots: list[tuple[datetime, datetime, WeatherHour, float | None, float | None]] = []
    bad_time = bad_value = 0
    for h in hours:
        t = parse_local(h.valid_time, utc_offset_min)
        if t is None:
            bad_time += 1
            continue
        prob = _clean(h.precipitation_probability_pct, 0.0, 100.0)
        mm = _clean(h.precipitation_mm, 0.0, None)
        if (h.precipitation_probability_pct is not None and prob is None) or (
            h.precipitation_mm is not None and mm is None
        ):
            bad_value += 1
        start, end = (t - timedelta(hours=1), t) if preceding else (t, t + timedelta(hours=1))
        slots.append((start, end, h, prob, mm))
    if bad_time:
        warnings.append(f"Thời tiết: bỏ {bad_time} mốc có valid_time không đọc được")
    if bad_value:
        warnings.append(f"Thời tiết: {bad_value} giờ có giá trị ngoài miền hợp lệ (xác suất 0-100%, mm >= 0) — coi như thiếu")
    slots.sort(key=lambda s: s[0])

    anchored = now_local is not None
    now = now_local if anchored else (slots[0][0] if slots else None)
    if not anchored:
        warnings.append("Không xác định được thời điểm hiện tại từ generated_at — tạm neo vào giờ dự báo đầu tiên")
    if now is None or horizon_min <= 0:
        return WeatherAnalysis(signal=SIGNAL_UNKNOWN, anchored=anchored, warnings=warnings)

    end_window = now + timedelta(minutes=horizon_min)
    flags: list[RainFlag] = []
    covered = 0.0
    for start, end, h, prob, mm in slots:
        if end <= now or start >= end_window:
            continue
        if prob is None and mm is None:
            continue
        covered += (min(end, end_window) - max(start, now)).total_seconds() / 60.0
        exceeds = (prob is not None and prob >= thr_prob) or (mm is not None and mm >= thr_mm)
        heavy = mm is not None and mm >= thr_mm * float(cfg["heavy_mm_ratio"])
        flags.append(
            RainFlag(
                valid_time=h.valid_time,
                prob_pct=prob,
                mm=mm,
                exceeds_tolerance=exceeds,
                severity="heavy" if heavy else ("exceeds" if exceeds else "none"),
                minutes_from_now=max(0, int((start - now).total_seconds() // 60)),
                window=f"{hhmm(start)}–{hhmm(end)}",
            )
        )

    coverage = min(1.0, covered / horizon_min)
    exceeding = [f for f in flags if f.exceeds_tolerance]
    first = min(exceeding, key=lambda f: f.minutes_from_now) if exceeding else None
    peak = max(exceeding, key=lambda f: (f.mm if f.mm is not None else -1.0, f.prob_pct or -1.0)) if exceeding else None
    heavy_any = any(f.severity == "heavy" for f in flags)

    if first is not None:
        signal = SIGNAL_NOW if first.minutes_from_now == 0 else SIGNAL_BEFORE
        safe_window = first.minutes_from_now
    elif not flags or coverage < float(cfg["min_coverage_ratio"]):
        signal, safe_window = SIGNAL_UNKNOWN, None
    else:
        signal, safe_window = SIGNAL_OK, int(round(covered))
    if signal in (SIGNAL_OK, SIGNAL_BEFORE) and coverage < 1.0:
        warnings.append(
            f"Dự báo chỉ phủ ~{coverage*100:.0f}% khung {horizon_min} phút tới — phần còn lại chưa có dữ liệu"
        )
    return WeatherAnalysis(
        flags=flags,
        signal=signal,
        first_exceed_min=first.minutes_from_now if first else None,
        first_exceed_window=first.window if first else None,
        peak_flag=peak,
        safe_window_min=safe_window,
        covered_min=int(round(covered)),
        coverage_ratio=coverage,
        heavy=heavy_any,
        anchored=anchored,
        warnings=warnings,
    )
