"""Type definitions for the GigCa Decision Engine.

Matches contracts/engine_input.schema.json and engine/spec.md Section 8.
Strict nullability is preserved: missing data is None, never silently coerced to 0.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

ObjectiveKey = Literal[
    "max_trip_value",
    "maintain_position",
    "rest_spot",
    "safety_comfort",
]

Confidence = Literal["none", "low", "medium"]

ReadinessMode = Literal["FULL", "PARTIAL", "INSUFFICIENT"]

DataStatusValue = Literal[
    "available",
    "partial",
    "missing",
    "stale",
    "not_integrated",
]

ObjectiveStatus = Literal[
    "available",
    "partial",
    "insufficient_data",
]

RainToleranceLevel = Literal["low", "medium", "high"]


@dataclass(frozen=True)
class WeatherHour:
    valid_time: str
    precipitation_mm: float | None
    precipitation_probability_pct: float | None


@dataclass(frozen=True)
class RoutingSample:
    destination_id: str
    profile: str
    route_distance_m: float | None
    route_duration_s: float | None


@dataclass(frozen=True)
class AreaSample:
    area_id: str
    spatial_scope: str
    representative_point: dict[str, float]
    area_name: str | None = None
    poi_counts_by_category: dict[str, int] = field(default_factory=dict)
    routing_samples: list[RoutingSample] = field(default_factory=list)
    weather_hourly: list[WeatherHour] = field(default_factory=list)
    trip_value: dict[str, Any] | None = None
    destination_distribution: dict[str, Any] | None = None
    traffic_feed: dict[str, Any] | None = None


@dataclass(frozen=True)
class PoiCandidate:
    poi_id: str
    name: str
    latitude: float
    longitude: float
    category: str
    subcategory: str | None = None
    verified: bool = False
    parking_allowed: bool = False
    opening_hours: str | None = None
    tags: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class TrafficEdge:
    edge_id: str
    from_node: str | None = None
    to_node: str | None = None
    length_m: float | None = None
    current_speed_kmh: float | None = None
    free_flow_speed_kmh: float | None = None
    congestion_level: str | None = None  # "thong_thoang", "dong_xe", "un_tac"
    observed_at: str | None = None


@dataclass(frozen=True)
class EngineInput:
    weather_hourly: list[WeatherHour]
    areas: list[AreaSample]
    traffic: list[TrafficEdge]
    data_status: dict[str, DataStatusValue]
    objective_readiness: dict[ObjectiveKey, ObjectiveStatus]
    poi_candidates: list[PoiCandidate] = field(default_factory=list)
    snapshot_id: str = "mock_snapshot"
    generated_at: str = "2026-09-27T00:00:00+07:00"
    data_label: str | None = None  # Nhãn nguồn (vd. simulation_label) — dữ liệu demo phải được gắn nhãn
    is_demo: bool = False
    data_status_reasons: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class DriverContext:
    current_lat: float
    current_lng: float
    idle_duration_min: int = 15
    horizon_min: int = 60
    max_reposition_km: float = 3.0


@dataclass(frozen=True)
class DriverPreferences:
    rain_tolerance_level: RainToleranceLevel = "medium"
    goal_weights: dict[ObjectiveKey, float] | None = None


@dataclass(frozen=True)
class TripValueCandidate:
    """Candidate area evaluated for propensity of long-distance and high-value trips (spec.md 5.1)."""
    area_id: str
    area_name: str = ""
    expected_net_value_vnd: float | None = None
    gross_fare_vnd: float | None = None
    estimated_duration_min: int | None = None
    demand_index: float | None = None
    avg_trip_distance_km: float | None = None  # Cự ly cuốc trung bình xuất phát từ khu vực này
    long_trip_rate_pct: float | None = None  # Tỷ lệ cuốc đi xa (> 8-10km hoặc đi sân bay/liên quận)
    hotspot_features: list[str] = field(default_factory=list)  # Đặc trưng điểm đón: sảnh khách sạn, tòa nhà hạng A, ga xe...
    source_confidence: Confidence = "none"
    explanation: str | None = None
    # --- Nâng cấp v2: đều có thể truy vết về dữ liệu đầu vào + tham số cấu hình ---
    rank: int | None = None
    reposition_km: float | None = None  # ƯỚC TÍNH từ đường chim bay x detour_factor, KHÔNG phải routing
    reposition_min: float | None = None
    reposition_cost_vnd: float | None = None
    wait_min: float | None = None  # avg_next_wait_min của khu vực, None nếu không đủ dữ liệu cho mọi ứng viên
    yield_vnd_per_hour: float | None = None  # (cước ròng - chi phí dịch chuyển) / giờ (chạy + dịch chuyển + chờ)
    pareto_optimal: bool | None = None  # không bị khu vực khác vượt trội đồng thời về năng suất và demand_index


@dataclass(frozen=True)
class PositionCandidate:
    """Candidate area evaluated for post-trip position retention (spec.md 5.2)."""
    area_id: str
    area_name: str = ""
    position_score: float = 0.0  # Thang điểm 0 - 100
    favorable_dropoff_pct: float = 0.0  # Tỷ lệ trả khách ở vùng trung tâm thuận lợi
    avg_next_wait_min: int = 0  # Thời gian chờ ước tính trước cuốc kế tiếp
    source_confidence: Confidence = "none"
    explanation: str | None = None
    rank: int | None = None
    reposition_km: float | None = None  # ƯỚC TÍNH, xem TripValueCandidate.reposition_km


@dataclass(frozen=True)
class RestSpotCandidate:
    """Rest spot candidate with real routing sample and verified metadata (spec.md 5.3)."""
    poi_id: str
    name: str
    category: str
    distance_m: float | None
    duration_s: float | None
    verified: bool = False
    parking_allowed: bool = False
    opening_hours: str | None = None
    suitability_tier: str = "tieu_chuan"  # "toi_uu", "kha", "tieu_chuan"
    synergy_tags: list[str] = field(default_factory=list)
    explanation: str | None = None
    rank: int | None = None
    fit_score: float | None = None  # 0-1, cao hơn = phù hợp hơn (thời gian di chuyển thật + loại điểm dừng)
    is_open: bool | None = None  # None = không xác định được từ opening_hours
    arrival_time: str | None = None  # giờ địa phương dự kiến đến nơi (HH:MM)



@dataclass(frozen=True)
class RainFlag:
    """Hourly rain condition compared against driver tolerance (spec.md 5.4)."""
    valid_time: str
    prob_pct: float | None
    mm: float | None
    exceeds_tolerance: bool
    severity: str = "none"  # "none" | "exceeds" | "heavy"
    minutes_from_now: int | None = None  # phút từ thời điểm hiện tại tới đầu khung giờ (0 = đang diễn ra)
    window: str | None = None  # khung giờ dự báo thực sự được áp dụng, vd. "15:00–16:00"


@dataclass(frozen=True)
class PlanStep:
    """A concrete sequential action step in a direction's plan."""
    step_number: int
    time_window: str  # e.g. "Ngay lập tức (0 - 5 phút)", "16:00 - 16:30"
    action: str  # e.g. "Chốt vị trí tại Trục Bến Thành - Lê Lợi"
    instruction: str  # Chi tiết chỉ dẫn hành động
    expected_outcome: str  # Kết quả kỳ vọng sau bước này


