"""Engine configuration: every threshold and weight lives here or in config/engine_config.json.

Implements spec.md Section 2 Principle 5: thresholds are parameters, never hidden in logic.

- DEFAULTS is the complete fallback.
- config/engine_config.json is deep-merged on top (only the keys you want to override are needed).
- A broken config file is a loud error, never a silent fallback to defaults.
"""

from __future__ import annotations

import copy
import json
import warnings
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[2]
CONFIG_FILE = ROOT_DIR / "config" / "engine_config.json"

DEFAULT_REST_CATEGORIES = ["cafe", "gas_station", "parking", "rest_area", "toilet"]

DEFAULT_RAIN_TOLERANCE_THRESHOLDS = {
    "low": {"prob_pct": 30.0, "mm": 0.5, "note": "Đề xuất tạm — chưa hiệu chỉnh"},
    "medium": {"prob_pct": 55.0, "mm": 2.0, "note": "Đề xuất tạm — chưa hiệu chỉnh"},
    "high": {"prob_pct": 75.0, "mm": 5.0, "note": "Đề xuất tạm — chưa hiệu chỉnh"},
}

DEFAULT_OBJECTIVE_DATA_DEPENDENCIES = {
    "max_trip_value": ["trip_value", "booking_and_destinations"],
    "maintain_position": ["booking_and_destinations", "routing"],
    "rest_spot": ["poi", "verified_waiting_places"],
    "safety_comfort": ["weather", "traffic"],
}

DEFAULT_FINAL_NOTE = (
    "Đây là gợi ý dựa trên dữ liệu hiện có, không phải quyết định thay bạn — "
    "hãy tự kiểm tra trước khi hành động, đặc biệt với các mục còn đang thiếu dữ liệu."
)

