export type Objective = "max_trip_value" | "maintain_position" | "rest_spot" | "safety_comfort";
export type Status = "available" | "partial" | "insufficient_data";
export interface DriverInput {
  mode: "simulation" | "sample" | "pipeline" | "database" | "live" | "research";
  research_driver_id?: string;
  rain_tolerance_level: string;
  context: {
    current_lat: number;
    current_lng: number;
    idle_duration_min: number;
    horizon_min: number;
    max_reposition_km: number;
  };
}
export interface Plan {
  target_location: string;
  summary: string;
  trade_offs: string;
  contingency_fallback: string;
  key_metrics: Record<string, unknown>;
  steps: {
    step_number: number;
    time_window: string;
    action: string;
    instruction: string;
  }[];
}
export interface ObjectiveResult {
  status: Status;
  confidence: string;
  plan: Plan | null;
  caveat?: string | null;
  reason_for_insufficiency?: string | null;
  candidates: Record<string, unknown>[];
  safe_window_min?: number | null;
  rain_flags?:
    | {
        valid_time: string;
        prob_pct: number | null;
        mm: number | null;
      }[]
    | null;
}
export interface Place {
  id: string;
  name: string;
  lat: number;
  lng: number;
  category?: string;
  verified?: boolean;
  parking_allowed?: boolean;
}
export interface Recommendation {
  direction_priority?: { objective: Objective; rank: number; rankable: boolean; reason?: string }[] | null;
  input_used?: { horizon_min?: number };
  research_driver_id?: string;
  origin_used?: { lat: number; lng: number };
  ml_insights?: {
    source?: string;
    model_name?: string;
    status?: string;
    notes: string[];
    wait_model?: { used: boolean; backtest: ModelBacktest; zones?: WaitPrediction[] };
    cycle_yield?: { backtest: ModelBacktest; zones: { area_id: string; low: number; median: number; high: number }[] };
    bandit?: { zones: Record<string, { evidence_n: number; explore: boolean; p_best: number }> };
  } | null;
  personal_model?: { status?: string; reason?: string; notes?: string[] } | null;
  generated_at: string;
  objectives: Record<Objective, ObjectiveResult>;
  assumptions_used: string[];
  data_quality_warnings: string[];
  snapshot: {
    id: string;
    mode: string;
    as_of: string;
    sources: { dataset: string; status: string; reason: string }[];
    limitations: string[];
  };
  weather: {
    valid_time: string;
    precipitation_mm: number | null;
    precipitation_probability_pct: number | null;
  }[];
  places: Place[];
  areas: Place[];
}
export interface ModelBacktest {
  status: string;
  reason?: string;
  passes?: boolean;
  calibrated?: boolean | null;
  n_spells?: number;
  n_cycles?: number;
  n_test?: number;
  mae_median_model_vnd?: number;
  mae_train_mean_vnd?: number;
  coverage_conformal?: number;
}
export interface WaitPrediction {
  area_id: string;
  p_wait_le_pct: Record<string, number | null>;
  expected_wait_min: number | null;
  median_wait_min: number | null;
  model: string;
}
export interface ResearchDriver {
  id: string;
  description: string;
  trips: number;
  waits: number;
  lat: number;
  lng: number;
}
export const objectives: Objective[] = ["max_trip_value", "maintain_position", "rest_spot", "safety_comfort"];
export const initialInput: DriverInput = {
  mode: "simulation",
  rain_tolerance_level: "medium",
  context: {
    current_lat: 10.7769,
    current_lng: 106.7009,
    idle_duration_min: 25,
    horizon_min: 180,
    max_reposition_km: 3,
  },
};
export const numberText = (value: unknown, suffix = "") =>
  typeof value === "number" && Number.isFinite(value)
    ? `${value.toLocaleString("vi-VN", { maximumFractionDigits: 1 })}${suffix}`
    : "—";
