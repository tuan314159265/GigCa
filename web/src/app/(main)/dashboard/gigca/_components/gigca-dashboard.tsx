"use client";

import { useState } from "react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { previewOnly } from "../../_components/gigca/preview";
import { Button } from "@/components/ui/button";
import { GigcaMap } from "../../_components/gigca/gigca-map";
import { useGigca } from "../../_components/gigca/gigca-provider";
import type { Objective } from "../../_components/gigca/types";
import { DirectionDetails } from "./direction-details";
import { DirectionOptions } from "./direction-options";
import { DriverForm } from "./driver-input";
import { modes } from "../../_components/gigca/labels";

export function GigcaDashboard() {
  const [selected, setSelected] = useState<Objective>("max_trip_value");
  const { error, busy, retry, result, capabilitiesError } = useGigca();
  return (
    <div data-content-padding="false" className="flex min-w-0 flex-col">
      <div className="flex items-center justify-between gap-3 px-4 py-5">
        <h1 className="font-semibold text-2xl">Gợi ý cho tôi</h1>
        <Badge variant="outline">
          {previewOnly
            ? "Preview · dữ liệu mẫu"
            : result
              ? modes[result.snapshot.mode]
              : "Chọn vị trí xuất phát"}
        </Badge>
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
    </div>
  );
}
