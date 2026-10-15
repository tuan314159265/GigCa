import snapshot from "./preview-recommendations.json";
import type { Recommendation } from "./types";

export const previewOnly = process.env.NEXT_PUBLIC_GIGCA_PREVIEW !== "false";
export const previewRecommendation = {
  ...snapshot,
  snapshot: {
    ...snapshot.snapshot,
    mode: "preview",
    sources: snapshot.snapshot.sources.map((source) => ({ ...source, status: "simulated" })),
    limitations: ["Snapshot mô phỏng cố định để xem giao diện, không phải tình trạng hiện tại."],
  },
} as Recommendation;
