"use client";

import { ArrowRight, Navigation } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { routeStreetSequence } from "../../_components/gigca/routes";
import type { Objective } from "../../_components/gigca/types";
import { useSelectedRoute } from "../../_components/gigca/use-selected-route";

export function RouteActions({ selected }: { selected: Objective }) {
  const { route, target, message, atDestination } = useSelectedRoute(selected);
  const streets = route ? routeStreetSequence(route) : [];
  if (!target) return null;
  return (
    <section aria-label="Hành động và tuyến đường" className="gigca-actions border-primary border-l-4">
      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <CardTitle>
              <span className="flex items-center gap-2">
                <Navigation className="size-5" />
                Hành động
              </span>
            </CardTitle>
            {route && (
              <Badge variant="default" className="gigca-action-distance">
                {(route.summary.lengthInMeters / 1000).toLocaleString("vi-VN", { maximumFractionDigits: 1 })} km ·{" "}
                {Math.ceil(route.summary.travelTimeInSeconds / 60)} phút
              </Badge>
            )}
          </div>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <strong>{atDestination ? `Giữ vị trí tại ${target.name}` : `Đi tới ${target.name}`}</strong>
          {streets.length ? (
            <ol aria-label="Thứ tự các đường trên tuyến" className="flex flex-wrap items-center gap-2">
              {streets.map((street, index) => (
                <li key={`${index}:${street}`} className="flex items-center gap-2">
                  {index > 0 && <ArrowRight aria-hidden className="size-4" />}
                  <Badge variant="secondary">
                    {index + 1}. {street}
                  </Badge>
                </li>
              ))}
            </ol>
          ) : (
            <p role="status">{message || "Tuyến chưa có tên đường."}</p>
          )}
        </CardContent>
      </Card>
    </section>
  );
}
