"use client";

import { useEffect, useState } from "react";
import { api } from "./api";
import type { RouteRoad } from "./routes";
import { startVisiblePolling } from "./visible-poll";

interface NearbyTraffic {
  roads: RouteRoad[];
  fetched_at: string;
}
const cache = new Map<string, { expires: number; promise: Promise<NearbyTraffic> }>();
function fetchNearby(lat: number, lng: number) {
  const key = `${lat}:${lng}`;
  const existing = cache.get(key);
  if (existing && existing.expires > Date.now()) return existing.promise;
  const promise = api<NearbyTraffic>(`/api/v1/traffic/nearby?${new URLSearchParams({ lat: String(lat), lng: String(lng) })}`)
    .then((data) => ({ ...data, roads: data.roads.map((road) => ({ ...road, speed: road.speed ?? undefined, delay: undefined })) }))
    .catch((error) => { cache.delete(key); throw error; });
  if (cache.size >= 16) cache.delete(cache.keys().next().value!);
  cache.set(key, { expires: Date.now() + 30000, promise });
  return promise;
}
export function useNearbyTraffic(enabled: boolean, lat: number, lng: number) {
  const [data, setData] = useState<NearbyTraffic | null>(null);
  const [message, setMessage] = useState("");
  useEffect(() => {
    let cancelled = false;
    setData(null);
    if (!enabled) { setMessage(""); return; }
    setMessage("Đang tải giao thông quanh vị trí…");
    const refresh = () => {
      fetchNearby(lat, lng).then((value) => {
        if (!cancelled) { setData(value); setMessage(value.roads.length ? "" : "Chưa có dữ liệu đường lân cận."); }
      }).catch(() => {
        if (!cancelled) setMessage("Chưa cập nhật được giao thông quanh vị trí.");
      });
    };
    refresh();
    const stop = startVisiblePolling(refresh, 30000);
    return () => { cancelled = true; stop(); };
  }, [enabled, lat, lng]);
  return { data, message };
}
