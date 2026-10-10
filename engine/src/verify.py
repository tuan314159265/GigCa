"""Verification runner for the Decision Engine — on REAL inputs only.

1. Tariff arithmetic: the published tariff in config reproduces hand-computed fares (no data needed).
2. The real ETL snapshot (Open-Meteo / OSM / OSRM) with the driver's inputs: what the engine can and cannot say.
3. Every real driver log imported with data/driver_log_import.py into data/raw/driver_logs/*.json (if any).
No simulated or mock data is loaded here; unit-test inputs live under engine/tests/ and are used only by the tests.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

if sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
if sys.stderr.encoding.lower() != "utf-8":
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


from engine.src.advisor import consult_driver_advisor
from engine.src.engine import run_driver_engine
from engine.src.personal_model import resolve_economics
from engine.src.types import DriverContext, DriverPreferences, DriverRecommendationOutput

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT_PATH = ROOT / "data" / "samples" / "engine_input" / "hcmc_demo_snapshot.json"
DRIVER_LOG_DIR = ROOT / "data" / "raw" / "driver_logs"


def print_banner(title: str) -> None:
    print("\n" + "=" * 80)
    print(f" {title.upper()}")
    print("=" * 80)


def print_recommendation_summary(output: DriverRecommendationOutput, title: str) -> None:
    print_banner(title)
    print(f"Generated at: {output.generated_at}")
    print("-" * 80)
    print(f"{'OBJECTIVE':<20} | {'STATUS':<18} | {'CONFIDENCE':<10} | {'DETAILS'}")
    print("-" * 80)

    for key, res in output.objectives.items():
        details = ""
        if res.status == "insufficient_data":
            details = f"[Thiếu dữ liệu] {res.reason_for_insufficiency or ''}"
        elif key == "rest_spot":
            count = len(res.candidates)
            cand_names = ", ".join(f"{c.name} [{c.suitability_tier}]" for c in res.candidates[:2])
            details = f"{count} ứng viên ({cand_names}{'...' if count > 2 else ''})"
        elif key in ("max_trip_value", "maintain_position"):
            top = ", ".join(f"#{c.rank} {c.area_name}" for c in res.candidates[:3])
            details = f"{len(res.candidates)} khu vực xếp hạng ({top}), {len(res.excluded or [])} bị loại"
        elif key == "safety_comfort":
            flags = res.rain_flags or []
            exceeded = sum(1 for f in flags if f.exceeds_tolerance)
            signal_txt = f"Tín hiệu: {res.weather_action_signal}"
            window_txt = f"Cửa sổ an toàn: ~{res.safe_window_min} phút" if res.safe_window_min is not None else ""
            details = f"{len(flags)} giờ | {exceeded} giờ vượt | {signal_txt} | {window_txt}"
            if res.traffic_note:
                details += f" | {res.traffic_note}"

        print(f"{key:<20} | {res.status:<18} | {res.confidence:<10} | {details}")

    print("-" * 80)
    for key, res in output.objectives.items():
        for e in res.excluded or []:
            print(f"  ✗ [{key}] loại {e['name']}: {e['reason']}")
        if res.robustness and res.robustness.get("runner_up"):
            rb = res.robustness
            print(f"  ≈ [{key}] độ vững: hạng 1 giữ {rb['top1_share']*100:.0f}% kịch bản, chênh hạng 2 {rb['margin_pct']}% "
                  f"({'ổn định' if rb['stable'] else 'NHẠY VỚI GIẢ ĐỊNH'}{', sát nhau' if rb['contested'] else ''})")
    if output.direction_priority:
        print("\nTHỨ TỰ NÊN XEM TRƯỚC (quy tắc rõ ràng, KHÔNG phải điểm tổng):")
        for r in output.direction_priority:
            rank = r["rank"] if r["rankable"] else "-"
            print(f"  {rank}. {r['objective']:<18} — {r['reason']}")
    for w in output.data_quality_warnings:
        print(f"  ⚠ Chất lượng dữ liệu: {w}")
    print("-" * 80)
    print("4 KẾ HOẠCH HÀNH ĐỘNG ĐỘC LẬP TƯƠNG ỨNG 4 HƯỚNG MỤC TIÊU:")
    for key, res in output.objectives.items():
        if res.plan:
            print(f"\n  ★ [{key.upper()}]: {res.plan.direction_title}")
            print(f"     • Tóm tắt  : {res.plan.summary}")
            print(f"     • Mục tiêu : {res.plan.target_location}")
            print(f"     • Các bước : {len(res.plan.steps)} bước hành động chi tiết")
            print(f"     • Đánh đổi : {res.plan.trade_offs}")
        else:
            print(f"\n  ► [{key.upper()}]: Chưa đủ dữ liệu ({res.reason_for_insufficiency})")

    # Advisor Reasoning
    advisor = consult_driver_advisor(output)
    print(f"\n[CỐ VẤN CHIẾN LƯỢC — PHÂN TÍCH LẬP LUẬN]")
    print(f"  • Đánh giá tình thế: {advisor['situation_assessment']}")
    print(f"  • Hướng dẫn tự chọn: {advisor['decision_guide']}")
    print(f"  • Kế hoạch dự phòng: {advisor['contingency_plan']}")
    print(f"  • Chế độ cố vấn: {advisor['advisor_mode']}")

    print("-" * 80)
    print("Giả định áp dụng:")
    for a in output.assumptions_used:
        print(f"  • {a}")
    print(f"\nLời nhắc cuối: \"{output.final_note}\"")


def _tariff_selfcheck() -> bool:
    """Hand-computed fares for the published tariff (12.500đ/2 km đầu, 4.300đ/km, 350đ/phút sau 2 km, 75%)."""
    econ = resolve_economics(None, [])
    if econ is None:
        print("[LỖI] Cấu hình 'tariff' trống.")
        return False
    cases = [  # (km, moving minutes after the first k0 km, expected customer fare)
        (1.5, 0.0, econ.fare_base_vnd),
        (econ.fare_base_km, 0.0, econ.fare_base_vnd),
        (5.0, 9.0, econ.fare_base_vnd + econ.fare_per_km_vnd * (5.0 - econ.fare_base_km) + econ.fare_per_min_vnd * 9.0),
    ]
    ok = True
    for km, mins, expected in cases:
        got = econ.gross_fare_vnd(km, mins)
        mark = "✓" if abs(got - expected) < 1e-6 else "✗"
        ok &= mark == "✓"
        print(f"  {mark} {km:g} km, {mins:g} phút tính phí -> cước khách {got:,.0f}đ, tài xế nhận "
              f"{got * econ.driver_share:,.0f}đ ({econ.driver_share * 100:.0f}%)")
    return ok


def run_verification() -> int:
    """Run the checks on real inputs and print what the engine concludes."""
    print("================================================================================")
    print("           GIGCA DRIVER DECISION ENGINE — VERIFICATION (DỮ LIỆU THẬT)          ")
    print("================================================================================")
    print_banner("1. Biểu cước công bố — kiểm tra số học")
    if not _tariff_selfcheck():
        return 1

    if not SNAPSHOT_PATH.exists():
        print(f"[NOTE] Không thấy snapshot thật tại {SNAPSHOT_PATH}")
        return 0
    payload = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    ctx = DriverContext(current_lat=10.7769, current_lng=106.7009, idle_duration_min=25, horizon_min=180)
    prefs = DriverPreferences(rain_tolerance_level="medium")
    from data.driver_log_import import attach_driver_log  # local imports: the engine itself does not depend on data/
    from data.engine_bridge import load_for_engine

    def _load(p: dict):
        return load_for_engine(p, trip_log=p.get("trip_log"), wait_spells=p.get("wait_spells"),
                               driver_profile=p.get("driver_profile"))

    out = run_driver_engine(_load(payload), ctx, prefs)
    print_recommendation_summary(out, "2. Snapshot ETL thật (Open-Meteo / OSM / OSRM), chưa có nhật ký tài xế")
    if out.what_if:
        print("  Bảng kịch bản (rút gọn):")
        for r in out.what_if["rows"]:
            print(f"    {r['trip_km']:g} km, chờ {r['wait_min']}' -> khách trả {r['customer_fare_vnd']:,}đ, "
                  f"bạn nhận {r['net_before_fuel_vnd']:,}đ, ~{r['yield_vnd_per_hour']:,}đ/giờ sau xăng")

    logs = sorted(DRIVER_LOG_DIR.glob("*.json")) if DRIVER_LOG_DIR.exists() else []
    if not logs:
        print("\n[NOTE] Chưa có nhật ký thật trong data/raw/driver_logs/ — xem data/driver_input/README.md để thu thập.")
    for path in logs:
        log = json.loads(path.read_text(encoding="utf-8"))
        try:
            p = attach_driver_log(payload, log)
        except ValueError as exc:
            print(f"[BỎ QUA] {path.name}: {exc}")
            continue
        o = run_driver_engine(_load(p), ctx, prefs, explain=True)
        prov = log.get("provenance") or {}
        print_recommendation_summary(o, f"3. Nhật ký thật {prov.get('driver_pseudonym', path.stem)} ({len(p['trip_log'])} chuyến)")
        for item in o.data_roadmap or []:
            if item.get("fastest_unlock"):
                print(f"    ▸ [{item['objective']}] {item['fastest_unlock']}")

    print("\n✓ Hoàn thành kiểm tra Decision Engine.")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_verification())
