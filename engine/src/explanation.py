"""Explanation Layer — generates verifiable, traceable explanations.

Implements Section 6 of engine/spec.md.
Rules:
- Format: [action/observation] + [exact number] + [source].
- No generic, untraceable statements.
- Every explanation must trace back to concrete numbers in the input.
"""

from __future__ import annotations

import math


def format_rest_spot_explanation(
    name: str,
    distance_m: float,
    duration_s: float,
    profile: str = "mẫu routing",
    verified: bool = False,
    parking_allowed: bool = False,
) -> str:
    """Format explanation for a rest spot candidate with exact numbers and source."""
    duration_min = max(1, round(duration_s / 60))
    dist_rounded = round(distance_m)
    if verified and parking_allowed:
        status = "đã xác minh và ghi nhận cho phép đỗ xe máy"
    elif verified:
        status = "đã xác minh nhưng chưa ghi nhận cho phép đỗ xe máy"
    else:
        status = "thuộc nhóm ứng viên nghỉ chưa xác minh quyền đỗ xe"
    return f"{name} cách vị trí hiện tại {dist_rounded}m (~{duration_min} phút theo {profile}), {status}."


def format_rain_flag_explanation(
    valid_time: str,
    prob_pct: float,
    mm: float,
    tolerance_level: str,
    threshold_prob: float,
    threshold_mm: float,
) -> str:
    """Format explanation for a rain forecast flag exceeding tolerance."""
    time_display = valid_time.split("T")[-1] if "T" in valid_time else valid_time
    return (
        f"Dự báo mưa lúc {time_display} đạt {prob_pct:.0f}% ({mm:.1f}mm từ Open-Meteo), "
        f"vượt mức chịu mưa '{tolerance_level}' (ngưỡng {threshold_prob:.0f}% / {threshold_mm:.1f}mm)."
    )
