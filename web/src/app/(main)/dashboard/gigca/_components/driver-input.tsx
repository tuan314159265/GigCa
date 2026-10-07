"use client";

import { useEffect, useState } from "react";
import { LocateFixed, RefreshCw } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field, FieldGroup, FieldLabel, FieldSet } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useGigca } from "../../_components/gigca/gigca-provider";
import { previewOnly } from "../../_components/gigca/preview";
import type { DriverInput } from "../../_components/gigca/types";

export function DriverForm() {
  const { input, run, busy } = useGigca();
  const [draft, setDraft] = useState(input);
  const [gpsError, setGpsError] = useState("");
  const [locating, setLocating] = useState(false);
  useEffect(() => setDraft(input), [input]);
  const update = (key: keyof DriverInput["context"], value: number) =>
    setDraft((current) => ({ ...current, context: { ...current.context, [key]: value } }));
  function locate() {
    setGpsError("");
    if (!navigator.geolocation) {
      setGpsError("Trình duyệt không hỗ trợ vị trí.");
      return;
    }
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      ({ coords }) => {
        setDraft((current) => ({
          ...current,
          context: {
            ...current.context,
            current_lat: coords.latitude,
            current_lng: coords.longitude,
          },
        }));
        setLocating(false);
      },
      () => {
        setGpsError("Không lấy được vị trí. Bạn có thể nhập tọa độ.");
        setLocating(false);
      },
      { timeout: 10000 },
    );
  }
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        void run(draft);
      }}
      className="flex flex-col gap-4 p-4"
    >
      <FieldSet disabled={previewOnly || busy}>
        <FieldGroup className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          {(
            [
              ["idle_duration_min", "Đã chờ (phút)", 0, 1440, 1],
              ["horizon_min", "Xét trong (phút)", 1, 480, 1],
              ["max_reposition_km", "Di chuyển tối đa (km)", 0.1, 50, 0.1],
            ] as const
          ).map(([key, label, min, max, step]) => (
            <Field key={key} data-disabled={previewOnly || busy}>
              <FieldLabel htmlFor={key}>{label}</FieldLabel>
              <Input
                id={key}
                type="number"
                required
                min={min}
                max={max}
                step={step}
                value={draft.context[key]}
                onChange={(event) => update(key, event.target.value === "" ? NaN : Number(event.target.value))}
              />
            </Field>
          ))}
          <Field data-disabled={previewOnly || busy}>
            <FieldLabel htmlFor="rain-tolerance">Chịu mưa</FieldLabel>
            <Select
              value={draft.rain_tolerance_level}
              disabled={previewOnly || busy}
              onValueChange={(value) => setDraft({ ...draft, rain_tolerance_level: value })}
            >
              <SelectTrigger id="rain-tolerance" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectGroup>
                  <SelectItem value="low">Ít</SelectItem>
                  <SelectItem value="medium">Vừa</SelectItem>
                  <SelectItem value="high">Cao</SelectItem>
                </SelectGroup>
              </SelectContent>
            </Select>
          </Field>
        </FieldGroup>
        <div className="flex flex-wrap items-center gap-2">
          <Button type="button" variant="outline" onClick={locate} disabled={previewOnly || busy || locating}>
            <LocateFixed data-icon="inline-start" />
            {locating ? "Đang lấy vị trí" : "Vị trí của tôi"}
          </Button>
          <Button
            type="submit"
            disabled={
              previewOnly ||
              busy ||
              !Number.isFinite(draft.context.current_lat) ||
              !Number.isFinite(draft.context.current_lng)
            }
          >
            <RefreshCw data-icon="inline-start" />
            {busy ? "Đang tính" : "Tính gợi ý"}
          </Button>
          <details className="ml-auto text-sm">
            <summary className="cursor-pointer text-muted-foreground">Tọa độ</summary>
            <FieldGroup className="mt-3 grid grid-cols-2 gap-3">
              <Field>
                <FieldLabel htmlFor="latitude">Vĩ độ</FieldLabel>
                <Input
                  id="latitude"
                  type="number"
                  required
                  min={-90}
                  max={90}
                  step="any"
                  value={Number.isFinite(draft.context.current_lat) ? draft.context.current_lat : ""}
                  onChange={(event) =>
                    update("current_lat", event.target.value === "" ? NaN : Number(event.target.value))
                  }
                />
              </Field>
              <Field>
                <FieldLabel htmlFor="longitude">Kinh độ</FieldLabel>
                <Input
                  id="longitude"
                  type="number"
                  required
                  min={-180}
                  max={180}
                  step="any"
                  value={Number.isFinite(draft.context.current_lng) ? draft.context.current_lng : ""}
                  onChange={(event) =>
                    update("current_lng", event.target.value === "" ? NaN : Number(event.target.value))
                  }
                />
              </Field>
            </FieldGroup>
          </details>
        </div>
      </FieldSet>
      {gpsError && (
        <Alert variant="destructive">
          <AlertDescription>{gpsError}</AlertDescription>
        </Alert>
      )}
    </form>
  );
}
