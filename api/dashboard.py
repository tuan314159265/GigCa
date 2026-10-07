"""Local dashboard API. Reuses the Data Explorer proxies and the existing engine."""
from __future__ import annotations

import json
import math
import os
import re
from dataclasses import asdict
from http.server import ThreadingHTTPServer
from urllib.parse import urlsplit

from data.engine_bridge import load_for_engine
from data.engine_interface import EngineDataInterface
from data.etl.pipeline import build_engine_input
from engine.src.engine import run_driver_engine, select_weather
from engine.src.types import DriverContext, DriverPreferences
from api.provider_proxy import GigCaHandler, ROOT, read_tomtom_key, tomtom_url, request_upstream, cached, get_traffic


def recommend(payload: dict, *, include_snapshot: bool = False) -> dict:
    mode = payload.get("mode", "simulation")
    if mode not in ("simulation", "sample", "pipeline", "database", "live"):
        raise ValueError("Chế độ dữ liệu không hợp lệ.")
    raw = payload.get("context", {})
    limits = {"current_lat": (-90, 90, 10.7769), "current_lng": (-180, 180, 106.7009),
              "idle_duration_min": (0, 1440, 25), "horizon_min": (1, 480, 180),
              "max_reposition_km": (0, 50, 3)}
    values = {}
    for name, (low, high, default) in limits.items():
        value = raw.get(name, default)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
            raise ValueError(f"Giá trị {name} không hợp lệ.")
        if name in ("idle_duration_min", "horizon_min") and value != int(value):
            raise ValueError(f"Giá trị {name} phải là số nguyên.")
        values[name] = value
    prefs = DriverPreferences(rain_tolerance_level=payload.get("rain_tolerance_level", "medium"))
    if mode == "live":
        if "current_lat" not in raw or "current_lng" not in raw:
            raise ValueError("Cần tọa độ hiện tại để lấy dữ liệu live.")
        from data.live_collector import collect_for_origin
        snapshot = collect_for_origin(values["current_lat"], values["current_lng"], values["horizon_min"], values["max_reposition_km"])
    elif mode == "database":
        if not os.environ.get("GIGCA_DATABASE_URL"):
            raise RuntimeError("Chưa cấu hình PostgreSQL/PostGIS. Đặt GIGCA_DATABASE_URL trên máy chủ.")
        traffic_warning = None
        try:
            read_tomtom_key()
        except RuntimeError:
            pass
        else:
            try:
                lat, lng = values["current_lat"], values["current_lng"]
                radius = min(10000, max(100, values["max_reposition_km"] * 1000))
                cached(f"dashboard_flow:{lat:.5f}:{lng:.5f}:{radius}", 45,
                       lambda: get_traffic(lat, lng, radius))
            except Exception:
                traffic_warning = "Chưa cập nhật được giao thông trực tuyến; Engine chỉ dùng quan sát còn hạn trong database."
        try:
            snapshot = EngineDataInterface.from_env().get_engine_input(
                os.environ.get("GIGCA_AREA_ID", "hcmc_demo_point_01"),
                rain_tolerance_level=prefs.rain_tolerance_level,
                forecast_hours=max(1, math.ceil(values["horizon_min"] / 60)))
            if traffic_warning:
                snapshot.setdefault("limitations", []).append(traffic_warning)
        except Exception:
            raise RuntimeError("Không đọc được PostgreSQL/PostGIS. Kiểm tra kết nối, migrations và dữ liệu khu vực.") from None
    elif mode == "pipeline":
        snapshot = build_engine_input(ROOT / "data/samples")
    else:
        filename = (ROOT / "data/fixtures/hcmc_full_simulated_snapshot.json" if mode == "simulation"
                    else ROOT / "data/samples/engine_input/hcmc_demo_snapshot.json")
        snapshot = json.loads(filename.read_text(encoding="utf-8"))
    data = load_for_engine(snapshot)
    result = asdict(run_driver_engine(data, DriverContext(**values), prefs))
    result["snapshot"] = {"id": data.snapshot_id, "mode": mode, "as_of": data.generated_at,
                          "sources": snapshot.get("data_status", []),
                          "limitations": snapshot.get("limitations", [])}
    selected_weather, _ = select_weather(data, DriverContext(**values))
    result["weather"] = [asdict(hour) for hour in selected_weather]
    result["origin_used"] = {"lat": values["current_lat"], "lng": values["current_lng"]}
    result["is_demo"] = mode == "simulation"

    result["places"] = [{"id": p.poi_id, "name": p.name, "lat": p.latitude, "lng": p.longitude,
                         "category": p.category, "verified": p.verified, "parking_allowed": p.parking_allowed}
                        for p in data.poi_candidates]
    result["areas"] = [{"id": a.area_id, "name": a.area_name or a.area_id,
                        "lat": a.representative_point.get("latitude"), "lng": a.representative_point.get("longitude")}
                       for a in data.areas]
    if include_snapshot:
        result["_input_snapshot"] = snapshot
    return result


