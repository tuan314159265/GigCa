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
    trip_log: list["TripRecord"] = field(default_factory=list)  # nhật ký chuyến của chính tài xế (tùy chọn)
    driver_profile: "DriverProfile | None" = None  # biểu cước + xe + mục tiêu do CHÍNH tài xế nhập (tùy chọn; thiếu thì dùng biểu cước công bố trong config)
    wait_spells: list["WaitSpell"] = field(default_factory=list)  # các đợt chờ cuốc do app companion ghi (tùy chọn)


@dataclass(frozen=True)
class TripRecord:
    """One completed trip from the DRIVER'S OWN log (user-contributed data, not market data).

    `net_vnd` is income after platform fees, before fuel (tiền thực nhận từ chuyến, KHÔNG gồm thưởng ngày/tip).
    A trip without net_vnd/duration/pickup/start time is rejected by the adapter (reported, never defaulted).
    `distance_km` is the pickup->dropoff distance the driver saw (or a post-trip routing result); when absent the
    personal model may estimate it from the two coordinates (straight line x detour) and says so."""
    trip_id: str
    started_at: str
    pickup_lat: float
    pickup_lng: float
    net_vnd: float
    duration_min: float
    dropoff_lat: float | None = None
    dropoff_lng: float | None = None
    distance_km: float | None = None


@dataclass(frozen=True)
class DriverProfile:
    """What the DRIVER tells us about their tariff, vehicle and goal (never market data).

    Tariff fields describe the CUSTOMER-FACING price list (what the customer pays):
        gross fare = fare_base_vnd                                   if km <= fare_base_km
                   = fare_base_vnd + fare_per_km_vnd·(km − fare_base_km) + fare_per_min_vnd·(moving minutes after fare_base_km)
    and the driver receives `driver_share` of it (net, before fuel). Every field is optional: a missing field stays None and
    the engine falls back to the PUBLISHED tariff in config (`tariff`), labelled as such — never to an invented number."""
    fare_base_vnd: float | None = None  # a — giá mở cửa: trọn gói cho fare_base_km đầu (khách trả)
    fare_per_km_vnd: float | None = None  # b — đơn giá mỗi km tiếp theo (khách trả)
    fuel_l_per_100km: float | None = None
    fuel_price_vnd_per_l: float | None = None
    target_vnd_per_hour: float | None = None  # mục tiêu thu nhập ròng/giờ do tài xế đặt
    fare_base_km: float | None = None  # số km gói trong giá mở cửa (vd. 2 km đầu)
    fare_per_min_vnd: float | None = None  # phụ phí mỗi phút di chuyển sau fare_base_km (khách trả)
    driver_share: float | None = None  # tỷ lệ tài xế thực nhận trên cước khách trả, trong (0, 1]

    @property
    def fuel_cost_vnd_per_km(self) -> float | None:
        """c — only when BOTH fuel inputs are given; otherwise None (the engine then labels its fallback)."""
        if self.fuel_l_per_100km is None or self.fuel_price_vnd_per_l is None:
            return None
        return self.fuel_l_per_100km * self.fuel_price_vnd_per_l / 100.0


WaitEnd = Literal["trip", "offline", "moved"]


@dataclass(frozen=True)
class DriverEconomics:
    """Resolved money parameters the scorers use.

        gross(km, v)  = a + b·max(0, km − k0) + m·max(0, km − k0)/v·60      (khách trả; v = tốc độ chuyến km/h)
        net(km, v)    = s · gross(km, v)                                    (tài xế nhận, trước xăng)
        income        = net − c·km                                          (sau xăng chặng chở khách)

    The per-minute term needs the MOVING minutes after the first k0 km; the engine estimates them as the remaining
    distance divided by the trip speed (learned from the driver's log, or the labelled what-if assumption).
    With k0 = m = 0 and s = 1 this is the old linear model net = a + b·km.

    `tariff_source`: "published_tariff" (config), "driver_input" or "mixed"; `share_source`: "config" or "driver_input";
    `fuel_source`: "driver_input" or "config_default"."""
    fare_base_vnd: float  # a
    fare_per_km_vnd: float  # b
    fuel_cost_vnd_per_km: float  # c
    tariff_source: str
    fuel_source: str
    target_vnd_per_hour: float | None = None
    fare_base_km: float = 0.0  # k0
    fare_per_min_vnd: float = 0.0  # m
    driver_share: float = 1.0  # s
    share_source: str = "config"
    tariff_reference: str | None = None  # nguồn biểu cước công bố (ghi trong config) — để truy vết

    def moving_min_after_base(self, km: float, speed_kmh: float) -> float:
        """Estimated moving minutes after the first k0 km (remaining distance / trip speed)."""
        if speed_kmh <= 0:
            return 0.0
        return max(0.0, km - self.fare_base_km) / speed_kmh * 60.0

    def gross_fare_vnd(self, km: float, minutes_after_base: float) -> float:
        extra_km = max(0.0, km - self.fare_base_km)
        extra_min = max(0.0, minutes_after_base) if extra_km > 0 else 0.0
        return self.fare_base_vnd + self.fare_per_km_vnd * extra_km + self.fare_per_min_vnd * extra_min

    def net_fare_vnd(self, km: float, speed_kmh: float) -> float:
        """What the driver receives for a trip of `km` at `speed_kmh` (before fuel)."""
        return self.driver_share * self.gross_fare_vnd(km, self.moving_min_after_base(km, speed_kmh))

    def net_per_extra_km(self, speed_kmh: float) -> float:
        """Driver's net for each km beyond k0 (per-km price + per-minute price at this speed), before fuel."""
        per_min_as_km = self.fare_per_min_vnd * 60.0 / speed_kmh if speed_kmh > 0 else 0.0
        return self.driver_share * (self.fare_per_km_vnd + per_min_as_km)


