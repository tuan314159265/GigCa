"""Import a REAL driver's own log (CSV) into the engine runtime format, row by row, with a rejection report.

Why this exists: market data (fares per area, booking rates, waits per area) has no public, licensed source, and the team
must not present invented numbers. The two earning lenses therefore run on data a consenting pilot driver records about
their OWN work: completed trips (`trip_log`) and waits for a request (`wait_spells`). This module turns the CSV files the
driver (or the team member interviewing them) fills in into JSON the engine reads, and says exactly which rows were
rejected and why. It never fills in a missing required value.

Usage (from the repository root):

    python -m data.driver_log_import \
        --trips data/raw/driver_logs/d01_trips.csv \
        --waits data/raw/driver_logs/d01_waits.csv \
        --profile data/raw/driver_logs/d01_profile.json \
        --driver-pseudonym D01 --consent-ref "Phiếu đồng ý D01, ký 2026-10-12" \
        --collected-via "Google Form + ảnh chụp lịch sử thu nhập" \
        --out data/raw/driver_logs/d01_engine_log.json

data/raw/ is git-ignored on purpose: a personal trip history must not be committed (RULES.md §2).
Templates with the expected columns are in data/driver_input/.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

TRIP_REQUIRED = ("trip_id", "started_at", "pickup_lat", "pickup_lng", "net_vnd", "duration_min")
TRIP_OPTIONAL = ("dropoff_lat", "dropoff_lng", "distance_km")
WAIT_REQUIRED = ("spell_id", "start", "end", "lat", "lng", "ended_by")
WAIT_OPTIONAL = ("rain_mm",)
WAIT_END = ("trip", "offline", "moved")
PROFILE_FIELDS = (
    "fare_base_vnd", "fare_base_km", "fare_per_km_vnd", "fare_per_min_vnd", "driver_share",
    "fuel_l_per_100km", "fuel_price_vnd_per_l", "target_vnd_per_hour",
)
LOCAL_TZ = timezone(timedelta(hours=7))
_THOUSANDS = re.compile(r"^\d{1,3}([.,]\d{3})+$")


def _blank(v: Any) -> bool:
    return v is None or (isinstance(v, str) and v.strip() == "")


def _number(v: Any, money: bool = False) -> float:
    """Parse a CSV cell. Money cells accept '45.000', '45,000', '45000đ'. Raises ValueError on anything else."""
    s = str(v).strip()
    if money:
        s = re.sub(r"\s*(đ|vnd|đồng|dong)$", "", s, flags=re.IGNORECASE).replace(" ", "")
        if _THOUSANDS.match(s):
            s = re.sub(r"[.,]", "", s)
    else:
        s = s.replace(",", ".") if s.count(",") == 1 and "." not in s else s
    x = float(s)
    if x != x or x in (float("inf"), float("-inf")):
        raise ValueError("not finite")
    return x


def _time(v: Any) -> str:
    """ISO 8601. A value without an offset is read as local time (UTC+7) and written WITH the offset, so the engine and
    a reader see the same instant. 'YYYY-MM-DD HH:MM' is accepted. Raises ValueError when unreadable."""
    s = str(v).strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(s.replace(" ", "T", 1) if "T" not in s else s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=LOCAL_TZ)
    return dt.isoformat()


def _lat_lng(lat: Any, lng: Any) -> tuple[float, float]:
    la, lo = _number(lat), _number(lng)
    if not (-90 <= la <= 90 and -180 <= lo <= 180):
        raise ValueError("toạ độ ngoài phạm vi")
    return la, lo


def validate_trips(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Returns (accepted trips, rejected rows with reason, warnings about optional fields that were dropped)."""
    ok: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    seen: set[str] = set()
    for i, r in enumerate(rows, start=2):  # row 1 is the header
        missing = [f for f in TRIP_REQUIRED if _blank(r.get(f))]
        if missing:
            rejected.append({"row": i, "reason": f"thiếu trường bắt buộc: {', '.join(missing)}"})
            continue
        tid = str(r["trip_id"]).strip()
        if tid in seen:
            rejected.append({"row": i, "reason": f"trip_id trùng: {tid}"})
            continue
        try:
            started = _time(r["started_at"])
            lat, lng = _lat_lng(r["pickup_lat"], r["pickup_lng"])
            net = _number(r["net_vnd"], money=True)
            dur = _number(r["duration_min"])
        except ValueError as exc:
            rejected.append({"row": i, "reason": f"giá trị không đọc được ({exc})"})
            continue
        if net < 0:
            rejected.append({"row": i, "reason": "net_vnd âm"})
            continue
        if dur <= 0:
            rejected.append({"row": i, "reason": "duration_min phải > 0"})
            continue
        trip: dict[str, Any] = {"trip_id": tid, "started_at": started, "pickup_lat": lat, "pickup_lng": lng,
                                "net_vnd": net, "duration_min": dur}
        if not _blank(r.get("dropoff_lat")) or not _blank(r.get("dropoff_lng")):
            try:
                trip["dropoff_lat"], trip["dropoff_lng"] = _lat_lng(r.get("dropoff_lat"), r.get("dropoff_lng"))
            except (ValueError, TypeError):
                warnings.append({"row": i, "field": "dropoff_lat/lng", "reason": "không hợp lệ — bỏ điểm trả, giữ chuyến"})
        if not _blank(r.get("distance_km")):
            try:
                d = _number(r["distance_km"])
                if d <= 0:
                    raise ValueError("<= 0")
                trip["distance_km"] = d
            except ValueError:
                warnings.append({"row": i, "field": "distance_km", "reason": "không hợp lệ — bỏ cự ly, giữ chuyến"})
        if "distance_km" not in trip and "dropoff_lat" not in trip:
            warnings.append({"row": i, "field": "distance_km",
                             "reason": "không có cự ly và điểm trả — chuyến không dùng được để học cự ly/tốc độ"})
        seen.add(tid)
        ok.append(trip)
    return ok, rejected, warnings


