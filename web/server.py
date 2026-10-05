#!/usr/bin/env python3
"""Local web server with same-origin proxies for the GigCa live map demo.

The TomTom API key is read from the repository .env file and is never sent to
the browser, printed, or saved by this server.
"""

from __future__ import annotations

import json
import math
import os
import re
import threading
import time
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, unquote, urlencode, urlsplit
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CENTER = (10.7769, 106.7009)
TOMTOM_FLOW = "https://api.tomtom.com/traffic/services/4/flowSegmentData/absolute/10/json"
TOMTOM_INCIDENTS = "https://api.tomtom.com/traffic/services/5/incidentDetails"
TOMTOM_ROUTE = "https://api.tomtom.com/routing/1/calculateRoute"
TOMTOM_POI = "https://api.tomtom.com/search/2/poiSearch"
TOMTOM_TILE = "https://api.tomtom.com/map/1/tile/basic/main"
INCIDENT_FIELDS = (
    "{incidents{type,geometry{type,coordinates},properties{"
    "id,iconCategory,magnitudeOfDelay,events{description},startTime,endTime,"
    "from,to,length,delay,timeValidity}}}"
)
CACHE: dict[str, tuple[float, object]] = {}
CACHE_LOCK = threading.Lock()


def read_tomtom_key() -> str:
    env_path = ROOT / ".env"
    if not env_path.is_file():
        raise RuntimeError("Thiếu file .env chứa API_TOMTOM.")
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, value = stripped.split("=", 1)
        if name.strip() == "API_TOMTOM":
            key = value.strip().strip("\"'")
            if key:
                return key
    raise RuntimeError("API_TOMTOM chưa được cấu hình trong .env.")


def cached(key: str, ttl_seconds: int, fetcher):
    now = time.monotonic()
    with CACHE_LOCK:
        entry = CACHE.get(key)
        if entry and now - entry[0] < ttl_seconds:
            return entry[1]
    value = fetcher()
    with CACHE_LOCK:
        CACHE[key] = (time.monotonic(), value)
    return value


def request_upstream(url: str, *, accept: str = "application/json") -> tuple[bytes, str]:
    request = Request(
        url,
        headers={"Accept": accept, "User-Agent": "GigCa-Data-Explorer/0.1"},
    )
    try:
        with urlopen(request, timeout=20) as response:
            return response.read(), response.headers.get("Content-Type", accept)
    except HTTPError as exc:
        raise RuntimeError(f"Nhà cung cấp trả HTTP {exc.code}.") from None
    except URLError as exc:
        raise RuntimeError(f"Không kết nối được tới nhà cung cấp ({type(exc.reason).__name__}).") from None


def request_json(url: str) -> dict:
    body, _ = request_upstream(url)
    result = json.loads(body)
    if not isinstance(result, dict):
        raise RuntimeError("Nhà cung cấp trả dữ liệu không đúng định dạng.")
    return result


def number(params: dict[str, list[str]], name: str, default: float, low: float, high: float) -> float:
    try:
        value = float(params.get(name, [str(default)])[0])
    except (TypeError, ValueError):
        raise ValueError(f"Tham số {name} không hợp lệ.") from None
    if not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"Tham số {name} nằm ngoài phạm vi.")
    return value


def tomtom_url(endpoint: str, params: dict[str, object]) -> str:
    return f"{endpoint}?{urlencode({**params, 'key': read_tomtom_key()}, doseq=True)}"


def get_weather(lat: float, lon: float) -> dict:
    from data.db.live_observations import read_scheduled_weather

    return read_scheduled_weather(lat, lon)


