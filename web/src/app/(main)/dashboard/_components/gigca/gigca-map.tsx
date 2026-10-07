"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type * as Leaflet from "leaflet";
import { Layers, LocateFixed, MapPin } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useGigca } from "./gigca-provider";
import { directions } from "./labels";
import { previewOnly } from "./preview";
import { recommendationTargets, roadRoute, type RoadRoute } from "./routes";
import type { Objective, Place } from "./types";

const snapshotBounds: Leaflet.LatLngBoundsExpression = [
  [10.725381285457912, 106.6552734375],
  [10.83330598364249, 106.76513671875],
];

export function GigcaMap({ selected, focusedPlace }: { selected?: Objective; focusedPlace?: Place | null }) {
  const { result, input, tomtom } = useGigca();
  const host = useRef<HTMLDivElement>(null);
  const map = useRef<Leaflet.Map | null>(null);
  const leaflet = useRef<typeof Leaflet | null>(null);
  const [ready, setReady] = useState(false);
  const [traffic, setTraffic] = useState(false);
  const [mapError, setMapError] = useState("");
  const [routeError, setRouteError] = useState("");
  const [trafficError, setTrafficError] = useState("");
  const [loadedRoutes, setLoadedRoutes] = useState<Map<string, RoadRoute>>(new Map());
  const [routing, setRouting] = useState(false);
  const [tick, setTick] = useState(0);
  const lat = input.context.current_lat;
  const lng = input.context.current_lng;
  const targets = useMemo(
    () => (focusedPlace ? [{ place: focusedPlace, objectives: [] as Objective[] }] : recommendationTargets(result)),
    [focusedPlace, result],
  );

  useEffect(() => {
    let cancelled = false;
    void import("leaflet").then((L) => {
      if (cancelled || !host.current) return;
      leaflet.current = L;
      const instance = L.map(host.current, {
        zoomAnimation: false,
        fadeAnimation: false,
        markerZoomAnimation: false,
        zoomControl: !previewOnly,
        minZoom: previewOnly ? 14 : 3,
        maxZoom: previewOnly ? 14 : 19,
      }).setView([10.7769, 106.7009], 14);
      map.current = instance;
      if (previewOnly) instance.setMaxBounds(snapshotBounds);
      // A small, fixed geographic snapshot is bundled for offline UI preview.
      // This is a basemap only; it never claims to provide live traffic or routes.
      const tiles = L.tileLayer(
        previewOnly
          ? "/maps/{z}/{x}/{y}.png"
          : tomtom
            ? "/api/map/tiles/{z}/{x}/{y}.png"
            : "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        {
          attribution: previewOnly
            ? "Tiles © Esri — Esri, HERE, Garmin, OpenStreetMap contributors"
            : tomtom
              ? "© TomTom"
              : '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
          maxZoom: previewOnly ? 14 : 19,
          ...(previewOnly
            ? {
                bounds: snapshotBounds,
              }
            : {}),
        },
      ).addTo(instance);
      tiles.on("tileerror", () => {
        if (!cancelled) setMapError("Không tải được nền bản đồ.");
      });
      if (previewOnly)
        L.tileLayer("/maps/labels/{z}/{x}/{y}.png", {
          maxZoom: 14,
          bounds: snapshotBounds,
          pane: "overlayPane",
        }).addTo(instance);
      const observer = new ResizeObserver(() => instance.invalidateSize({ animate: false }));
      observer.observe(host.current);
      instance.once("unload", () => observer.disconnect());
      setReady(true);
    });
    return () => {
      cancelled = true;
      map.current?.remove();
      map.current = null;
      setReady(false);
    };
  }, [tomtom]);

  useEffect(() => {
    if (!tomtom || previewOnly) return;
    const timer = window.setInterval(() => {
      if (!document.hidden) setTick((value) => value + 1);
    }, 60000);
    return () => window.clearInterval(timer);
  }, [tomtom]);

  useEffect(() => {
    let cancelled = false;
    setLoadedRoutes(new Map());
    setRouteError("");
    if (previewOnly || !tomtom || !targets.length || !Number.isFinite(lat) || !Number.isFinite(lng)) {
      setRouting(false);
      return;
    }
    setRouting(true);
    void Promise.allSettled(targets.map((target) => roadRoute(lat, lng, target.place))).then((outcomes) => {
      if (cancelled) return;
      const routes = new Map<string, RoadRoute>();
      outcomes.forEach((outcome, index) => {
        if (outcome.status === "fulfilled") routes.set(targets[index].place.id, outcome.value);
      });
      setLoadedRoutes(routes);
      setRouting(false);
      if (routes.size < targets.length) setRouteError("Một số tuyến đường chưa tải được.");
    });
    return () => {
      cancelled = true;
    };
  }, [lat, lng, tomtom, targets, tick]);

  useEffect(() => {
    const instance = map.current;
    const L = leaflet.current;
    if (!ready || !instance || !L || !Number.isFinite(lat) || !Number.isFinite(lng)) return;
    const markers = L.layerGroup().addTo(instance);
    const label = (text: string) => {
      const span = document.createElement("span");
      span.textContent = text;
      return span;
    };
    L.circleMarker([lat, lng], {
      radius: 7,
      color: "var(--gigca-map-foreground)",
      fillColor: "var(--gigca-map-background)",
      fillOpacity: 1,
      weight: 3,
    })
      .bindTooltip(label("Vị trí của tôi"), { permanent: true, direction: "top" })
      .addTo(markers);
    for (const target of targets) {
      const active = focusedPlace || (selected && target.objectives.includes(selected));
      L.circleMarker([target.place.lat, target.place.lng], {
        radius: active ? 9 : 6,
        weight: active ? 3 : 2,
        color: "var(--gigca-map-foreground)",
        fillColor: active ? "var(--gigca-map-foreground)" : "var(--gigca-map-background)",
        fillOpacity: 1,
      })
        .bindTooltip(label(target.place.name), { permanent: Boolean(active), direction: "bottom" })
        .addTo(markers);
      const route = loadedRoutes.get(target.place.id);
      if (route)
        L.polyline(
          route.legs.flatMap((leg) =>
            leg.points.map((point) => [point.latitude, point.longitude] as Leaflet.LatLngTuple),
          ),
          {
            color: "var(--gigca-map-foreground)",
            weight: active ? 5 : 3,
            opacity: active ? 1 : 0.3,
          },
        ).addTo(markers);
    }
    return () => {
      instance.removeLayer(markers);
    };
  }, [ready, lat, lng, targets, selected, focusedPlace, loadedRoutes]);

  useEffect(() => {
    const instance = map.current;
    const L = leaflet.current;
    if (!ready || !instance || !L || !Number.isFinite(lat) || !Number.isFinite(lng)) return;
    const points: Leaflet.LatLngTuple[] = [
      [lat, lng],
      ...targets.map((target) => [target.place.lat, target.place.lng] as Leaflet.LatLngTuple),
    ];
    instance.fitBounds(L.latLngBounds(points), { padding: [65, 65], maxZoom: previewOnly ? 14 : 15, animate: false });
  }, [ready, lat, lng, targets]);

  useEffect(() => {
    const instance = map.current;
    const L = leaflet.current;
    if (!ready || !instance || !L || !traffic || !tomtom || previewOnly) return;
    setTrafficError("");
    const layer = L.tileLayer(`/api/traffic/tiles/{z}/{x}/{y}.png?t=${tick}`, { opacity: 0.8, maxZoom: 19 }).addTo(
      instance,
    );
    layer.on("tileerror", () => setTrafficError("Không tải được lớp giao thông."));
    return () => {
      instance.removeLayer(layer);
    };
  }, [ready, traffic, tomtom, tick]);

  const selectedTarget = targets.find((target) => focusedPlace || (selected && target.objectives.includes(selected)));
  const selectedRoute = selectedTarget && loadedRoutes.get(selectedTarget.place.id);
  return (
    <section aria-label="Bản đồ & điểm chờ" className="flex min-w-0 flex-col">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b px-4 py-3">
        <div className="flex flex-wrap items-center gap-2">
          <MapPin className="size-4" />
          <h2 className="font-medium text-sm">Bản đồ & điểm chờ</h2>
          <Badge variant="outline">{previewOnly ? "Nền bản đồ lưu sẵn" : tomtom ? "TomTom" : "OpenStreetMap"}</Badge>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button
            size="sm"
            variant="outline"
            disabled={!tomtom || previewOnly}
            aria-pressed={traffic}
            onClick={() => setTraffic(!traffic)}
          >
            <Layers data-icon="inline-start" />
            {traffic ? "Ẩn giao thông" : "Xem giao thông"}
          </Button>
          <Button
            size="icon-sm"
            variant="outline"
            aria-label="Về vị trí của tôi"
            onClick={() => map.current?.setView([lat, lng], previewOnly ? 14 : 15, { animate: false })}
          >
            <LocateFixed />
          </Button>
        </div>
      </div>
      <div ref={host} className="gigca-map isolate h-80 w-full bg-muted lg:h-[420px]" />
      <div className="flex flex-wrap items-center gap-3 border-b px-4 py-2 text-sm">
        <Badge variant="secondary">{selected ? directions[selected].title : "Các điểm chờ"}</Badge>
        <span className="min-w-0 text-muted-foreground">
          {selectedTarget?.place.name ??
            (selected === "safety_comfort" ? "Theo tình trạng các đoạn đường" : "Chọn điểm trên danh sách")}
        </span>
        {selectedRoute && (
          <Badge variant="outline">
            {(selectedRoute.summary.lengthInMeters / 1000).toFixed(1)} km ·{" "}
            {Math.ceil(selectedRoute.summary.travelTimeInSeconds / 60)} phút
          </Badge>
        )}
        {routing && <span role="status">Đang tải tuyến đường…</span>}
        {previewOnly && (
          <Badge variant="outline" className="ml-auto">
            Chưa có tuyến & giao thông trực tiếp
          </Badge>
        )}
        {!previewOnly && !tomtom && (
          <Badge variant="outline" className="ml-auto">
            Chưa cấu hình TomTom
          </Badge>
        )}
      </div>
      {(mapError || routeError || trafficError) && (
        <Alert variant="destructive">
          <AlertDescription>{mapError || routeError || trafficError}</AlertDescription>
        </Alert>
      )}
    </section>
  );
}
