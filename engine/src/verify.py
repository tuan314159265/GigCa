"""Verification runner for Decision Engine.

Runs sample snapshot and variations, displaying results in an inspection table
demonstrating responsiveness to input changes without hardcoded lookups.
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


from engine.src.adapter import load_engine_input_from_file
from engine.src.advisor import consult_driver_advisor
from engine.src.engine import run_driver_engine
from engine.src.mock_data import (
    create_default_driver_context,
    create_default_driver_preferences,
    create_mock_engine_input,
)
from engine.src.types import DriverRecommendationOutput

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT_PATH = ROOT / "data" / "samples" / "engine_input" / "hcmc_demo_snapshot.json"
FULL_FIXTURE_PATH = ROOT / "data" / "fixtures" / "hcmc_full_simulated_snapshot.json"


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


def run_verification() -> int:
    """Run verification scenarios and print comparison table."""
    print("================================================================================")
    print("           GIGCA DRIVER DECISION ENGINE — VERIFICATION SUITE                    ")
    print("================================================================================")

    ctx = create_default_driver_context(horizon_min=180, idle_min=25)

    # 1. Baseline Run with Mock Data
    mock_input = create_mock_engine_input()
    prefs_med = create_default_driver_preferences(rain_tolerance="medium")
    out_baseline = run_driver_engine(mock_input, ctx, prefs_med)
    print_recommendation_summary(out_baseline, "Kịch bản 1: Baseline Mock Data (Rain Tolerance = MEDIUM)")

    # 2. Responsiveness: Rain Tolerance Comparison
    print_banner("Kịch bản 2: Kiểm tra phản ứng đầu vào — Mức chịu mưa LOW vs MEDIUM vs HIGH")
    for level in ["low", "medium", "high"]:
        p = create_default_driver_preferences(rain_tolerance=level)
        out = run_driver_engine(mock_input, ctx, p)
        safety_res = out.objectives["safety_comfort"]
        flags = safety_res.rain_flags or []
        exceeded_times = [f.window or f.valid_time for f in flags if f.exceeds_tolerance]
        signal = safety_res.weather_action_signal
        window = safety_res.safe_window_min
        print(
            f"Mức chịu mưa: {level.upper():<6} -> "
            f"Số giờ vượt: {len(exceeded_times)}/{len(flags)} "
            f"| Tín hiệu: {signal:<22} "
            f"| Cửa sổ an toàn: ~{window}m "
            f"({', '.join(exceeded_times) if exceeded_times else 'Khô ráo'})"
        )

    # 3. Snapshot Run from File (hcmc_demo_snapshot.json)
    if SNAPSHOT_PATH.exists():
        snapshot_input = load_engine_input_from_file(SNAPSHOT_PATH)
        out_snapshot = run_driver_engine(snapshot_input, ctx, prefs_med)
        print_recommendation_summary(out_snapshot, "Kịch bản 3: Snapshot thật data/samples/engine_input/hcmc_demo_snapshot.json")
    else:
        print(f"[NOTE] Snapshot file not found at {SNAPSHOT_PATH}")

    # 4. Responsiveness to the driver's position and idle time (full simulated snapshot)
    if FULL_FIXTURE_PATH.exists():
        full_input = load_engine_input_from_file(FULL_FIXTURE_PATH)
        print_banner("Kịch bản 4: Phản ứng với VỊ TRÍ và THỜI GIAN CHỜ của tài xế (fixture đầy đủ)")
        for name, (lat, lng) in {"Bến Thành": (10.7725, 106.698), "Hàng Xanh": (10.801, 106.711)}.items():
            c = create_default_driver_context(lat=lat, lng=lng, horizon_min=180, idle_min=25)
            o = run_driver_engine(full_input, c, prefs_med).objectives["max_trip_value"]
            names = " > ".join(f"{x.area_name.split(' - ')[0].replace('Khu vực ', '')} ({x.yield_vnd_per_hour:,.0f}đ/h)" for x in o.candidates)
            print(f"Tài xế ở {name:<10}: {names}  | loại: {len(o.excluded or [])}")
        for idle in (10, 50):
            c = create_default_driver_context(horizon_min=180, idle_min=idle)
            o = run_driver_engine(full_input, c, prefs_med)
            order = " > ".join(r["objective"] for r in o.direction_priority or [] if r["rankable"])
            print(f"Chờ {idle:>2} phút        : thứ tự xem xét = {order}")
    else:
        print(f"[NOTE] Full fixture not found at {FULL_FIXTURE_PATH}")

    # 5. v3: the driver's own trip log unlocks the earning lenses on REAL collected data (synthetic log, test only)
    real_path = ROOT / "data" / "processed" / "engine_input_snapshot.json"
    if real_path.exists():
        import random
        from datetime import datetime, timedelta

        from engine.src.adapter import load_engine_input_from_dict

        print_banner("Kịch bản 5 (v3): Dữ liệu thật + nhật ký chuyến mô phỏng của tài xế -> mô hình cá nhân")
        payload = json.loads(real_path.read_text(encoding="utf-8"))
        rng = random.Random(7)
        zones = [(10.7725, 106.6980, 78000, 22), (10.7830, 106.6850, 64000, 18), (10.8010, 106.6790, 91000, 31)]
        now = datetime(2026, 10, 6, 19, 35)
        log = []
        for day in range(12):
            cur = (now - timedelta(days=12 - day)).replace(hour=17, minute=30, second=0, microsecond=0)
            for i in range(6):
                la, lo, net, dur = rng.choice(zones)
                d_la, d_lo = rng.choice(zones)[:2]
                d = dur * rng.uniform(0.8, 1.2)
                log.append({"trip_id": f"v{day}_{i}", "started_at": cur.isoformat(), "pickup_lat": la, "pickup_lng": lo,
                            "net_vnd": net * rng.uniform(0.7, 1.3), "duration_min": d, "dropoff_lat": d_la, "dropoff_lng": d_lo})
                cur += timedelta(minutes=d + rng.randint(3, 15))
        for label, extra in (("không có nhật ký", {}), ("có nhật ký 72 chuyến", {"trip_log": log})):
            o = run_driver_engine(load_engine_input_from_dict({**payload, **extra}), ctx, prefs_med, explain=True)
            r1 = o.objectives["max_trip_value"]
            top = r1.candidates[0] if r1.candidates else None
            print(f"[{label}] Hướng 1: {r1.status}/{r1.confidence}"
                  + (f" | top ~{top.yield_vnd_per_hour:,}đ/giờ, khoảng {top.yield_low_vnd_per_hour:,}-{top.yield_high_vnd_per_hour:,} (n={top.evidence_n})" if top else ""))
            if o.tradeoff_matrix:
                for line in o.tradeoff_matrix["comparisons"]:
                    print(f"    ⇄ {line}")
            for line in (o.decision_boundaries or {}).get("summary", []):
                print(f"    ? {line}")
            for item in o.data_roadmap or []:
                if item.get("fastest_unlock"):
                    print(f"    ▸ [{item['objective']}] {item['fastest_unlock']}")

    print("\n✓ Hoàn thành kiểm tra Decision Engine.")
    return 0



if __name__ == "__main__":
    raise SystemExit(run_verification())