def get_pois(lat: float, lon: float, radius: int, query: str) -> dict:
    params = {
        "lat": lat,
        "lon": lon,
        "radius": radius,
        "limit": 100,
        "language": "vi-VN",
    }
    response = request_json(tomtom_url(f"{TOMTOM_POI}/{query}.json", params))
    results = response.get("results", [])
    pois = []
    for item in results:
        position = item.get("position") or {}
        if position.get("lat") is None or position.get("lon") is None:
            continue
        pois.append(
            {
                "id": item.get("id"),
                "name": item.get("poi", {}).get("name") or item.get("address", {}).get("freeformAddress"),
                "category": (item.get("poi", {}).get("categories") or ["POI"])[0],
                "latitude": position["lat"],
                "longitude": position["lon"],
                "address": item.get("address", {}).get("freeformAddress"),
                "provider": "TomTom Search API",
            }
        )
    return {"provider": "TomTom Search API", "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "radius_m": radius, "pois": pois}


def get_traffic(lat: float, lon: float, radius: float) -> dict:
    flow = request_json(
        tomtom_url(
            TOMTOM_FLOW,
            {"point": f"{lat},{lon}", "unit": "KMPH", "openLr": "true"},
        )
    )
    lat_delta = radius / 111_000
    lon_delta = radius / (111_000 * max(0.2, math.cos(math.radians(lat))))
    bbox = f"{lon-lon_delta},{lat-lat_delta},{lon+lon_delta},{lat+lat_delta}"
    incidents = request_json(
        tomtom_url(
            TOMTOM_INCIDENTS,
            {
                "bbox": bbox,
                "fields": INCIDENT_FIELDS,
                "language": "en-GB",
                "timeValidityFilter": "present",
            },
        )
    )
    result = {
        "provider": "TomTom Traffic API",
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "center": {"latitude": lat, "longitude": lon},
        "flow": flow.get("flowSegmentData", {}),
        "incidents": incidents.get("incidents", []),
    }
    try:
        from data.db.live_observations import save_traffic_observation

        observation_id = save_traffic_observation(lat, lon, result["flow"])
        result["persistence"] = {"status": "saved", "observation_id": observation_id}
    except Exception as exc:
        # Keep the map proxy useful without a configured database, while making
        # the missing/failing persistence visible to local developers.
        status = "not_configured" if isinstance(exc, RuntimeError) else "failed"
        reason = str(exc) if status == "not_configured" else type(exc).__name__
        result["persistence"] = {"status": status, "reason": reason}
    return result


class GigCaHandler(SimpleHTTPRequestHandler):
    server_version = "GigCaDataExplorer/0.1"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, format_string: str, *args) -> None:
        # Avoid logging query values (coordinates and provider parameters).
        print(f"[{self.log_date_time_string()}] {self.command} {urlsplit(self.path).path}")

    def send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urlsplit(self.path)
        path = unquote(parsed.path)
        params = parse_qs(parsed.query)

        if path == "/.env" or path.startswith(("/.git", "/.venv", "/.cache")) or any(part.startswith(".") for part in path.split("/") if part):
            self.send_error(404)
            return
        if path == "/api/health":
            self.send_json({"status": "ok", "service": "GigCa local data explorer"})
            return

        try:
            if path == "/api/weather":
                lat = number(params, "lat", DEFAULT_CENTER[0], -90, 90)
                lon = number(params, "lon", DEFAULT_CENTER[1], -180, 180)
                payload = cached(f"weather:{lat:.3f}:{lon:.3f}", 600, lambda: get_weather(lat, lon))
                self.send_json(payload)
                return

            if path == "/api/pois":
                lat = number(params, "lat", DEFAULT_CENTER[0], -90, 90)
                lon = number(params, "lon", DEFAULT_CENTER[1], -180, 180)
                radius = int(number(params, "radius", 1500, 100, 5000))
                query = params.get("query", ["cafe"])[0].strip().lower()
                if not re.fullmatch(r"[a-z0-9 -]{2,40}", query):
                    raise ValueError("Từ khóa POI không hợp lệ.")
                payload = cached(f"pois:{lat:.3f}:{lon:.3f}:{radius}:{query}", 300, lambda: get_pois(lat, lon, radius, query))
                self.send_json(payload)
                return

            if path == "/api/traffic":
                lat = number(params, "lat", DEFAULT_CENTER[0], -90, 90)
                lon = number(params, "lon", DEFAULT_CENTER[1], -180, 180)
                radius = number(params, "radius", 1500, 100, 5000)
                payload = cached(f"traffic:{lat:.4f}:{lon:.4f}:{radius}", 45, lambda: get_traffic(lat, lon, radius))
                self.send_json(payload)
                return

            if path == "/api/route":
                origin_lat = number(params, "origin_lat", DEFAULT_CENTER[0], -90, 90)
                origin_lon = number(params, "origin_lon", DEFAULT_CENTER[1], -180, 180)
                dest_lat = number(params, "destination_lat", 10.7796, -90, 90)
                dest_lon = number(params, "destination_lon", 106.6932, -180, 180)
                locations = f"{origin_lat},{origin_lon}:{dest_lat},{dest_lon}"
                response = request_json(
                    tomtom_url(
                        f"{TOMTOM_ROUTE}/{locations}/json",
                        {"traffic": "true", "travelMode": "motorcycle", "sectionType": ["traffic", "travelMode"]},
                    )
                )
                routes = response.get("routes", [])
                if not routes:
                    raise RuntimeError("TomTom không tìm được tuyến giữa hai điểm này.")
                self.send_json(
                    {
                        "provider": "TomTom Routing API",
                        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                        "travel_mode": "motorcycle",
                        "route": routes[0],
                    }
                )
                return

            match = re.fullmatch(r"/api/map/tiles/(\d{1,2})/(\d+)/(\d+)\.png", path)
            if match:
                zoom, x, y = map(int, match.groups())
                if zoom > 22 or x >= 2**zoom or y >= 2**zoom:
                    self.send_error(400, "Tile coordinate outside range")
                    return
                tile_path = f"{TOMTOM_TILE}/{zoom}/{x}/{y}.png"
                body, content_type = request_upstream(tomtom_url(tile_path, {"view": "Unified"}), accept="image/png")
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Cache-Control", "public, max-age=300")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

        except (ValueError, RuntimeError, OSError, json.JSONDecodeError) as exc:
            self.send_json({"error": str(exc)}, 502 if isinstance(exc, RuntimeError) else 400)
            return

        return super().do_GET()


def main() -> None:
    port = int(os.environ.get("GIGCA_WEB_PORT", "8000"))
    host = os.environ.get("GIGCA_WEB_HOST", "127.0.0.1")
    server = ThreadingHTTPServer((host, port), GigCaHandler)
    print(f"GigCa Data Explorer: http://{host}:{port}/web/")
    print("Live proxies enabled for TomTom map/POI/traffic/routing; rain is read from scheduled PostGIS snapshots.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping GigCa Data Explorer.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
