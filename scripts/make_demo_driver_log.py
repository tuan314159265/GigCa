"""Regenerate the demo fixture's DRIVER-OWNED data: tariff profile, trip log and wait spells.

Why this exists: market-side fields (gross/net fare per area, demand_index, favorable_dropoff_pct, avg_next_wait_min…)
are defined by the ride platform and cannot be verified by the driver, so the engine no longer reads them. The
fixture instead carries what a single driver can verify: their own tariff, their own trips and their own waits.

Everything produced here is SYNTHETIC and labelled demo. It is generated deterministically (fixed seed) so the fixture
can be reproduced and reviewed; no real driver data is involved.

Usage (from the repository root):  python scripts/make_demo_driver_log.py
The script is idempotent: it strips any leftover market fields from `areas`, then rewrites the driver-owned sections.
"""

from __future__ import annotations

import json
import math
import random
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "data" / "fixtures" / "hcmc_full_simulated_snapshot.json"
SEED = 20260927
NOW = datetime(2026, 9, 27, 14, 0)  # == generated_at of the fixture, local time (UTC+7)
TZ = "+07:00"

# Fictional tariff of the simulated driver (VND). The engine must be able to RECOVER it from the log.
PROFILE = {
    "fare_base_vnd": 12000,
    "fare_per_km_vnd": 4800,
    "fuel_l_per_100km": 2.2,
    "fuel_price_vnd_per_l": 24000,
    "target_vnd_per_hour": 90000,
}
# zone: (lat, lng, mean trip km, mean trip speed km/h, mean wait min, pick weight)
ZONES = {
    "ben_thanh": (10.7725, 106.6980, 4.5, 20.0, 6.0, 0.34),
    "tan_dinh": (10.7890, 106.6910, 3.5, 19.0, 9.0, 0.22),
    "vo_thi_sau": (10.7830, 106.6960, 3.0, 18.0, 10.0, 0.22),
    "hang_xanh": (10.8010, 106.7110, 8.0, 24.0, 18.0, 0.22),
}
CELL_M = 600.0  # must equal personal_model.zone_cell_m: centres are snapped to the middle of their grid cell
DAYS, TRIPS_PER_DAY = 12, 6
PATIENCE_MIN = 20.0  # the simulated driver relocates after waiting this long (-> a "moved" spell, censored)
NOISE_VND = 2500.0
JITTER_DEG = 0.0007  # ~80 m, stays inside one 600 m zone cell


def _snap_centres() -> dict[str, tuple[float, float]]:
    """Move each zone centre to the middle of the grid cell the engine will put it in, so a cluster never straddles
    two cells (the jitter is ~80 m, the cell 600 m)."""
    m_per_deg = 111_320.0
    lat_ref = sum(z[0] for z in ZONES.values()) / len(ZONES)
    dlat = CELL_M / m_per_deg
    dlng = CELL_M / (m_per_deg * math.cos(math.radians(lat_ref)))
    return {
        n: ((math.floor(z[0] / dlat) + 0.5) * dlat, (math.floor(z[1] / dlng) + 0.5) * dlng) for n, z in ZONES.items()
    }


CENTRES = _snap_centres()


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S") + TZ


def _pick(rng: random.Random, exclude: str | None = None) -> str:
    names = [n for n in sorted(ZONES) if n != exclude]
    return rng.choices(names, weights=[ZONES[n][5] for n in names])[0]


def _near(rng: random.Random, zone: str) -> tuple[float, float]:
    lat, lng = CENTRES[zone]
    return round(lat + rng.uniform(-JITTER_DEG, JITTER_DEG), 6), round(lng + rng.uniform(-JITTER_DEG, JITTER_DEG), 6)


