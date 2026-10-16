"use client";

import Image from "next/image";
import { useEffect, useRef, useState } from "react";
import { Camera, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Empty, EmptyHeader, EmptyTitle } from "@/components/ui/empty";
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { api } from "./api";
import { roadGroupGeometry, type RoadGroup, type RoadRoute } from "./routes";
import { startVisiblePolling } from "./visible-poll";

interface TrafficCamera {
  id: string;
  name: string;
  distance_to_route_m: number;
  image_url: string;
}
interface CameraResult {
  cameras: TrafficCamera[];
  source_page: string;
  catalog_fetched_at: string | null;
}

export function TrafficCameraPanel({ route, road }: { route: RoadRoute; road: RoadGroup }) {
  const [cameras, setCameras] = useState<TrafficCamera[]>([]);
  const [selected, setSelected] = useState(0);
  const failed = useRef<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const [frame, setFrame] = useState<{ src: string; cameraId: string; fetchedAt: string } | null>(null);
  const currentFrame = useRef<typeof frame>(null);
  const [refresh, setRefresh] = useState(0);
  const geometry = JSON.stringify(roadGroupGeometry(route, road));
  useEffect(() => {
    const controller = new AbortController();
    setCameras([]);
    failed.current = [];
    setSelected(0);
    setMessage("");
    setLoading(true);
    const lines = JSON.parse(geometry) as number[][][];
    if (!lines.length) {
      setMessage("Chưa có tọa độ đoạn đường để tìm camera.");
      setLoading(false);
      return;
    }
    void api<CameraResult>("/api/v1/cameras/near-route", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ lines, radius_m: 300 }),
      signal: controller.signal,
    })
      .then((data) => {
        if (!controller.signal.aborted) setCameras(data.cameras);
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted)
          setMessage(error instanceof Error ? error.message : "Không tải được danh sách camera.");
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [geometry]);
  const camera = cameras[selected];
  const image = frame?.cameraId === camera?.id ? frame?.src : null;
  const fetchedAt = frame?.cameraId === camera?.id ? frame?.fetchedAt : "";
  useEffect(
    () => () => {
      if (currentFrame.current) URL.revokeObjectURL(currentFrame.current.src);
    },
    [],
  );
  useEffect(() => {
    if (!camera) return;
    return startVisiblePolling(() => {
      failed.current = [];
      setRefresh((value) => value + 1);
    }, 30000);
  }, [camera?.id]);
  useEffect(() => {
    const controller = new AbortController();
    if (!camera) return;
    if (currentFrame.current?.cameraId !== camera.id) setMessage("Đang tải ảnh camera…");
    void fetch(`${camera.image_url}?refresh=${refresh}`, {
      signal: AbortSignal.any([controller.signal, AbortSignal.timeout(20000)]),
      cache: "no-store",
    })
      .then(async (response) => {
        if (!response.ok) throw new Error("Camera hiện không tải được ảnh.");
        if (!response.headers.get("content-type")?.startsWith("image/"))
          throw new Error("Nguồn camera không trả ảnh hợp lệ.");
        const blob = await response.blob();
        if (controller.signal.aborted) return;
        const objectUrl = URL.createObjectURL(blob);
        const fetched = response.headers.get("x-camera-fetched-at");
        const next = {
          src: objectUrl,
          cameraId: camera.id,
          fetchedAt: fetched && Number.isFinite(Date.parse(fetched)) ? fetched : new Date().toISOString(),
        };
        const previous = currentFrame.current;
        currentFrame.current = next;
        setFrame(next);
        if (previous) URL.revokeObjectURL(previous.src);
        setMessage("");
      })
      .catch(() => {
        if (controller.signal.aborted) return;
        if (currentFrame.current?.cameraId === camera.id) {
          setMessage("Chưa cập nhật được ảnh · đang giữ ảnh lần tải trước.");
          return;
        }
        failed.current = [...new Set([...failed.current, camera.id])];
        const next = cameras.findIndex((item, index) => index > selected && !failed.current.includes(item.id));
        if (next >= 0) setSelected(next);
        else setMessage("Các camera gần đoạn đường hiện không tải được ảnh.");
      });
    return () => {
      controller.abort();
    };
  }, [camera?.id, camera?.image_url, cameras, selected, refresh]);
  return (
    <section aria-label="Camera gần đoạn đường" className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 className="flex items-center gap-2 font-medium">
          <Camera className="size-4" />
          Camera gần tuyến
        </h3>
        {camera && (
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              failed.current = [];
              setRefresh((value) => value + 1);
            }}
          >
            <RefreshCw data-icon="inline-start" />
            Làm mới
          </Button>
        )}
      </div>
      {camera && (
        <Select value={camera.id} onValueChange={(id) => setSelected(cameras.findIndex((item) => item.id === id))}>
          <SelectTrigger aria-label="Chọn camera gần tuyến" className="w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectGroup>
              {cameras.map((item) => (
                <SelectItem key={item.id} value={item.id}>
                  {item.name} · {item.distance_to_route_m} m
                </SelectItem>
              ))}
            </SelectGroup>
          </SelectContent>
        </Select>
      )}
      {image && camera ? (
        <>
          <div className="relative aspect-video w-full overflow-hidden rounded-sm bg-muted">
            <Image
              src={image}
              alt={`Camera ${camera.name}`}
              fill
              unoptimized
              sizes="(min-width: 1024px) 900px, 100vw"
              className="object-contain"
              onError={() => {
                if (currentFrame.current) URL.revokeObjectURL(currentFrame.current.src);
                currentFrame.current = null;
                setFrame(null);
                setMessage("Ảnh camera không hiển thị được.");
              }}
            />
          </div>
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <Badge variant="outline">Cách tuyến {camera.distance_to_route_m} m</Badge>
            <Badge variant="secondary">Tự cập nhật 30 giây</Badge>
            {fetchedAt && <span>Tải ảnh lúc {new Date(fetchedAt).toLocaleTimeString("vi-VN")}</span>}
            {message && <span role="status">{message}</span>}
          </div>
        </>
      ) : (
        <Empty>
          <EmptyHeader>
            <EmptyTitle>
              {loading ? "Đang tìm camera…" : message || "Không có camera công khai trong 300 m quanh đoạn đường."}
            </EmptyTitle>
          </EmptyHeader>
        </Empty>
      )}
      <a
        href="https://giaothong.hochiminhcity.gov.vn/Map.aspx"
        target="_blank"
        rel="noreferrer"
        className="text-sm underline"
      >
        Nguồn: Cổng giao thông TP.HCM
      </a>
    </section>
  );
}
