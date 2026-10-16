"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Empty, EmptyHeader, EmptyTitle } from "@/components/ui/empty";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useGigca } from "./gigca-provider";
import { modes } from "./labels";
import { numberText, type Objective } from "./types";
import { groupRouteRoads, routeRoads } from "./routes";
import { useSelectedRoute } from "./use-selected-route";
import { weatherTimeline } from "./weather-timeline";
import { useNearbyTraffic } from "./use-nearby-traffic";
import { TrafficCameraPanel } from "./traffic-camera-panel";

export function ConditionsPanel({ selected = "max_trip_value", compact = false }: { selected?: Objective; compact?: boolean }) {
  const { result, input, tomtom } = useGigca();
  const { route, message: routeMessage, atDestination } = useSelectedRoute(selected);
  const nearbyMode = atDestination && result?.snapshot.mode === "live";
  const nearby = useNearbyTraffic(Boolean(nearbyMode && tomtom), input.context.current_lat, input.context.current_lng);
  const trafficMessage = nearbyMode ? (tomtom ? nearby.message : "Chưa cấu hình nguồn giao thông.") : routeMessage;
  const roads = nearbyMode ? groupRouteRoads(nearby.data?.roads ?? []) : route ? groupRouteRoads(routeRoads(route)) : [];
  const [detailId, setDetailId] = useState<string | null>(null);
  const roadKey = (road: (typeof roads)[number]) => (road.name === "Đoạn đường chưa có tên" ? road.id : road.name);
  const detail = roads.find((road) => roadKey(road) === detailId);
  const weather = weatherTimeline(
    result?.weather ?? [],
    result?.generated_at ?? "",
    result?.input_used?.horizon_min ?? input.context.horizon_min,
  );
  const metrics = result?.objectives.safety_comfort.plan?.key_metrics;
  const probabilities = weather.flatMap((row) =>
    typeof row.precipitation_probability_pct === "number" ? [row.precipitation_probability_pct] : [],
  );
  const rainAmounts = weather.flatMap((row) =>
    typeof row.precipitation_mm === "number" ? [row.precipitation_mm] : [],
  );
  const Surface = compact ? "div" : Card;
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="outline">{result ? modes[result.snapshot.mode] : "Chưa tính gợi ý"}</Badge>
        <Badge variant="outline">Tốc độ {numberText(metrics?.traffic_speed_kmh, " km/h")}</Badge>
        <Badge variant="outline">Dự báo theo giờ</Badge>
      </div>
      <div className={compact ? "grid grid-cols-2 gap-3" : "grid gap-4 sm:grid-cols-3"}>
        {[
          ["Xác suất mưa cao nhất", probabilities.length ? `${Math.max(...probabilities)}%` : "—"],
          ["Lượng mưa cao nhất", rainAmounts.length ? numberText(Math.max(...rainAmounts), " mm") : "—"],
          ["Năng suất ước tính", numberText(result?.objectives[selected].plan?.key_metrics.yield_vnd_per_hour, " đ/h")],
        ].filter(([label]) => !compact || label !== "Năng suất ước tính").map(([label, value]) => (
          <Surface key={label} className={compact ? "rounded-md bg-muted/50 py-4" : undefined}>
            <CardHeader>
              <CardTitle>{label}</CardTitle>
            </CardHeader>
            <CardContent>
              <strong className="text-primary text-3xl font-semibold tabular-nums">{value}</strong>
            </CardContent>
          </Surface>
        ))}
      </div>
      <Surface className={compact ? "border-t pt-4" : undefined}>
        <CardHeader>
          <CardTitle>{nearbyMode ? "Giao thông quanh vị trí hiện tại" : "Giao thông trên tuyến đang chọn"}</CardTitle>
        </CardHeader>
        <CardContent>
          {roads.length > 0 ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Đường</TableHead>
                  <TableHead>Tốc độ thấp nhất</TableHead>
                  <TableHead>Đoạn đông nhất</TableHead>
                  <TableHead>
                    <span className="sr-only">Chi tiết</span>
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {roads.map((road) => (
                  <TableRow key={road.id}>
                    <TableCell>{road.name}</TableCell>
                    <TableCell className="font-semibold tabular-nums">{numberText(road.speed, " km/h")}</TableCell>
                    <TableCell>
                      <Badge variant="outline" className={trafficStyles[road.status]}>
                        {trafficLabels[road.status]}
                        {road.partial && road.status !== "unknown" ? " · dữ liệu một phần" : ""}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <Button variant="outline" size="sm" onClick={() => setDetailId(roadKey(road))}>
                        Chi tiết
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : (
            <Empty>
              <EmptyHeader>
                <EmptyTitle>{trafficMessage || "Chưa có đoạn đường"}</EmptyTitle>
              </EmptyHeader>
            </Empty>
          )}
          {nearbyMode && nearby.data?.fetched_at && roads.length > 0 && (
            <p className="mt-3 text-xs text-muted-foreground">TomTom · Mẫu đường trong phạm vi 500 m · Cập nhật {new Date(nearby.data.fetched_at).toLocaleTimeString("vi-VN")}</p>
          )}
          {roads.length > 0 && trafficMessage && (
            <p role="status" className="mt-3">
              {trafficMessage}
            </p>
          )}
        </CardContent>
      </Surface>
      {detail && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between gap-2">
              <CardTitle>{detail.name}</CardTitle>
              <Button variant="ghost" size="sm" onClick={() => setDetailId(null)}>
                Đóng
              </Button>
            </div>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <div className="flex flex-wrap gap-4">
              <Badge variant="outline" className={trafficStyles[detail.status]}>
                {trafficLabels[detail.status]}
              </Badge>
              <span>Tốc độ thấp nhất: {numberText(detail.speed, " km/h")}</span>
            </div>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{nearbyMode ? "Đoạn lấy mẫu" : "Đoạn trên tuyến"}</TableHead>
                  <TableHead>Tốc độ</TableHead>
                  <TableHead>Tình trạng</TableHead>
                  <TableHead>Chậm</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {detail.segments.map((segment, index) => (
                  <TableRow key={segment.id}>
                    <TableCell>Đoạn {index + 1}</TableCell>
                    <TableCell>{numberText(segment.speed, " km/h")}</TableCell>
                    <TableCell>
                      <Badge variant="outline" className={trafficStyles[segment.status]}>
                        {trafficLabels[segment.status]}
                      </Badge>
                    </TableCell>
                    <TableCell>{numberText(segment.delay, " giây")}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            {route && <TrafficCameraPanel key={`${roadKey(detail)}:${selected}`} route={route} road={detail} />}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
const trafficLabels = { smooth: "Thông thoáng", moderate: "Đông xe", congested: "Ùn tắc", unknown: "Chưa có dữ liệu" };
const trafficStyles = {
  smooth: "border-emerald-500 bg-emerald-50 text-emerald-800",
  moderate: "border-amber-500 bg-amber-50 text-amber-800",
  congested: "border-red-500 bg-red-50 text-red-800",
  unknown: "",
};