def validate_waits(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    ok: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    seen: set[str] = set()
    for i, r in enumerate(rows, start=2):
        missing = [f for f in WAIT_REQUIRED if _blank(r.get(f))]
        if missing:
            rejected.append({"row": i, "reason": f"thiếu trường bắt buộc: {', '.join(missing)}"})
            continue
        sid = str(r["spell_id"]).strip()
        if sid in seen:
            rejected.append({"row": i, "reason": f"spell_id trùng: {sid}"})
            continue
        ended = str(r["ended_by"]).strip().lower()
        if ended not in WAIT_END:
            rejected.append({"row": i, "reason": f"ended_by phải là một trong {', '.join(WAIT_END)}"})
            continue
        try:
            start, end = _time(r["start"]), _time(r["end"])
            lat, lng = _lat_lng(r["lat"], r["lng"])
        except ValueError as exc:
            rejected.append({"row": i, "reason": f"giá trị không đọc được ({exc})"})
            continue
        if datetime.fromisoformat(end) < datetime.fromisoformat(start):
            rejected.append({"row": i, "reason": "end trước start"})
            continue
        spell: dict[str, Any] = {"spell_id": sid, "start": start, "end": end, "lat": lat, "lng": lng, "ended_by": ended}
        if not _blank(r.get("rain_mm")):
            try:
                rain = _number(r["rain_mm"])
                if rain < 0:
                    raise ValueError("< 0")
                spell["rain_mm"] = rain
            except ValueError:
                warnings.append({"row": i, "field": "rain_mm", "reason": "không hợp lệ — bỏ, giữ đợt chờ"})
        seen.add(sid)
        ok.append(spell)
    return ok, rejected, warnings


def validate_profile(raw: dict[str, Any]) -> tuple[dict[str, float], list[str]]:
    """Keep known numeric fields; report unknown or invalid ones. Tariff fields left out fall back (in the engine) to the
    PUBLISHED tariff in config/engine_config.json — labelled as such in every output."""
    out: dict[str, float] = {}
    problems: list[str] = []
    for k, v in raw.items():
        if k.startswith("_"):
            continue
        if k not in PROFILE_FIELDS:
            problems.append(f"trường không hỗ trợ: {k}")
            continue
        if v is None:
            continue
        try:
            x = _number(v, money=k.endswith("_vnd") or k.endswith("_vnd_per_l") or k.endswith("_per_hour"))
        except (ValueError, TypeError):
            problems.append(f"{k}: không phải số")
            continue
        if x < 0 or (k == "driver_share" and not 0 < x <= 1):
            problems.append(f"{k}: ngoài miền hợp lệ" + (" (driver_share là phân số, vd 0.75)" if k == "driver_share" else ""))
            continue
        out[k] = x
    return out, problems


def _read_csv(path: Path) -> list[dict[str, Any]]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def build_driver_log(
    trips_rows: list[dict[str, Any]],
    wait_rows: list[dict[str, Any]],
    profile: dict[str, Any] | None,
    *,
    driver_pseudonym: str,
    consent_reference: str,
    collected_via: str,
) -> dict[str, Any]:
    trips, t_rej, t_warn = validate_trips(trips_rows)
    waits, w_rej, w_warn = validate_waits(wait_rows)
    prof, p_problems = validate_profile(profile or {})
    return {
        "schema": "gigca_driver_log_v1",
        "provenance": {
            "kind": "real_driver_log",  # dữ liệu THẬT của một tài xế tham gia thử nghiệm, có đồng ý
            "driver_pseudonym": driver_pseudonym,
            "consent_reference": consent_reference,
            "collected_via": collected_via,
            "imported_at": datetime.now(LOCAL_TZ).isoformat(timespec="seconds"),
        },
        "driver_profile": prof or None,
        "trip_log": trips,
        "wait_spells": waits,
        "import_report": {
            "trips": {"rows": len(trips_rows), "accepted": len(trips), "rejected": t_rej, "warnings": t_warn},
            "wait_spells": {"rows": len(wait_rows), "accepted": len(waits), "rejected": w_rej, "warnings": w_warn},
            "profile_problems": p_problems,
        },
    }


def attach_driver_log(snapshot: dict[str, Any], driver_log: dict[str, Any]) -> dict[str, Any]:
    """Merge a driver log produced by `build_driver_log` into a Data-contract snapshot for the engine (runtime only)."""
    if driver_log.get("schema") != "gigca_driver_log_v1":
        raise ValueError("driver log không đúng schema gigca_driver_log_v1")
    if (driver_log.get("provenance") or {}).get("kind") != "real_driver_log":
        raise ValueError("chỉ nạp nhật ký thật của tài xế (provenance.kind = real_driver_log)")
    out = dict(snapshot)
    out["trip_log"] = list(driver_log.get("trip_log") or [])
    out["wait_spells"] = list(driver_log.get("wait_spells") or [])
    if driver_log.get("driver_profile"):
        out["driver_profile"] = dict(driver_log["driver_profile"])
    out["driver_log_provenance"] = driver_log.get("provenance")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Nhập nhật ký THẬT của tài xế (CSV) sang định dạng engine, kèm báo cáo dòng bị loại")
    ap.add_argument("--trips", type=Path, required=True, help="CSV nhật ký chuyến (xem data/driver_input/trip_log_template.csv)")
    ap.add_argument("--waits", type=Path, help="CSV đợt chờ (xem data/driver_input/wait_spells_template.csv)")
    ap.add_argument("--profile", type=Path, help="JSON hồ sơ tài xế (xem data/driver_input/driver_profile_template.json)")
    ap.add_argument("--driver-pseudonym", required=True, help="Bí danh, KHÔNG dùng tên/SĐT thật (vd D01)")
    ap.add_argument("--consent-ref", required=True, help="Tham chiếu phiếu đồng ý của tài xế")
    ap.add_argument("--collected-via", required=True, help="Cách thu thập (vd 'Google Form + ảnh chụp lịch sử thu nhập')")
    ap.add_argument("--out", type=Path, required=True, help="File JSON đầu ra (nên đặt trong data/raw/, đã git-ignore)")
    a = ap.parse_args(argv)

    profile = json.loads(a.profile.read_text(encoding="utf-8")) if a.profile else None
    log = build_driver_log(
        _read_csv(a.trips), _read_csv(a.waits) if a.waits else [], profile,
        driver_pseudonym=a.driver_pseudonym, consent_reference=a.consent_ref, collected_via=a.collected_via,
    )
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    rep = log["import_report"]
    print(f"Chuyến: nhận {rep['trips']['accepted']}/{rep['trips']['rows']}, loại {len(rep['trips']['rejected'])}, "
          f"cảnh báo {len(rep['trips']['warnings'])}")
    print(f"Đợt chờ: nhận {rep['wait_spells']['accepted']}/{rep['wait_spells']['rows']}, loại {len(rep['wait_spells']['rejected'])}")
    for x in rep["trips"]["rejected"] + rep["wait_spells"]["rejected"]:
        print(f"  ✗ dòng {x['row']}: {x['reason']}")
    for p in rep["profile_problems"]:
        print(f"  ⚠ hồ sơ: {p}")
    print(f"-> {a.out}")
    if "data/raw" not in a.out.as_posix():
        print("  ⚠ File nằm ngoài data/raw/ — đừng commit nhật ký cá nhân lên Git.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
