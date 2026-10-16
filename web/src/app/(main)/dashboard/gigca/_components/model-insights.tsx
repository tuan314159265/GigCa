"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Empty, EmptyHeader, EmptyTitle } from "@/components/ui/empty";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useGigca } from "../../_components/gigca/gigca-provider";
import { recommendationTargets } from "../../_components/gigca/routes";
import { numberText, type Objective } from "../../_components/gigca/types";

export function ModelInsights({ selected }: { selected: Objective }) {
  const { result } = useGigca();
  const insights = result?.ml_insights;
  const isBaseModel = insights?.source === "synthetic_base_model";
  const waitModel = insights?.wait_model;
  const cycle = insights?.cycle_yield;
  const area = recommendationTargets(result).find((target) => target.objectives.includes(selected))?.place;
  const wait = waitModel?.zones?.find((zone) => zone.area_id === area?.id);
  const probabilities = Object.entries(wait?.p_wait_le_pct ?? {})
    .filter((entry): entry is [string, number] => typeof entry[1] === "number" && Number.isFinite(entry[1]))
    .sort((a, b) => Number(a[0]) - Number(b[0]))
    .map(([minutes, probability]) => ({ minutes: `${minutes} phút`, probability }));
  return (
    <section aria-label="So sánh các khu vực" className="flex min-w-0 flex-col gap-4">
      <div className="grid min-w-0 gap-4">
        <Card>
          <CardHeader>
            <CardTitle>Khả năng nhận cuốc</CardTitle>
          </CardHeader>
          <CardContent>
            {probabilities.length ? (
              <div className="grid grid-cols-2 gap-3">
                {probabilities.map((row) => (
                  <div key={row.minutes} className="rounded-md bg-muted/50 p-3">
                    <p className="mb-2">Trong {row.minutes}</p>
                    <strong className="text-2xl text-primary tabular-nums">{numberText(row.probability, "%")}</strong>
                  </div>
                ))}
              </div>
            ) : (
              <Empty>
                <EmptyHeader>
                  <EmptyTitle>Chưa có xác suất chờ cho điểm đến này</EmptyTitle>
                </EmptyHeader>
              </Empty>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>So sánh khu vực · ước tính</CardTitle>
          </CardHeader>
          <CardContent className="max-h-64 overflow-auto">
            {cycle && (isBaseModel || cycle.backtest.calibrated === true) && cycle.zones.length ? (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Vùng</TableHead>
                    <TableHead>Năng suất / giờ</TableHead>
                    <TableHead>Khoảng ước tính</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {cycle.zones.map((zone) => (
                    <TableRow key={zone.area_id} data-state={area?.id === zone.area_id ? "selected" : undefined}>
                      <TableCell className="max-w-56 whitespace-normal">
                        {result?.areas.find((place) => place.id === zone.area_id)?.name ?? zone.area_id}
                      </TableCell>
                      <TableCell className="font-semibold text-primary tabular-nums">{numberText(zone.median, " đ/h")}</TableCell>
                      <TableCell>
                        {numberText(zone.low)}–{numberText(zone.high)} đ/h
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            ) : (
              <Empty>
                <EmptyHeader>
                  <EmptyTitle>{cycle?.backtest.reason ?? "Chưa có khoảng dự đoán đủ điều kiện"}</EmptyTitle>
                </EmptyHeader>
              </Empty>
            )}
          </CardContent>
        </Card>
      </div>
    </section>
  );
}
