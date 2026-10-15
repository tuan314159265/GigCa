"use client";

import { Badge } from "@/components/ui/badge";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { useGigca } from "../../_components/gigca/gigca-provider";
import { directions, statuses } from "../../_components/gigca/labels";
import { objectives, type Objective } from "../../_components/gigca/types";

export function DirectionOptions({ selected, onSelect }: { selected: Objective; onSelect: (key: Objective) => void }) {
  const { result, busy, error } = useGigca();
  const hasResult = Boolean(result);
  const message = busy
    ? hasResult ? "Đang cập nhật gợi ý…" : "Đang tính gợi ý…"
    : hasResult
      ? error ? "Chưa cập nhật được. Bạn đang xem kết quả lần trước." : "Đã tính xong — chọn một hướng bên dưới để xem gợi ý."
      : "Bấm Tính gợi ý để xem bốn hướng bên dưới.";
  return (
    <section aria-label="Phương án của bạn" className="min-w-0 px-4 pb-3">
      <p id="direction-options-status" role="status" aria-live="polite" className="mb-3 text-sm font-medium">
        {message}
      </p>
      <ToggleGroup
        type="single"
        value={hasResult ? selected : ""}
        disabled={!hasResult || busy}
        aria-describedby="direction-options-status"
        onValueChange={(value) => { if (hasResult && !busy && objectives.includes(value as Objective)) onSelect(value as Objective); }}
        data-ready={hasResult ? "true" : "false"}
        className="gigca-direction-switch gigca-direction-cards grid w-full grid-cols-1 gap-0 sm:grid-cols-2 lg:grid-cols-4"
        spacing={0}
        aria-label="Chọn hướng gợi ý"
      >
        {objectives.map((key) => {
          const direction = result?.objectives[key];
          const Icon = directions[key].icon;
          return (
            <ToggleGroupItem key={key} value={key} className={hasResult && !busy ? "cursor-pointer" : "cursor-default"}>
              <span className="flex items-center gap-2"><Icon />{directions[key].title}</span>
              {direction && <Badge variant="secondary">{statuses[direction.status]}</Badge>}
            </ToggleGroupItem>
          );
        })}
      </ToggleGroup>
    </section>
  );
}
