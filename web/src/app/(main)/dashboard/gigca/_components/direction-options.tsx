"use client";

import { Badge } from "@/components/ui/badge";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { useGigca } from "../../_components/gigca/gigca-provider";
import { directions, statuses } from "../../_components/gigca/labels";
import { objectives, type Objective } from "../../_components/gigca/types";

export function DirectionOptions({ selected, onSelect }: { selected: Objective; onSelect: (key: Objective) => void }) {
  const { result, busy } = useGigca();
  return (
    <section aria-label="Phương án của bạn" className="min-w-0 px-4 pb-3">
      <ToggleGroup
        type="single"
        value={selected}
        onValueChange={(value) => { if (objectives.includes(value as Objective)) onSelect(value as Objective); }}
        className="gigca-direction-switch gigca-direction-cards grid w-full grid-cols-1 gap-0 sm:grid-cols-2 lg:grid-cols-4"
        spacing={0}
        aria-label="Chọn hướng gợi ý"
      >
        {objectives.map((key) => {
          const direction = result?.objectives[key];
          const Icon = directions[key].icon;
          return (
            <ToggleGroupItem key={key} value={key} disabled={!direction || busy}>
              <span className="flex items-center gap-2"><Icon />{directions[key].title}</span>
              {direction && <Badge variant="secondary">{statuses[direction.status]}</Badge>}
            </ToggleGroupItem>
          );
        })}
      </ToggleGroup>
    </section>
  );
}