class DashboardHandler(GigCaHandler):
    def do_GET(self):
        tile = re.fullmatch(r"/api/traffic/tiles/(\d{1,2})/(\d+)/(\d+)\.png", urlsplit(self.path).path)
        if tile:
            zoom, x, y = map(int, tile.groups())
            if zoom > 22 or x >= 2**zoom or y >= 2**zoom:
                self.send_json({"error": "Tọa độ tile không hợp lệ."}, 400)
                return
            try:
                # Relative speed overlay: green/yellow/red roads, not vehicle counts.
                endpoint = f"https://api.tomtom.com/traffic/map/4/tile/flow/relative/{zoom}/{x}/{y}.png"
                body, content_type = cached(f"traffic_tile:{zoom}:{x}:{y}", 30,
                    lambda: request_upstream(tomtom_url(endpoint, {"tileSize": 256}), accept="image/png"))
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Cache-Control", "private, max-age=30")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except (RuntimeError, OSError) as exc:
                self.send_json({"error": str(exc)}, 502)
            return
        if urlsplit(self.path).path == "/api/capabilities":
            try:
                read_tomtom_key()
                tomtom = True
            except RuntimeError:
                tomtom = False
            self.send_json({"tomtom": tomtom, "database": bool(os.environ.get("GIGCA_DATABASE_URL")),
                            "recommendations": True, "modes": ["simulation", "sample", "pipeline", "database", "live"]})
            return
        # Serve only APIs here, not repository files.
        path = urlsplit(self.path).path
        if path not in {"/api/health", "/api/weather", "/api/pois", "/api/traffic", "/api/route"} and not re.fullmatch(r"/api/map/tiles/\d{1,2}/\d+/\d+\.png", path):
            self.send_error(404)
            return
        super().do_GET()

    def do_POST(self):
        if urlsplit(self.path).path != "/api/recommendations":
            self.send_error(404)
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 16384:
                raise ValueError("Yêu cầu không hợp lệ.")
            payload = json.loads(self.rfile.read(size))
            if not isinstance(payload, dict) or not isinstance(payload.get("context", {}), dict):
                raise ValueError("Yêu cầu không hợp lệ.")
            self.send_json(recommend(payload))
        except (ValueError, TypeError, KeyError) as exc:
            self.send_json({"error": str(exc)}, 400)
        except RuntimeError as exc:
            self.send_json({"error": str(exc)}, 503)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            return
        except Exception:
            self.send_json({"error": "Không thể tính gợi ý. Kiểm tra dữ liệu trên máy chủ."}, 500)


def load_local_settings():
    path = ROOT / ".env"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        name, sep, value = line.strip().partition("=")
        if sep and name.strip() in {"GIGCA_DATABASE_URL", "GIGCA_AREA_ID", "GIGCA_DATA_MODE", "GIGCA_SESSION_DB", "SSL_CERT_FILE"}:
            value = value.strip().strip("\"'")
            if value:
                os.environ.setdefault(name.strip(), value)


if __name__ == "__main__":
    load_local_settings()
    server = ThreadingHTTPServer(("127.0.0.1", 8000), DashboardHandler)
    print("GigCa Dashboard API: http://127.0.0.1:8000", flush=True)
    server.serve_forever()
