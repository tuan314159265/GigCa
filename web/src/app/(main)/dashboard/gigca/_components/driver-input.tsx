"use client";

import { useEffect, useState } from "react";
import { LocateFixed, RefreshCw } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field, FieldDescription, FieldGroup, FieldLabel, FieldSet } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useGigca } from "../../_components/gigca/gigca-provider";
import { previewOnly } from "../../_components/gigca/preview";
import type { DriverInput } from "../../_components/gigca/types";
import { LocationSearch } from "./location-search";

function mainInput(value: DriverInput): DriverInput {
  return {
    ...value,
    mode: value.mode === "research" ? "live" : value.mode,
    research_driver_id: undefined,
  };
}

export function DriverForm() {
  const { input, run, busy } = useGigca();
  const [draft, setDraft] = useState(() => mainInput(input));
  const [gpsError, setGpsError] = useState("");
  const [locating, setLocating] = useState(false);
  useEffect(() => setDraft(mainInput(input)), [input]);
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
        setGpsError("Không lấy được vị trí. Bạn có thể tìm địa điểm bằng tên hoặc nhập tọa độ.");
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
        <div className="grid min-w-0 items-start gap-4 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <LocationSearch
          labelAction={
          <Button type="button" variant="outline" onClick={locate} disabled={previewOnly || busy || locating}>
            <LocateFixed data-icon="inline-start" />
            {locating ? "Đang lấy vị trí" : "Vị trí của tôi"}
          </Button>
          }
          disabled={previewOnly || busy}
          onSelect={(lat, lng) => {
            setGpsError("");
            setDraft((current) => ({
              ...current,
              context: { ...current.context, current_lat: lat, current_lng: lng },
            }));
          }}
        />
          <div className="xl:pt-3">
            <FieldGroup className="grid grid-cols-2 gap-3">
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

          </div>
        </div>
        <FieldGroup className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          {(
            [
              ["idle_duration_min", "Đã chờ (phút)", 0, 1440, 1, "Số phút bạn đã chờ mà chưa nhận được cuốc mới."],
              [
                "horizon_min",
                "Xét trong (phút)",
                1,
                480,
                1,
                "Khoảng thời gian sắp tới dùng để đánh giá gợi ý và dự báo mưa.",
              ],
              [
                "max_reposition_km",
                "Di chuyển tối đa (km)",
                0.1,
                50,
                0.1,
                "Quãng đường tối đa bạn sẵn sàng đi từ vị trí hiện tại tới điểm được gợi ý.",
              ],
            ] as const
          ).map(([key, label, min, max, step, description]) => (
            <Field key={key} data-disabled={previewOnly || busy}>
              <FieldLabel htmlFor={key}>{label}</FieldLabel>
              <Input
                id={key}
                aria-describedby={`${key}-description`}
                type="number"
                required
                min={min}
                max={max}
                step={step}
                value={draft.context[key]}
                onChange={(event) => update(key, event.target.value === "" ? NaN : Number(event.target.value))}
              />
              <FieldDescription id={`${key}-description`}>{description}</FieldDescription>
            </Field>
          ))}
          <Field data-disabled={previewOnly || busy}>
            <FieldLabel htmlFor="rain-tolerance">Chịu mưa</FieldLabel>
            <Select
              value={draft.rain_tolerance_level}
              disabled={previewOnly || busy}
              onValueChange={(value) => setDraft({ ...draft, rain_tolerance_level: value })}
            >
              <SelectTrigger id="rain-tolerance" aria-describedby="rain-tolerance-description" className="w-full">
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
            <FieldDescription id="rain-tolerance-description">
              Ít: muốn tránh mưa; Vừa: chịu được mưa nhẹ; Cao: chấp nhận mưa nhiều hơn trước khi được gợi ý tránh mưa.
            </FieldDescription>
          </Field>
        </FieldGroup>
        <div className="flex flex-wrap items-center gap-2">

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