def generate() -> tuple[list[dict], list[dict]]:
    rng = random.Random(SEED)
    trips: list[dict] = []
    spells: list[dict] = []
    tid = sid = 0
    for day in range(DAYS, 0, -1):
        clock = (NOW - timedelta(days=day)).replace(hour=12, minute=40, second=0, microsecond=0)
        zone = _pick(rng)
        for _ in range(TRIPS_PER_DAY):
            # --- wait in `zone`; if it outlasts the driver's patience, a censored "moved" spell, then try elsewhere ---
            while True:
                wait = rng.expovariate(1.0 / ZONES[zone][4])
                lat, lng = _near(rng, zone)
                sid += 1
                if wait > PATIENCE_MIN:
                    spells.append({"spell_id": f"w{sid:03d}", "start": _iso(clock), "end": _iso(clock + timedelta(minutes=PATIENCE_MIN)),
                                   "lat": lat, "lng": lng, "ended_by": "moved"})
                    clock += timedelta(minutes=PATIENCE_MIN)
                    zone = _pick(rng, exclude=zone)
                    continue
                spells.append({"spell_id": f"w{sid:03d}", "start": _iso(clock), "end": _iso(clock + timedelta(minutes=wait)),
                               "lat": lat, "lng": lng, "ended_by": "trip"})
                clock += timedelta(minutes=wait)
                break
            # --- the trip that ended the wait ---
            _, _, mean_km, speed, _, _ = ZONES[zone]
            km = max(0.8, rng.lognormvariate(math.log(mean_km), 0.35))
            net = PROFILE["fare_base_vnd"] + PROFILE["fare_per_km_vnd"] * km + rng.gauss(0.0, NOISE_VND)
            dur = km / max(8.0, rng.gauss(speed, 2.0)) * 60.0
            drop_zone = _pick(rng, exclude=zone)  # where the driver goes to wait next
            p_lat, p_lng = lat, lng
            bearing = rng.uniform(0.0, 2.0 * math.pi)
            straight_km = km / 1.3  # the reported distance is road distance; the dropoff is placed consistently with it
            d_lat = round(p_lat + straight_km * math.cos(bearing) / 111.32, 6)
            d_lng = round(p_lng + straight_km * math.sin(bearing) / (111.32 * math.cos(math.radians(p_lat))), 6)
            tid += 1
            trip = {
                "trip_id": f"t{tid:03d}", "started_at": _iso(clock),
                "pickup_lat": p_lat, "pickup_lng": p_lng,
                "net_vnd": round(max(net, 8000.0)), "duration_min": round(dur, 1),
                "dropoff_lat": d_lat, "dropoff_lng": d_lng,
            }
            if tid % 10 != 0:  # every 10th trip has no distance: the engine must estimate it from the coordinates and say so
                trip["distance_km"] = round(km, 2)
            trips.append(trip)
            clock += timedelta(minutes=dur)
            zone = drop_zone
        # end of the shift: the driver waits a while, then goes offline (censored)
        sid += 1
        lat, lng = _near(rng, zone)
        spells.append({"spell_id": f"w{sid:03d}", "start": _iso(clock), "end": _iso(clock + timedelta(minutes=rng.uniform(25, 55))),
                       "lat": lat, "lng": lng, "ended_by": "offline"})
    return trips, spells


def _records(items: list[dict], indent: str) -> str:
    return "[\n" + ",\n".join(indent + json.dumps(i, ensure_ascii=False, separators=(", ", ": ")) for i in items) + "\n  ]"


def main() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))

    # 1) strip every platform-defined field from areas (idempotent)
    for a in payload["areas"]:
        a.pop("trip_value", None)
        a.pop("destination_distribution", None)

    # 2) honest data_status / readiness: no market source exists
    reasons = {
        "trip_value": "Không có nguồn cước thị trường kiểm chứng được; thu nhập theo vùng học từ nhật ký chuyến và biểu cước của chính tài xế (mô phỏng).",
        "booking_and_destinations": "Không có nguồn booking/điểm đến thị trường kiểm chứng được; thời gian chờ học từ các đợt chờ của chính tài xế (mô phỏng).",
        "vehicle_density": "Không có feed mật độ xe được cấp phép.",
    }
    for item in payload["data_status"]:
        if item["dataset"] in reasons:
            item["status"] = "not_integrated" if item["dataset"] != "vehicle_density" else "missing"
            item["reason"] = reasons[item["dataset"]]
    for item in payload["objective_readiness"]:
        if item["objective"] in ("max_trip_value", "maintain_position"):
            item["status"] = "insufficient_data"
            item["blocking_datasets"] = ["trip_value" if item["objective"] == "max_trip_value" else "booking_and_destinations"]
            item["reason"] = "Không có dữ liệu thị trường; hướng này chỉ chạy được từ dữ liệu của chính tài xế (biểu cước, nhật ký chuyến, đợt chờ)."
    payload["simulation_label"] = (
        "Bộ dữ liệu MÔ PHỎNG: thời tiết/POI/giao thông mô phỏng + biểu cước, nhật ký chuyến và đợt chờ của MỘT tài xế giả lập "
        "(sinh tất định bởi scripts/make_demo_driver_log.py). Không chứa dữ liệu thị trường của sàn."
    )

    # 3) driver-owned sections
    trips, spells = generate()
    payload["driver_profile"] = PROFILE
    payload["trip_log"] = trips
    payload["wait_spells"] = spells

    # compact, one record per line so the fixture stays small and diff-able
    head = {k: v for k, v in payload.items() if k not in ("trip_log", "wait_spells")}
    text = json.dumps(head, ensure_ascii=False, indent=2)
    extra = ',\n  "trip_log": ' + _records(trips, "    ") + ',\n  "wait_spells": ' + _records(spells, "    ") + "\n}\n"
    FIXTURE.write_text(text[:-2].rstrip() + extra, encoding="utf-8")
    print(f"wrote {FIXTURE.relative_to(ROOT)}: {len(trips)} trips, {len(spells)} wait spells")


if __name__ == "__main__":
    main()