@dataclass(frozen=True)
class DirectionPlan:
    """A complete, actionable strategic plan for a specific objective direction.
    
    Analogous to a complete travel itinerary (e.g. Economical Plan vs Max Experience Plan).
    Contains target location, sequential operational steps, projected key metrics, and trade-offs.
    """
    plan_id: ObjectiveKey
    direction_title: str  # e.g. "Hướng 1: Kế Hoạch Săn Cuốc Giá Trị Cao (Max Trip Value)"
    objective_focus: str  # e.g. "Tối đa hóa doanh thu ròng trên từng chuyến xe"
    summary: str  # Tóm tắt chiến lược hành động
    target_location: str  # Địa điểm hoặc khu vực mục tiêu chính
    steps: list[PlanStep]  # Trình tự các bước hành động cụ thể theo thời gian
    key_metrics: dict[str, Any]  # Các chỉ số đo lường dự phóng
    trade_offs: str  # Đánh đổi & rủi ro cần biết
    contingency_fallback: str  # Phương án dự phòng nếu gặp trở ngại


@dataclass(frozen=True)
class SynthesizedAction:
    """Deprecated: Cross-objective synthesis action kept for backward compatibility."""
    action_type: str
    headline: str
    recommended_target: str | None
    urgency: str
    deadline_time: str | None
    strategic_reason: str


@dataclass(frozen=True)
class ObjectiveResult:
    """Output block for one of the 4 independent objectives.
    
    Contains the complete DirectionPlan for this objective, plus status and underlying evidence.
    """
    objective: ObjectiveKey
    status: ObjectiveStatus
    confidence: Confidence
    plan: DirectionPlan | None = None
    candidates: list[Any] = field(default_factory=list)
    context_only: list[dict[str, Any]] | None = None
    rain_flags: list[RainFlag] | None = None
    safe_window_min: int | None = None
    peak_rain_time: str | None = None
    weather_action_signal: str | None = None
    traffic_note: str | None = None
    avoid_zones: list[str] | None = None
    safe_corridors: list[str] | None = None
    caveat: str | None = None
    reason_for_insufficiency: str | None = None
    excluded: list[dict[str, Any]] | None = None  # ứng viên bị loại + lý do (không loại âm thầm)
    robustness: dict[str, Any] | None = None  # kiểm tra độ vững của hạng 1 khi giả định dao động


@dataclass(frozen=True)
class DriverRecommendationOutput:
    """Top-level recommendation output containing 4 complete directional action plans.
    
    Tài xế là người quyết định chọn 1 trong 4 kế hoạch này tùy theo ưu tiên và thể trạng.
    Engine không chọn thay tài xế.
    """
    generated_at: str
    objectives: dict[ObjectiveKey, ObjectiveResult]
    assumptions_used: list[str]
    final_note: str
    synthesized_action: SynthesizedAction | None = None
    direction_priority: list[dict[str, Any]] | None = None  # THỨ TỰ xét 4 hướng (không phải điểm tổng)
    data_quality_warnings: list[str] = field(default_factory=list)

