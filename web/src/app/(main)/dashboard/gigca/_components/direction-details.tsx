"use client";

import { Badge } from "@/components/ui/badge";
import { Empty, EmptyDescription, EmptyHeader, EmptyTitle } from "@/components/ui/empty";
import { Separator } from "@/components/ui/separator";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ConditionsPanel } from "../../_components/gigca/conditions-panel";
import { useGigca } from "../../_components/gigca/gigca-provider";
import { directions, planMetric, statuses } from "../../_components/gigca/labels";
import { numberText, type Objective } from "../../_components/gigca/types";
import { ModelInsights } from "./model-insights";
import { RouteActions } from "./route-actions";

export function DirectionDetails({ selected }: { selected: Objective }) {
  const { result } = useGigca();
  const current = result?.objectives[selected];
  const metrics = current?.plan?.key_metrics;
  const isBaseModel = result?.ml_insights?.source === "synthetic_base_model";
  const isBaseEarning = isBaseModel && (selected === "max_trip_value" || selected === "maintain_position");
  const detailMetrics = isBaseEarning
    ? [
        ["Chờ ước tính", numberText(metrics?.expected_wait_min, " phút")],
        ["Di chuyển ước tính", numberText(metrics?.reposition_km_estimated, " km")],
        [
          selected === "max_trip_value" ? "Có cuốc trong 10 phút" : "Năng suất ước tính",
          selected === "max_trip_value"
            ? numberText(metrics?.p_wait_le_pct, "%")
            : numberText(metrics?.yield_vnd_per_hour, " đ/h"),
        ],
      ]
    : selected === "max_trip_value"
      ? [
          [
            isBaseModel ? "Nguồn dự đoán" : "Cước ròng / chuyến",
            isBaseModel ? "Model mô phỏng" : numberText(metrics?.expected_net_value_vnd, " đ"),
          ],
          [isBaseModel ? "Chờ ước tính" : "Chờ dùng trong công thức", numberText(metrics?.wait_min_used, " phút")],
        ]
      : selected === "maintain_position"
        ? [
            [
              isBaseModel ? "Có cuốc trong 10 phút · mô phỏng" : "Điểm trả thuận lợi",
              numberText(isBaseModel ? metrics?.p_wait_le_pct : metrics?.favorable_dropoff_pct, "%"),
            ],
            [
              "Chờ cuốc tiếp",
              numberText(isBaseModel ? metrics?.expected_wait_min : metrics?.avg_next_wait_min, " phút"),
            ],
          ]
        : selected === "rest_spot"
          ? [
              ["Khoảng cách", numberText(metrics?.distance_m, " m")],
              ["Nghỉ dự kiến", numberText(metrics?.recommended_rest_min, " phút")],
            ]
          : [
              ["Tốc độ hiện tại", numberText(metrics?.traffic_speed_kmh, " km/h")],
            ];
  return (
    <section aria-label="Chi tiết phương án" className="flex min-w-0 flex-col gap-4 p-4">
      <div className="grid min-w-0 items-start gap-5 xl:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        <div className="flex min-w-0 flex-col gap-4">
        <Card className="min-w-0">
          <CardHeader>
            <CardTitle>Tổng quan</CardTitle>
          </CardHeader>
          <CardContent>
            {current?.plan ? (
              <div className="flex flex-col gap-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <h2 className="font-medium text-lg tracking-tight">{directions[selected].title}</h2>
                  <Badge variant="outline">{isBaseEarning ? "Ước tính mô phỏng" : statuses[current.status]}</Badge>
                </div>
                <Separator />
                <div className="flex flex-col gap-1">
                  <span className="text-xs text-muted-foreground">{selected === "safety_comfort" ? "Khuyến nghị" : "Điểm đến"}</span>
                  <span className="gigca-destination font-medium">{current.plan.target_location}</span>
                </div>
                <Separator />
                <div className="text-sm">
                  <h3 className="font-medium">{selected === "safety_comfort" ? "Bạn nên làm gì?" : "Vì sao chọn khu vực này?"}</h3>
                  <div className="mt-3 flex flex-col gap-3">
                    <p>{current.plan.summary}</p>
                    {!isBaseEarning && (
                      <>
                        <p>{current.plan.contingency_fallback}</p>
                        <details>
                          <summary className="cursor-pointer font-medium">Chi tiết</summary>
                          <div className="mt-2 flex flex-col gap-2">
                            <p>{current.plan.trade_offs}</p>
                            {current.caveat && current.caveat !== current.plan.trade_offs && <p>{current.caveat}</p>}
                          </div>
                        </details>
                      </>
                    )}
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
        <RouteActions key={selected} selected={selected} />
        <div className="min-w-0">
          {!isBaseEarning && (
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
          )}
        </div>
        </div>
        <Card className="min-w-0">
          <CardHeader><CardTitle>Thông tin dự kiến</CardTitle></CardHeader>
          <CardContent className="flex min-w-0 flex-col gap-4">
          {current?.plan && (
            <div aria-label="Số liệu gợi ý" className="grid grid-cols-2 gap-3">
              {[
                [selected === "safety_comfort" ? "Tình hình mưa" : isBaseEarning && selected === "max_trip_value" ? "Năng suất ước tính" : directions[selected].title,
                 selected === "safety_comfort" ? ({ THOI_TIET_THUAN_LOI: "Chưa cần tránh mưa", TRU_MUA_NGAY: "Cần tìm chỗ trú", DI_CHUYEN_TRUOC_KHI_MUA: "Chuẩn bị tránh mưa" } as Record<string, string>)[String(metrics?.weather_action_signal)] ?? "Xem khuyến nghị" : planMetric(selected, current)],
                ...detailMetrics,
              ].map(([label, value], index) => (
                <div key={label} className={index === 0 ? "rounded-md bg-primary/5 p-4" : "rounded-md bg-muted/50 p-4"}>
                  <p className="mb-3 text-sm font-medium">{label}</p>
                  <strong className="text-primary text-2xl font-semibold tabular-nums sm:text-3xl">{value}</strong>
                </div>
              ))}
            </div>
          )}
          <ConditionsPanel selected={selected} compact />
          {(selected === "max_trip_value" || selected === "maintain_position") && (
            <details className="border-t pt-4"><summary className="cursor-pointer font-medium">So sánh khu vực</summary><div className="mt-4"><ModelInsights selected={selected} /></div></details>
          )}
          </CardContent>
        </Card>
      </div>
    </section>
  );
}
