import type { Recommendation } from "./types";

export function weatherTimeLabel(timestamp: number) {
  return new Date(timestamp).toLocaleTimeString("vi-VN", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Asia/Ho_Chi_Minh",
  });
}

// Five-minute display grid, not five-minute forecast data. Never interpolate,
// divide hourly rain totals, or bridge missing provider hours.
export function weatherTimeline(hours: Recommendation["weather"], generatedAt: string, horizonMin: number) {
  const start = Date.parse(generatedAt);
  if (!Number.isFinite(start) || !Number.isFinite(horizonMin) || horizonMin <= 0) return [];
  const end = start + Math.min(horizonMin, 480) * 60000;
  const step = 5 * 60000;
  const timestamps = [start];
  for (let t = Math.floor(start / step) * step + step; t < end; t += step) timestamps.push(t);
  timestamps.push(end);
  const rows = hours
    .map((hour) => ({ ...hour, timestamp: Date.parse(hour.valid_time) }))
    .filter((hour) => Number.isFinite(hour.timestamp))
    .sort((a, b) => a.timestamp - b.timestamp);
  const numeric = (value: number | null | undefined) =>
    typeof value === "number" && Number.isFinite(value) ? value : null;
  return timestamps.map((timestamp) => {
    const row = rows.findLast((hour) => hour.timestamp <= timestamp && timestamp < hour.timestamp + 3600000);
    return {
      timestamp,
      forecastWindow: row
        ? `${weatherTimeLabel(row.timestamp)}–${weatherTimeLabel(row.timestamp + 3600000)}`
        : "Chưa có dự báo",
      precipitation_probability_pct: numeric(row?.precipitation_probability_pct),
      precipitation_mm: numeric(row?.precipitation_mm),
    };
  });
}
