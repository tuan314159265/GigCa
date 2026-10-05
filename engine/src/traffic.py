"""Traffic analysis from edge observations: speed ratio vs free-flow, freshness filter, no invented street names."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from engine.src.timeutil import parse_local
from engine.src.types import TrafficEdge

_LABEL_CLASS = {"thong_thoang": "smooth", "dong_xe": "slow", "un_tac": "congested"}


@dataclass(frozen=True)
class TrafficAnalysis:
    usable: bool
    total_edges: int = 0
    used_edges: int = 0
    stale_edges: int = 0
    unusable_edges: int = 0
    smooth: list[str] = field(default_factory=list)
    slow: list[str] = field(default_factory=list)
    congested: list[str] = field(default_factory=list)
    mean_speed_kmh: float | None = None
    mean_ratio: float | None = None
    newest_age_min: int | None = None
    details: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def edge_label(edge_id: str) -> str:
    """Readable label derived ONLY from the edge id (the input has no street names)."""
    core = re.sub(r"^edge[_\-]?", "", edge_id, flags=re.I)
    core = re.sub(r"[_\-]?\d+$", "", core)
    core = core.replace("_", " ").replace("-", " ").strip()
    return core.title() if core else edge_id


def analyze_traffic(
    edges: list[TrafficEdge],
    traffic_status: str | None,
    now_local: datetime | None,
    cfg: dict[str, Any],
    utc_offset_min: int,
) -> TrafficAnalysis:
    if traffic_status not in ("available", "partial") or not edges:
        return TrafficAnalysis(usable=False, total_edges=len(edges))

    smooth, slow, cong = [], [], []
    details: list[dict[str, Any]] = []
    speeds: list[tuple[float, float | None]] = []
    ratios: list[float] = []
    stale = unusable = undated = 0
    ages: list[int] = []
    for e in edges:
        obs = parse_local(e.observed_at, utc_offset_min)
        if obs is None:
            undated += 1
        elif now_local is not None:
            age = (now_local - obs).total_seconds() / 60.0
            if age > float(cfg["max_age_min"]):
                stale += 1
                continue
            ages.append(max(0, int(age)))

        ratio = None
        cls = None
        cs, ff = e.current_speed_kmh, e.free_flow_speed_kmh
        if cs is not None and ff is not None and ff > 0 and cs >= 0:
            ratio = cs / ff
            cls = "smooth" if ratio >= cfg["smooth_ratio"] else ("congested" if ratio < cfg["congested_ratio"] else "slow")
        elif e.congestion_level in _LABEL_CLASS:
            cls = _LABEL_CLASS[e.congestion_level]
        if cls is None:
            unusable += 1
            continue
        label = edge_label(e.edge_id)
        {"smooth": smooth, "slow": slow, "congested": cong}[cls].append(label)
        if cs is not None:
            speeds.append((float(cs), e.length_m))
        if ratio is not None:
            ratios.append(ratio)
        details.append(
            {"edge_id": e.edge_id, "class": cls, "ratio": None if ratio is None else round(ratio, 2), "speed_kmh": cs}
        )

    used = len(details)
    mean_speed = None
    if speeds:
        if all(l is not None and l > 0 for _, l in speeds):
            total = sum(l for _, l in speeds)  # type: ignore[misc]
            mean_speed = sum(v * l for v, l in speeds) / total  # type: ignore[operator]
        else:
            mean_speed = sum(v for v, _ in speeds) / len(speeds)
    warnings: list[str] = []
    if stale:
        warnings.append(f"Giao thông: loại {stale} đoạn quá cũ (> {cfg['max_age_min']} phút)")
    if undated:
        warnings.append(f"Giao thông: {undated} đoạn không có observed_at — không kiểm chứng được độ mới")
    if unusable:
        warnings.append(f"Giao thông: {unusable} đoạn thiếu tốc độ/mức ùn — không dùng")
    return TrafficAnalysis(
        usable=used > 0,
        total_edges=len(edges),
        used_edges=used,
        stale_edges=stale,
        unusable_edges=unusable,
        smooth=sorted(smooth),
        slow=sorted(slow),
        congested=sorted(cong),
        mean_speed_kmh=mean_speed,
        mean_ratio=(sum(ratios) / len(ratios)) if ratios else None,
        newest_age_min=min(ages) if ages else None,
        details=details,
        warnings=warnings,
    )
