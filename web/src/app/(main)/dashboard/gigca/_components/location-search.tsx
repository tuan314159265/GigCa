"use client";

import { useRef, useState, type ReactNode } from "react";
import { Search } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { api } from "../../_components/gigca/api";

interface Location { id: string; name: string; address: string; lat: number; lng: number }
export function LocationSearch({ disabled, onSelect, labelAction }: {
  disabled: boolean;
  labelAction?: ReactNode;
  onSelect: (lat: number, lng: number) => void;
}) {
  const [query, setQuery] = useState("");
  const [places, setPlaces] = useState<Location[]>([]);
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const requestId = useRef(0);
  async function search() {
    const id = ++requestId.current;
    setLoading(true); setMessage(""); setPlaces([]);
    try {
      const response = await api<{ places: Location[] }>(`/api/locations/search?q=${encodeURIComponent(query.trim())}`);
      if (id !== requestId.current) return;
      setPlaces(response.places);
      if (!response.places.length) setMessage("Không tìm thấy địa điểm. Thử thêm quận hoặc thành phố.");
    } catch (error) {
      if (id === requestId.current) setMessage(error instanceof Error ? error.message : "Không tìm được địa điểm.");
    } finally { if (id === requestId.current) setLoading(false); }
  }
  return <Field>
    <div className="flex flex-wrap items-center gap-3">
      <FieldLabel htmlFor="location-search">Vị trí xuất phát</FieldLabel>
      {labelAction}
    </div>
    <div className="flex gap-2">
      <Input id="location-search" placeholder="Tên địa điểm hoặc địa chỉ, ví dụ: Chợ Bến Thành, TP.HCM"
        value={query} disabled={disabled} maxLength={160}
        onChange={(event) => { requestId.current++; setLoading(false); setQuery(event.target.value); setPlaces([]); setMessage(""); }}
        onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); if (query.trim().length >= 2 && !loading && !disabled) void search(); } }} />
      <Button type="button" variant="outline" disabled={disabled || loading || query.trim().length < 2}
        onClick={() => void search()}><Search data-icon="inline-start" />{loading ? "Đang tìm" : "Tìm"}</Button>
    </div>
    {places.length > 0 && <div className="flex flex-col gap-2" aria-label="Kết quả tìm địa điểm">
      {places.map((place) => <Button key={place.id} type="button" variant="outline" disabled={disabled}
        className="h-auto justify-start whitespace-normal py-3 text-left"
        onClick={() => { onSelect(place.lat, place.lng); setQuery(place.name); setPlaces([]); setMessage("Đã chọn vị trí. Bấm Tính gợi ý để cập nhật."); }}>
        <span className="flex flex-col gap-1"><span>{place.name}</span>{place.address !== place.name && <span>{place.address}</span>}</span>
      </Button>)}
    </div>}
    {message && <Alert><AlertDescription>{message}</AlertDescription></Alert>}
  </Field>;
}