@dataclass(frozen=True)
class WaitSpell:
    """One stretch where the driver stood still waiting for a request (recorded by the companion app / GPS trace).

    `ended_by == "trip"` is an observed wait; "offline" and "moved" are CENSORED (the real wait was at least this long),
    so a lunch break no longer counts as a long wait."""
    spell_id: str
    start: str
    end: str
    lat: float
    lng: float
    ended_by: WaitEnd
    rain_mm: float | None = None  # mưa (mm/giờ) lúc bắt đầu chờ, nếu app ghi được; chỉ dùng làm đặc trưng cho mô hình ML


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
    expected_net_value_vnd: float | None = None  # s·cước(d̄_z, v_z): tiền tài xế nhận/chuyến TRƯỚC xăng theo biểu cước
    net_after_fuel_vnd: float | None = None  # expected_net_value_vnd - c·d̄_z (đã trừ xăng chặng chở khách)
    estimated_duration_min: int | None = None  # thời gian chặng chở khách = d̄_z / v_z
    avg_trip_distance_km: float | None = None  # d̄_z: cự ly cuốc TB xuất phát từ vùng, TÍNH TỪ NHẬT KÝ của tài xế
    hotspot_features: list[str] = field(default_factory=list)  # chỉ MÔ TẢ (sự kiện địa lý), KHÔNG phải bằng chứng nhu cầu
    source_confidence: Confidence = "none"
    explanation: str | None = None
    # --- Nâng cấp v2: đều có thể truy vết về dữ liệu đầu vào + tham số cấu hình ---
    rank: int | None = None
    reposition_km: float | None = None  # ƯỚC TÍNH từ đường chim bay x detour_factor, KHÔNG phải routing
    reposition_min: float | None = None
    reposition_cost_vnd: float | None = None
    wait_min: float | None = None  # thời gian chờ kỳ vọng w_z của vùng (survival); None nếu không đủ dữ liệu cho mọi ứng viên
    yield_vnd_per_hour: float | None = None  # [net(d̄, v) − c·d̄ − c·r] / giờ (chặng chở khách + dịch chuyển + chờ)
    pareto_optimal: bool | None = None  # không bị vùng khác vượt trội đồng thời về năng suất và P10 của năng suất (lợi nhuận vs độ chắc ăn)
    # --- Nâng cấp v3: bằng chứng và bất định (chỉ có khi dữ liệu cho biết số mẫu / sai số) ---
    evidence_n: int | None = None  # số chuyến thật đứng sau ước lượng của khu vực (nhật ký tài xế)
    yield_low_vnd_per_hour: int | None = None  # P10 của năng suất (chỉ lan truyền dao động mẫu của cự ly cuốc TB và thời gian chờ TB của vùng)
    yield_high_vnd_per_hour: int | None = None
    data_source: str | None = None  # vd. "driver_trip_log"


@dataclass(frozen=True)
class PositionCandidate:
    """Candidate area evaluated for post-trip position retention (spec.md 5.2)."""
    area_id: str
    area_name: str = ""
    position_score: float = 0.0  # Thang điểm 0 - 100 = 100·P(chờ ≤ ngưỡng) - phạt chờ - phạt dịch chuyển
    p_wait_le_pct: float | None = None  # 100·P(chờ ≤ wait_threshold_min) từ survival (Kaplan–Meier, có xử lý kiểm duyệt)
    wait_threshold_min: float | None = None  # ngưỡng phút dùng cho p_wait_le_pct (cấu hình, mặc định 10)
    p_wait_le_by_min: dict[str, float] = field(default_factory=dict)  # {"10": %, "20": %} mọi ngưỡng cấu hình
    median_wait_min: float | None = None  # None = chưa đạt 50% trong khung quan sát (chờ thường > khung đó)
    expected_wait_min: float | None = None  # thời gian chờ kỳ vọng (restricted mean) trong khung quan sát
    source_confidence: Confidence = "none"
    explanation: str | None = None
    rank: int | None = None
    reposition_km: float | None = None  # ƯỚC TÍNH, xem TripValueCandidate.reposition_km
    evidence_n: int | None = None  # số cặp (trả khách -> cuốc kế) thật đứng sau ước lượng
    data_source: str | None = None


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
    # --- v3 (đều tùy chọn, thêm vào không phá tương thích) ---
    personal_model: dict[str, Any] | None = None  # tóm tắt mô hình cá nhân từ nhật ký chuyến (None nếu không có nhật ký)
    tradeoff_matrix: dict[str, Any] | None = None  # đánh đổi định lượng giữa 4 hướng trên cùng thước đo
    data_roadmap: list[dict[str, Any]] | None = None  # dữ liệu nào đang chặn hướng nào và cách mở khóa
    data_tier: dict[str, Any] | None = None  # bậc sẵn sàng dữ liệu 0-3 của dữ liệu do chính tài xế cung cấp
    what_if: dict[str, Any] | None = None  # bảng kịch bản + ngưỡng hòa vốn từ biểu cước (công bố hoặc tài xế nhập), không xếp hạng vùng
    decision_boundaries: dict[str, Any] | None = None  # "điều gì làm khuyến nghị đổi" (chỉ khi explain=True)
    ml_insights: dict[str, Any] | None = None  # v5: mô hình ML trên dữ liệu của tài xế (chờ có ngữ cảnh, khoảng conformal, bandit) + kết quả backtest

