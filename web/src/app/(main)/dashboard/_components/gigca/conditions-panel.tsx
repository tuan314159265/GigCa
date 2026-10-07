"use client";

import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from "recharts";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";
import { Empty, EmptyHeader, EmptyTitle } from "@/components/ui/empty";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useGigca } from "./gigca-provider";
import { modes } from "./labels";
import { numberText, type Objective } from "./types";
import { recommendationTargets, roadRoute, routeRoads, type RouteRoad } from "./routes";

export function ConditionsPanel({ selected = "max_trip_value" }: { selected?: Objective }) {
  const { result, input, tomtom } = useGigca();
  const [roads, setRoads] = useState<RouteRoad[]>([]);
  const [routeMessage, setRouteMessage] = useState("");
  const [detail, setDetail] = useState<RouteRoad | null>(null);
  const target = recommendationTargets(result).find((entry) => entry.objectives.includes(selected))?.place;
  useEffect(() => {
    let cancelled = false;
    setRoads([]);
    setDetail(null);
    if (result?.snapshot.mode === "preview" || !tomtom || !target || !Number.isFinite(input.context.current_lat) || !Number.isFinite(input.context.current_lng)) {
      setRouteMessage(result?.snapshot.mode === "preview" ? "Preview · chưa có tuyến giao thông trực tiếp" : "Chưa có tuyến hoặc kết nối TomTom");
      return;
    }
    const refresh = () => {
      setRouteMessage("Đang cập nhật tuyến đường…");
      roadRoute(input.context.current_lat, input.context.current_lng, target).then((route) => {
        if (cancelled) return;
        setRoads(routeRoads(route));
        setRouteMessage("");
      }).catch((error: unknown) => {
        if (!cancelled) setRouteMessage(error instanceof Error ? error.message : "Không tải được tuyến đường");
      });
    };
    refresh();
    const timer = window.setInterval(refresh, 60000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [selected, target?.lat, target?.lng, input.context.current_lat, input.context.current_lng, tomtom, result?.snapshot.mode, result?.generated_at]);
  const weather = (result?.weather ?? []).map((row) => ({
    ...row,
    time: new Date(row.valid_time).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" }),
  }));
  const metrics = result?.objectives.safety_comfort.plan?.key_metrics;
  const probabilities = weather.flatMap((row) =>
    typeof row.precipitation_probability_pct === "number" ? [row.precipitation_probability_pct] : [],
  );
  const rainAmounts = weather.flatMap((row) => typeof row.precipitation_mm === "number" ? [row.precipitation_mm] : []);
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="outline">{modes[result?.snapshot.mode ?? "simulation"]}</Badge>
        {probabilities.length > 0 && <Badge variant="secondary">Mưa cao nhất {Math.max(...probabilities)}%</Badge>}
        <Badge variant="outline">Tốc độ {numberText(metrics?.traffic_speed_kmh, " km/h")}</Badge>
      </div>
      <div className="grid gap-4 sm:grid-cols-3">
        {[
          ["Xác suất mưa cao nhất", probabilities.length ? `${Math.max(...probabilities)}%` : "—"],
          ["Lượng mưa cao nhất", rainAmounts.length ? numberText(Math.max(...rainAmounts), " mm") : "—"],
          ["Thu nhập ước tính", numberText(result?.objectives.max_trip_value.plan?.key_metrics.yield_vnd_per_hour, " đ/h")],
        ].map(([label, value]) => <Card key={label}><CardHeader><CardTitle>{label}</CardTitle></CardHeader><CardContent><strong className="text-primary text-2xl">{value}</strong></CardContent></Card>)}
      </div>
      <div className="grid min-w-0 gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Xác suất mưa</CardTitle>
          </CardHeader>
          <CardContent>
            {weather.length ? (
              <ChartContainer
                className="h-56 w-full"
                config={{ precipitation_probability_pct: { label: "Xác suất mưa (%)", color: "var(--chart-2)" } }}
              >
                <BarChart accessibilityLayer data={weather} margin={{ left: -15, right: 8 }}>
                  <CartesianGrid vertical={false} />
                  <XAxis dataKey="time" tickLine={false} axisLine={false} tickMargin={8} />
                  <YAxis domain={[0, 100]} tickLine={false} axisLine={false} unit="%" />
                  <ChartTooltip content={<ChartTooltipContent />} />
                  <Bar
                    dataKey="precipitation_probability_pct"
                    fill="var(--color-precipitation_probability_pct)"
                    radius={3}
                    maxBarSize={55}
                    isAnimationActive={false}
                  />
                </BarChart>
              </ChartContainer>
            ) : (
              <Empty>
                <EmptyHeader>
                  <EmptyTitle>Chưa có dự báo mưa</EmptyTitle>
                </EmptyHeader>
              </Empty>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Lượng mưa</CardTitle>
          </CardHeader>
          <CardContent>
            {weather.length ? (
              <ChartContainer
                className="h-56 w-full"
                config={{ precipitation_mm: { label: "Lượng mưa (mm)", color: "var(--chart-4)" } }}
              >
                <BarChart accessibilityLayer data={weather} margin={{ left: -15, right: 8 }}>
                  <CartesianGrid vertical={false} />
                  <XAxis dataKey="time" tickLine={false} axisLine={false} tickMargin={8} />
                  <YAxis tickLine={false} axisLine={false} unit=" mm" />
                  <ChartTooltip content={<ChartTooltipContent />} />
                  <Bar
                    dataKey="precipitation_mm"
                    fill="var(--color-precipitation_mm)"
                    radius={3}
                    maxBarSize={55}
                    isAnimationActive={false}
                  />
                </BarChart>
              </ChartContainer>
            ) : (
              <Empty>
                <EmptyHeader>
                  <EmptyTitle>Chưa có lượng mưa</EmptyTitle>
                </EmptyHeader>
              </Empty>
            )}
          </CardContent>
        </Card>
      </div>
      <Card>
        <CardHeader><CardTitle>Giao thông trên tuyến đang chọn</CardTitle></CardHeader>
        <CardContent>
          {roads.length > 0 ? <Table>
            <TableHeader><TableRow><TableHead>Đường</TableHead><TableHead>Tốc độ</TableHead><TableHead>Tình trạng</TableHead><TableHead><span className="sr-only">Chi tiết</span></TableHead></TableRow></TableHeader>
            <TableBody>{roads.map((road) => <TableRow key={road.id}>
              <TableCell>{road.name}</TableCell>
              <TableCell>{numberText(road.speed, " km/h")}</TableCell>
              <TableCell><Badge variant="outline" className={trafficStyles[road.status]}>{trafficLabels[road.status]}</Badge></TableCell>
              <TableCell><Button variant="outline" size="sm" onClick={() => setDetail(road)}>Chi tiết</Button></TableCell>
            </TableRow>)}</TableBody>
          </Table> : <Empty><EmptyHeader><EmptyTitle>{routeMessage || "Chưa có đoạn đường"}</EmptyTitle></EmptyHeader></Empty>}
          {roads.length > 0 && routeMessage && <p role="status" className="mt-3">{routeMessage}</p>}
        </CardContent>
      </Card>
      {detail && <Card>
        <CardHeader><div className="flex items-center justify-between gap-2"><CardTitle>{detail.name}</CardTitle><Button variant="ghost" size="sm" onClick={() => setDetail(null)}>Đóng</Button></div></CardHeader>
        <CardContent className="flex flex-col gap-4">
          <div className="flex flex-wrap gap-4"><Badge variant="outline" className={trafficStyles[detail.status]}>{trafficLabels[detail.status]}</Badge><span>Tốc độ: {numberText(detail.speed, " km/h")}</span><span>Chậm trên đoạn báo cáo: {numberText(detail.delay, " giây")}</span></div>
          <Empty><EmptyHeader><EmptyTitle>Chưa có nguồn camera giao thông</EmptyTitle></EmptyHeader></Empty>
        </CardContent>
      </Card>}
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
