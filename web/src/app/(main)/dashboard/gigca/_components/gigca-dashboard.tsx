"use client";

import { useEffect, useState } from "react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

import { GigcaMap } from "../../_components/gigca/gigca-map";
import { useGigca } from "../../_components/gigca/gigca-provider";
import { modes } from "../../_components/gigca/labels";
import { previewOnly } from "../../_components/gigca/preview";
import type { Objective } from "../../_components/gigca/types";
import { DirectionDetails } from "./direction-details";
import { DirectionOptions } from "./direction-options";
import { DriverAssistant } from "./driver-assistant";
import { DriverForm } from "./driver-input";

export function GigcaDashboard() {
  const [hydrated, setHydrated] = useState(false);
  const [selected, setSelected] = useState<Objective>("max_trip_value");
  const { error, busy, retry, result, capabilitiesError, initialize } = useGigca();
  useEffect(() => {
    initialize();
    setHydrated(true);
  }, [initialize]);
  if (!hydrated)
    return (
      <div aria-busy="true" aria-label="Đang tải GigCa" className="flex min-w-0 flex-col gap-4 p-4">
        <div className="h-8 w-48 animate-pulse rounded bg-muted" />
        <div className="h-64 w-full animate-pulse rounded-lg bg-muted" />
        <div className="h-80 w-full animate-pulse rounded-lg bg-muted" />
      </div>
    );
  let badgeLabel = "Chọn vị trí xuất phát";
  if (result) badgeLabel = modes[result.snapshot.mode];
  if (previewOnly) badgeLabel = "Preview · dữ liệu mẫu";
  return (
    <div data-content-padding="false" className="flex min-w-0 flex-col">
      <div className="flex items-center justify-between gap-3 px-4 py-5">
        <h1 className="font-semibold text-2xl">Gợi ý cho tôi</h1>
        <Badge variant="outline">{badgeLabel}</Badge>
      </div>
      {capabilitiesError && (
        <Alert variant="destructive">
          <AlertTitle>Backend chưa sẵn sàng</AlertTitle>
          <AlertDescription>{capabilitiesError}</AlertDescription>
        </Alert>
      )}
      {result?.research_driver_id && (
        <Alert>
          <AlertTitle>Mô phỏng {result.research_driver_id}</AlertTitle>
          <AlertDescription>
            Lịch sử và mưa tổng hợp. Bối cảnh tái hiện: {new Date(result.generated_at).toLocaleString("vi-VN")}.
          </AlertDescription>
        </Alert>
      )}
      {error && (
        <Alert variant="destructive">
          <AlertTitle>Không cập nhật được gợi ý</AlertTitle>
          <AlertDescription>
            {error}
            <Button variant="outline" size="sm" disabled={busy} onClick={() => void retry()}>
              Thử lại
            </Button>
          </AlertDescription>
        </Alert>
      )}
      <DriverForm />
      <DirectionOptions selected={selected} onSelect={setSelected} />
      <GigcaMap selected={selected} />
      {result && <DirectionDetails key={selected} selected={selected} />}
      <DriverAssistant selected={selected} onSelect={setSelected} />
    </div>
  );
}
