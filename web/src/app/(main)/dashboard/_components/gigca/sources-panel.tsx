"use client";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useGigca } from "./gigca-provider";
import { modes } from "./labels";
import { previewOnly } from "./preview";

const datasets: Record<string, string> = {
  poi: "Địa điểm",
  weather: "Thời tiết",
  traffic: "Giao thông",
  places: "Điểm chờ",
  areas: "Khu vực",
  fares: "Giá cước",
  rest_spots: "Điểm nghỉ",
  poi_density_grid: "Mật độ POI",
  waiting_location_candidates: "Điểm chờ ứng viên",
  events: "Sự kiện",
  routing: "Định tuyến",
  road_incidents: "Sự cố đường",
  verified_waiting_places: "Điểm nghỉ đã xác minh",
  vehicle_density: "Mật độ xe",
  booking_and_destinations: "Cuốc & điểm trả",
  trip_value: "Giá trị cuốc",
};
export function SourcesPanel() {
  const { result, tomtom, database } = useGigca();
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap gap-2">
        <Badge variant="secondary">{modes[result?.snapshot.mode ?? "simulation"]}</Badge>
        <Badge variant="outline">TomTom · {tomtom ? "Đã cấu hình" : "Chưa cấu hình"}</Badge>
        <Badge variant="outline">PostgreSQL · {database ? "Đã cấu hình" : "Chưa cấu hình"}</Badge>
        {previewOnly && <Badge variant="outline">Không gọi API</Badge>}
        {result && (
          <Badge variant="outline">Snapshot {new Date(result.snapshot.as_of).toLocaleDateString("vi-VN")}</Badge>
        )}
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Nguồn dữ liệu</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Dữ liệu</TableHead>
                <TableHead>Trạng thái</TableHead>
                <TableHead>Nguồn</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {result?.snapshot.sources.map((source) => (
                <TableRow key={source.dataset}>
                  <TableCell>{datasets[source.dataset] ?? source.dataset}</TableCell>
                  <TableCell>
                    <Badge variant="outline">
                      {(
                        {
                          available: "Có dữ liệu",
                          simulated: "Mô phỏng",
                          missing: "Thiếu",
                          not_integrated: "Chưa tích hợp",
                          partial: "Một phần",
                        } as Record<string, string>
                      )[source.status] ?? source.status}
                    </Badge>
                  </TableCell>
                  <TableCell className="whitespace-normal">{source.reason}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
      <details className="text-sm">
        <summary className="cursor-pointer font-medium">Giả định & giới hạn dữ liệu</summary>
        <ul className="mt-3 flex list-disc flex-col gap-2 pl-5 text-muted-foreground">
          {[
            ...new Set([
              ...(result?.assumptions_used ?? []),
              ...(result?.data_quality_warnings ?? []),
              ...(result?.snapshot.limitations ?? []),
            ]),
          ].map((text) => (
            <li key={text}>{text}</li>
          ))}
        </ul>
      </details>
    </div>
  );
}
