"use client";

import { Badge } from "@/components/ui/badge";
import { Empty, EmptyDescription, EmptyHeader, EmptyTitle } from "@/components/ui/empty";
import { Separator } from "@/components/ui/separator";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ConditionsPanel } from "../../_components/gigca/conditions-panel";
import { useGigca } from "../../_components/gigca/gigca-provider";
import { directions, planMetric, statuses } from "../../_components/gigca/labels";
import { numberText, type Objective } from "../../_components/gigca/types";

export function DirectionDetails({ selected }: { selected: Objective }) {
  const { result } = useGigca();
  const current = result?.objectives[selected];
  const metrics = current?.plan?.key_metrics;
  const detailMetrics =
    selected === "max_trip_value"
      ? [
          ["Cước ròng / chuyến", numberText(metrics?.expected_net_value_vnd, " đ")],
          ["Chờ dự kiến", numberText(metrics?.wait_min_used, " phút")],
        ]
      : selected === "maintain_position"
        ? [
            ["Điểm trả thuận lợi", numberText(metrics?.favorable_dropoff_pct, "%")],
            ["Chờ cuốc tiếp", numberText(metrics?.avg_next_wait_min, " phút")],
          ]
        : selected === "rest_spot"
          ? [
              ["Khoảng cách", numberText(metrics?.distance_m, " m")],
              ["Nghỉ dự kiến", numberText(metrics?.recommended_rest_min, " phút")],
            ]
          : [
              ["Tốc độ hiện tại", numberText(metrics?.traffic_speed_kmh, " km/h")],
              ["Phủ dự báo", numberText(metrics?.forecast_coverage_pct, "%")],
            ];
  return (
    <section aria-label="Chi tiết phương án" className="flex min-w-0 flex-col gap-4 p-4">
      <div className="grid min-w-0 gap-4">
        <Card className="min-w-0">
          <CardHeader>
            <CardTitle>Tổng quan</CardTitle>
          </CardHeader>
          <CardContent>
            {current?.plan ? (
              <div className="flex flex-col gap-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <h2 className="font-medium text-lg tracking-tight">{directions[selected].title}</h2>
                  <Badge variant="outline">{statuses[current.status]}</Badge>
                </div>
                <Separator />
                <div className="flex flex-col gap-1">
                  <span className="text-xs text-muted-foreground">Điểm đến</span>
                  <span className="gigca-destination font-medium">{current.plan.target_location}</span>
                </div>
                <Separator />
                <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
                  <div className="flex flex-col gap-2">
                    <span className="text-xs text-muted-foreground">{directions[selected].title}</span>
                    <span className="gigca-key-metric font-medium text-lg tabular-nums">
                      {planMetric(selected, current)}
                    </span>
                  </div>
                  {detailMetrics.map(([label, value]) => (
                    <div key={label} className="flex flex-col gap-2">
                      <span className="text-xs text-muted-foreground">{label}</span>
                      <span className="text-sm tabular-nums">{value}</span>
                    </div>
                  ))}
                  <div className="flex flex-col gap-2">
                    <span className="text-xs text-muted-foreground">Độ tin cậy</span>
                    <span className="text-sm">
                      {({ low: "Thấp", medium: "Vừa", high: "Cao" } as Record<string, string>)[current.confidence] ??
                        current.confidence}
                    </span>
                  </div>
                </div>
                <Separator />
                <div className="text-sm">
                  <h3 className="font-medium">Vì sao chọn phương án này?</h3>
                  <div className="mt-3 flex flex-col gap-3 text-muted-foreground">
                    <p>{current.plan.summary}</p>
                    <p>{current.plan.trade_offs}</p>
                    <p>{current.plan.contingency_fallback}</p>
                    {current.caveat && <p>{current.caveat}</p>}
                  </div>
                </div>
              </div>
            ) : (
              <Empty>
                <EmptyHeader>
                  <EmptyTitle>Chưa đủ dữ liệu cho {directions[selected].title.toLowerCase()}</EmptyTitle>
                  <EmptyDescription>{current?.reason_for_insufficiency}</EmptyDescription>
                </EmptyHeader>
              </Empty>
            )}
          </CardContent>
        </Card>
        <div className="grid min-w-0 items-start gap-4 xl:grid-cols-3">
          <Card className="min-w-0">
            <CardHeader>
              <CardTitle>Hành động</CardTitle>
            </CardHeader>
            <CardContent>
              {current?.plan ? (
                <div className="flex flex-col divide-y">
                  {current.plan.steps.map((step) => (
                    <div key={step.step_number} className="flex gap-4 py-4">
                      <Badge variant="secondary" className="h-fit">
                        {step.step_number}
                      </Badge>
                      <div className="flex min-w-0 flex-col gap-2">
                        <div className="flex flex-wrap items-center gap-2">
                          <h3 className="font-medium text-sm">{step.action}</h3>
                          <Badge variant="outline">{step.time_window}</Badge>
                        </div>
                        <p className="text-sm text-muted-foreground">{step.instruction}</p>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <Empty>
                  <EmptyHeader>
                    <EmptyTitle>Chưa có hành động đề xuất</EmptyTitle>
                  </EmptyHeader>
                </Empty>
              )}
            </CardContent>
          </Card>
          <div className="min-w-0 xl:col-span-2">
            <ConditionsPanel selected={selected} />
          </div>
        </div>
      </div>
    </section>
  );
}
