import { Banknote, Coffee, MapPin, ShieldCheck } from "lucide-react";
import { numberText, type Objective, type ObjectiveResult } from "./types";

export const directions = {
  max_trip_value: { title: "Cuốc giá trị cao", icon: Banknote },
  maintain_position: { title: "Giữ vị trí tốt", icon: MapPin },
  rest_spot: { title: "Nghỉ ngơi", icon: Coffee },
  safety_comfort: { title: "Né mưa & kẹt xe", icon: ShieldCheck },
};
export const statuses = { available: "Có dữ liệu", partial: "Một phần", insufficient_data: "Chưa đủ dữ liệu" };
export const modes: Record<string, string> = {
  preview: "Preview",
  live: "Theo vị trí hiện tại",
  simulation: "Mô phỏng",
  sample: "Snapshot mẫu",
  pipeline: "Data pipeline",
  database: "PostgreSQL",
};
export function planMetric(key: Objective, result?: ObjectiveResult) {
  const metrics = result?.plan?.key_metrics;
  if (!metrics) return "—";
  if (key === "max_trip_value") return numberText(metrics.yield_vnd_per_hour, " đ/h");
  if (key === "maintain_position") return numberText(metrics.position_score, "/100");
  return numberText(key === "rest_spot" ? metrics.duration_min : metrics.safe_window_min, " phút");
}
