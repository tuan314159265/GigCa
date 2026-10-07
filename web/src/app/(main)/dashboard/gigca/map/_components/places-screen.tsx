"use client";

import { useState } from "react";
import { cn } from "cn";
import { MapPin, Search } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Empty, EmptyHeader, EmptyTitle } from "@/components/ui/empty";
import { InputGroup, InputGroupAddon, InputGroupInput } from "@/components/ui/input-group";
import { ScrollArea } from "@/components/ui/scroll-area";
import { GigcaMap } from "../../../_components/gigca/gigca-map";
import { useGigca } from "../../../_components/gigca/gigca-provider";
import type { Place } from "../../../_components/gigca/types";

export function PlacesScreen() {
  const { result } = useGigca();
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<Place | null>(null);
  const places = [...(result?.places ?? []), ...(result?.areas ?? [])].filter((place) =>
    place.name.toLocaleLowerCase("vi-VN").includes(query.toLocaleLowerCase("vi-VN")),
  );
  return (
    <div data-content-padding="false" className="grid min-w-0 lg:grid-cols-[350px_minmax(0,1fr)] lg:divide-x">
      <Card className="rounded-none ring-0">
        <CardHeader>
          <CardTitle>Bản đồ & điểm chờ</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <InputGroup>
            <InputGroupInput
              aria-label="Tìm điểm chờ"
              placeholder="Tìm điểm chờ…"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
            <InputGroupAddon>
              <Search />
            </InputGroupAddon>
          </InputGroup>
          <ScrollArea className="h-72 lg:h-[calc(100dvh-190px)]">
            <div className="flex flex-col gap-3 p-px">
              {places.map((place) => (
                <button
                  type="button"
                  key={place.id}
                  aria-pressed={selected?.id === place.id}
                  onClick={() => setSelected(place)}
                  className={cn(
                    "flex flex-col gap-3 rounded-xl border p-3 text-left text-sm hover:bg-muted/50 focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/50",
                    selected?.id === place.id && "border-primary bg-muted/50",
                  )}
                >
                  <span className="flex items-start gap-2">
                    <MapPin className="mt-0.5 size-4 shrink-0" />
                    {place.name}
                  </span>
                  <span className="flex flex-wrap gap-2">
                    <Badge variant="outline">{({ cafe: "Cà phê", parking: "Bãi đỗ xe", gas_station: "Cây xăng" } as Record<string, string>)[place.category ?? ""] ?? place.category ?? "Khu vực"}</Badge>
                    {place.parking_allowed && <Badge variant="secondary">Có chỗ đỗ xe</Badge>}
                  </span>
                </button>
              ))}
            </div>
            {!places.length && (
              <Empty>
                <EmptyHeader>
                  <EmptyTitle>Không có điểm phù hợp</EmptyTitle>
                </EmptyHeader>
              </Empty>
            )}
          </ScrollArea>
        </CardContent>
      </Card>
      <div className="min-w-0">
        <GigcaMap focusedPlace={selected} />
      </div>
    </div>
  );
}