DEFAULTS: dict[str, Any] = {
    "rest_categories": DEFAULT_REST_CATEGORIES,
    "rain_tolerance_thresholds": DEFAULT_RAIN_TOLERANCE_THRESHOLDS,
    "objective_data_dependencies": DEFAULT_OBJECTIVE_DATA_DEPENDENCIES,
    "time": {"local_utc_offset_minutes": 420},
    "geo": {
        "detour_factor": 1.3,
        "reposition_speed_kmh": 20.0,
        "reposition_cost_vnd_per_km": 2000,
        "at_area_radius_m": 500,
    },
    "routing": {"origin_tolerance_m": 800},
    "weather": {
        "area_scope_km": 5.0,
        "pre_rain_buffer_min": 15,
        "min_coverage_ratio": 0.5,
        "heavy_mm_ratio": 1.5,
        "slot_convention": "preceding_hour",
    },
    "traffic": {"smooth_ratio": 0.8, "congested_ratio": 0.5, "max_age_min": 30},
    "max_trip_value": {"trip_accept_ratio": 0.8, "max_wait_min": 20},
    "maintain_position": {"wait_penalty_per_min": 1.5, "reposition_penalty_per_km": 2.0},
    "rest_spot": {
        "max_candidates": 5,
        "weights": {"travel_time": 0.6, "category_fit": 0.4},
        "travel_time_ref_s": 600,
        "long_idle_min": 25,
        "category_fit_long_idle": {
            "cafe": 1.0, "rest_area": 1.0, "parking": 0.8, "toilet": 0.5, "gas_station": 0.5,
        },
        "category_fit_short_idle": {
            "gas_station": 1.0, "toilet": 1.0, "cafe": 0.8, "rest_area": 0.8, "parking": 0.6,
        },
        "tier_cutoffs": {"toi_uu": 0.75, "kha": 0.5},
        "rest_duration_min_by_idle": [
            {"idle_ge": 0, "rest_min": 15},
            {"idle_ge": 25, "rest_min": 25},
            {"idle_ge": 45, "rest_min": 30},
        ],
        "category_aliases": {
            "fuel": "gas_station", "toilets": "toilet", "motorcycle_parking": "parking",
            "coffee_shop": "cafe", "rest": "rest_area",
        },
        "amenity_tags": {
            "cafe": ["có_chỗ_ngồi", "đồ_uống_nghỉ_ngơi"],
            "parking": ["bãi_đỗ_xe_máy"],
            "toilet": ["vệ_sinh_công_cộng"],
            "gas_station": ["nạp_nhiên_liệu", "dừng_chân_nhanh"],
            "rest_area": ["điểm_nghỉ_chân"],
        },
    },
    "robustness": {"perturbation_pct": 20.0, "top1_share_min": 0.8, "tie_margin_pct": 5.0},
    "priority": {"rain_lead_min": 45, "fatigue_idle_min": 45},
    "final_note": DEFAULT_FINAL_NOTE,
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def _unknown_keys(base: dict[str, Any], override: dict[str, Any], prefix: str = "") -> list[str]:
    """Keys present in override but not in defaults (catches typos). 'note' is always allowed."""
    problems: list[str] = []
    for key, value in override.items():
        path = f"{prefix}{key}"
        if key == "note":
            continue
        if key not in base:
            problems.append(path)
        elif isinstance(value, dict) and isinstance(base[key], dict) and key not in (
            "rain_tolerance_thresholds", "category_fit_long_idle", "category_fit_short_idle",
            "category_aliases", "amenity_tags", "objective_data_dependencies",
        ):
            problems.extend(_unknown_keys(base[key], value, path + "."))
    return problems


def validate_config(cfg: dict[str, Any]) -> list[str]:
    """Return a list of human-readable problems; empty list means the config is coherent."""
    problems: list[str] = []
    th = cfg["rain_tolerance_thresholds"]
    for a, b in (("low", "medium"), ("medium", "high")):
        for field in ("prob_pct", "mm"):
            if float(th[a][field]) > float(th[b][field]):
                problems.append(f"rain_tolerance_thresholds: {a}.{field} > {b}.{field} (phải tăng dần low<=medium<=high)")
    tr = cfg["traffic"]
    if not 0 < tr["congested_ratio"] <= tr["smooth_ratio"] <= 1.0:
        problems.append("traffic: cần 0 < congested_ratio <= smooth_ratio <= 1")
    if cfg["geo"]["detour_factor"] < 1.0:
        problems.append("geo.detour_factor phải >= 1.0 (đường bộ không ngắn hơn đường chim bay)")
    if cfg["geo"]["reposition_speed_kmh"] <= 0:
        problems.append("geo.reposition_speed_kmh phải > 0")
    w = cfg["rest_spot"]["weights"]
    if any(float(v) < 0 for v in w.values()) or sum(float(v) for v in w.values()) <= 0:
        problems.append("rest_spot.weights phải không âm và có tổng > 0")
    cut = cfg["rest_spot"]["tier_cutoffs"]
    if not cut["toi_uu"] >= cut["kha"]:
        problems.append("rest_spot.tier_cutoffs: toi_uu phải >= kha")
    if cfg["weather"]["slot_convention"] not in ("preceding_hour", "following_hour"):
        problems.append("weather.slot_convention phải là preceding_hour hoặc following_hour")
    rb = cfg["robustness"]
    if not 0 < rb["perturbation_pct"] < 100 or not 0 < rb["top1_share_min"] <= 1:
        problems.append("robustness: perturbation_pct trong (0,100), top1_share_min trong (0,1]")
    return problems


def load_config(path: Path | None = None) -> dict[str, Any]:
    """Load DEFAULTS deep-merged with the JSON file. Raises on invalid JSON or incoherent values."""
    cfg_path = path or CONFIG_FILE
    cfg = copy.deepcopy(DEFAULTS)
    if cfg_path.exists():
        with open(cfg_path, "r", encoding="utf-8") as f:
            override = json.load(f)  # invalid JSON -> loud error on purpose
        typos = _unknown_keys(DEFAULTS, override)
        if typos:
            warnings.warn(f"engine_config.json có khóa không được engine dùng: {typos}", stacklevel=2)
        cfg = _deep_merge(cfg, override)
    problems = validate_config(cfg)
    if problems:
        raise ValueError("engine_config không hợp lệ: " + "; ".join(problems))
    return cfg


ENGINE_CONFIG = load_config()
REST_CATEGORIES: list[str] = ENGINE_CONFIG["rest_categories"]
RAIN_TOLERANCE_THRESHOLDS: dict[str, dict[str, float | str]] = ENGINE_CONFIG["rain_tolerance_thresholds"]
OBJECTIVE_DATA_DEPENDENCIES: dict[str, list[str]] = ENGINE_CONFIG["objective_data_dependencies"]
FINAL_NOTE: str = ENGINE_CONFIG["final_note"]

TIME_CFG = ENGINE_CONFIG["time"]
GEO_CFG = ENGINE_CONFIG["geo"]
ROUTING_CFG = ENGINE_CONFIG["routing"]
WEATHER_CFG = ENGINE_CONFIG["weather"]
TRAFFIC_CFG = ENGINE_CONFIG["traffic"]
TRIP_CFG = ENGINE_CONFIG["max_trip_value"]
POSITION_CFG = ENGINE_CONFIG["maintain_position"]
REST_CFG = ENGINE_CONFIG["rest_spot"]
ROBUSTNESS_CFG = ENGINE_CONFIG["robustness"]
PRIORITY_CFG = ENGINE_CONFIG["priority"]
