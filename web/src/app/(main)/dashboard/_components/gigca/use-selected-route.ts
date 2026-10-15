"use client";

import { useEffect, useState } from "react";
import { useGigca } from "./gigca-provider";
import { recommendationTargets, roadRoute, type RoadRoute } from "./routes";
import type { Objective } from "./types";
import { startVisiblePolling } from "./visible-poll";

export function useSelectedRoute(selected: Objective) {
  const { result, input, tomtom } = useGigca();
  const target = recommendationTargets(result).find((entry) => entry.objectives.includes(selected))?.place;
  const [route, setRoute] = useState<RoadRoute | null>(null);
  const [message, setMessage] = useState("");
  const lat = input.context.current_lat;
  const lng = input.context.current_lng;
  const atDestination = Boolean(target && Math.abs(target.lat - lat) < 0.0001 && Math.abs(target.lng - lng) < 0.0001);
  useEffect(() => {
    let cancelled = false;
    setRoute(null);
    if (atDestination) {
      setMessage("Bạn đang ở khu vực được chọn.");
      return;
    }
    if (
      !target ||
      !Number.isFinite(lat) ||
      !Number.isFinite(lng) ||
      !tomtom ||
      ["preview", "research"].includes(result?.snapshot.mode ?? "")
    ) {
      setMessage("Chưa có tuyến đường trực tiếp.");
      return;
    }
    const refresh = () => {
      setMessage("Đang tải tuyến đường…");
      roadRoute(lat, lng, target)
        .then((value) => {
          if (!cancelled) {
            setRoute(value);
            setMessage("");
          }
        })
        .catch((error: unknown) => {
          if (!cancelled) {
            setRoute(null);
            setMessage(error instanceof Error ? error.message : "Không tải được tuyến đường.");
          }
        });
    };
    refresh();
    const stopPolling = startVisiblePolling(refresh, 30000);
    return () => {
      cancelled = true;
      stopPolling();
    };
  }, [target?.lat, target?.lng, lat, lng, tomtom, result?.snapshot.mode, result?.generated_at, atDestination]);
  return { route, message, target, atDestination };
}
