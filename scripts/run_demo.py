#!/usr/bin/env python3
"""Interactive demo runner for the GigCa Decision Engine.

Allows passing custom driver contexts and preferences via CLI arguments.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import json

from data.engine_bridge import load_for_engine
from data.driver_log_import import attach_driver_log
from engine.src.advisor import consult_driver_advisor
from engine.src.engine import run_driver_engine
from engine.src.types import DriverContext, DriverPreferences

REAL_SNAPSHOT = ROOT / "data" / "samples" / "engine_input" / "hcmc_demo_snapshot.json"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Chạy GigCa Decision Engine trên dữ liệu THẬT (snapshot ETL + biểu cước công bố + dữ liệu tài xế nếu có)"
    )
    parser.add_argument("--rain", choices=["low", "medium", "high"], default="medium",
                        help="Mức chịu mưa của tài xế (mặc định: medium)")
    parser.add_argument("--idle", type=int, default=25, help="Thời gian tài xế đã rảnh chờ cuốc (phút, mặc định: 25)")
    parser.add_argument("--horizon", type=int, default=180, help="Khung giờ lập kế hoạch tiếp theo (phút, mặc định: 180)")
    parser.add_argument("--lat", type=float, default=10.7769, help="Vĩ độ tài xế")
    parser.add_argument("--lng", type=float, default=106.7009, help="Kinh độ tài xế")
    parser.add_argument("--snapshot", type=str, default=None,
                        help="Snapshot JSON theo contract Data (mặc định: snapshot ETL thật data/samples/engine_input/...)")
    parser.add_argument("--driver-log", type=str, default=None,
                        help="Nhật ký THẬT của tài xế do data/driver_log_import.py tạo (trip_log + wait_spells + hồ sơ)")
    parser.add_argument("--profile", type=str, default=None,
                        help="JSON hồ sơ tài xế (xăng, mục tiêu đ/giờ, biểu cước riêng nếu có) — ghi đè hồ sơ trong --driver-log")
    args = parser.parse_args()

    # 1. Khởi tạo Input: chỉ dữ liệu thật (không còn bộ mô phỏng)
    snapshot_path = Path(args.snapshot) if args.snapshot else REAL_SNAPSHOT
    if not snapshot_path.exists():
        print(f"[LỖI] Không tìm thấy file snapshot tại: {snapshot_path}")
        return 1
    print(f"-> Đang nạp snapshot: {snapshot_path}")
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    if args.driver_log:
        log = json.loads(Path(args.driver_log).read_text(encoding="utf-8"))
        payload = attach_driver_log(payload, log)
        prov = log.get("provenance") or {}
        print(f"-> Nhật ký tài xế {prov.get('driver_pseudonym')} ({prov.get('collected_via')}): "
              f"{len(payload['trip_log'])} chuyến, {len(payload['wait_spells'])} đợt chờ")
    else:
        print("-> Chưa có nhật ký tài xế: hai hướng kiếm tiền chỉ có bảng kịch bản theo biểu cước (Bậc 0)")
    if args.profile:
        payload["driver_profile"] = {**(payload.get("driver_profile") or {}),
                                     **{k: v for k, v in json.loads(Path(args.profile).read_text(encoding="utf-8")).items()
                                        if not k.startswith("_") and v is not None}}
    engine_input = load_for_engine(
        payload,
        trip_log=payload.get("trip_log"),
        wait_spells=payload.get("wait_spells"),
        driver_profile=payload.get("driver_profile"),
    )

    # 2. Khởi tạo ngữ cảnh và tùy chọn tài xế
    ctx = DriverContext(current_lat=args.lat, current_lng=args.lng, idle_duration_min=args.idle,
                        horizon_min=args.horizon, max_reposition_km=3.0)
    prefs = DriverPreferences(rain_tolerance_level=args.rain)

    # 3. Chạy Decision Engine
    output = run_driver_engine(engine_input, ctx, prefs)

    # 4. Hiển thị kết quả
    print("\n" + "=" * 80)
    print("                 KẾT QUẢ GỢI Ý QUYẾT ĐỊNH CHO TÀI XẾ")
    print("=" * 80)
    print(f"• Bối cảnh tài xế : Đã rảnh {ctx.idle_duration_min} phút | Horizon {ctx.horizon_min} phút | Mức chịu mưa: {args.rain.upper()}")
    print(f"• Thời điểm tạo   : {output.generated_at}")
    print("-" * 80)

    # Hiển thị 4 Kế hoạch Hành động Chiến lược Độc lập
    print("\n[BẢNG 4 KẾ HOẠCH HÀNH ĐỘNG ĐỘC LẬP DÀNH CHO TÀI XẾ]")
    print("(Tương tự như việc lập kế hoạch du lịch: Engine đưa ra các kế hoạch hành động hoàn chỉnh")
    print(" theo từng hướng chiến lược để tài xế chủ động lựa chọn phương án phù hợp nhất)\n")

    direction_labels = {
        "max_trip_value": "HƯỚNG 1: TỐI ĐA HÓA GIÁ TRỊ CUỐC (MAX TRIP VALUE)",
        "maintain_position": "HƯỚNG 2: BÁM TRỤ VÙNG LÕI & VÒNG QUAY NHANH (MAINTAIN POSITION)",
        "rest_spot": "HƯỚNG 3: NGHỈ NGƠI & PHỤC HỒI NĂNG LƯỢNG (REST & RECHARGE)",
        "safety_comfort": "HƯỚNG 4: PHÒNG VỆ THỜI TIẾT & AN TOÀN TAY LÁI (SAFETY & COMFORT)",
    }

    for key, label in direction_labels.items():
        res = output.objectives.get(key)
        if not res:
            continue

        status_badge = f"[{res.status.upper()}] (Độ tin cậy: {res.confidence.upper()})"
        print("=" * 80)
        print(f" ► {label} {status_badge}")
        print("=" * 80)

        if res.status == "insufficient_data" or not res.plan:
            print(f"  • Trạng thái       : Chưa đủ dữ liệu để lập kế hoạch hoàn chỉnh.")
            print(f"  • Lý do thiếu      : {res.reason_for_insufficiency}")
            if res.context_only:
                print(f"  • Dữ liệu ngữ cảnh : Đã ghi nhận {len(res.context_only)} mẫu bối cảnh (chỉ đọc, không bịa đặt).")
            print()
            continue

        plan = res.plan
        print(f"  ★ Tên kế hoạch     : {plan.plan_title if hasattr(plan, 'plan_title') else plan.direction_title}")
        print(f"  ★ Trọng tâm        : {plan.objective_focus}")
        print(f"  ★ Địa điểm mục tiêu: {plan.target_location}")
        print(f"  ★ Tóm tắt chiến lược: {plan.summary}")
        print(f"\n  ► TRÌNH TỰ CÁC BƯỚC HÀNH ĐỘNG CỤ THỂ:")
        for step in plan.steps:
            print(f"     [Bước {step.step_number}] ({step.time_window}): {step.action}")
            print(f"              -> Chi tiết : {step.instruction}")
            print(f"              -> Kỳ vọng  : {step.expected_outcome}")

        print(f"\n  ► CHỈ SỐ DỰ PHÓNG CHÍNH:")
        for mk, mv in plan.key_metrics.items():
            if isinstance(mv, float) and "vnd" in mk:
                print(f"     • {mk:<24}: {mv:,.0f} đ")
            else:
                print(f"     • {mk:<24}: {mv}")

        print(f"\n  ► ĐÁNH ĐỔI & RỦI RO CẦN BIẾT:")
        print(f"     • {plan.trade_offs}")
        print(f"  ► PHƯƠNG ÁN DỰ PHÒNG:")
        print(f"     • {plan.contingency_fallback}")
        if res.caveat:
            print(f"  ► LƯU Ý DỮ LIỆU: {res.caveat}")
        print()

    # Bảng kịch bản theo biểu cước (Bậc 0 — có ngay, không cần nhật ký)
    wi = output.what_if
    if wi:
        print("=" * 80)
        print("[BẢNG KỊCH BẢN THEO BIỂU CƯỚC — KHÔNG PHẢI DỰ ĐOÁN]")
        print("=" * 80)
        for note in wi["notes"]:
            print(f"  • {note}")
        print(f"  {'km':>4} {'chờ':>5} {'cước khách':>11} {'bạn nhận':>9} {'sau xăng':>9} {'đ/giờ':>9}"
              + (f" {'cần nhận':>9}" if wi.get("target_vnd_per_hour") else ""))
        for r in wi["rows"]:
            line = (f"  {r['trip_km']:>4g} {r['wait_min']:>4}' {r['customer_fare_vnd']:>11,} {r['net_before_fuel_vnd']:>9,} "
                    f"{r['net_after_fuel_vnd']:>9,} {r['yield_vnd_per_hour']:>9,}")
            if "min_fare_for_target_vnd" in r:
                line += f" {r['min_fare_for_target_vnd']:>9,} {'✓' if r['tariff_meets_target'] else '✗'}"
            print(line)
        for b in wi.get("break_even_trip_km") or []:
            km = f"≥ {b['min_trip_km']:g} km" if b["min_trip_km"] is not None else "không cuốc nào ≤ 40 km đạt"
            print(f"  ▸ Chờ {b['wait_min']} phút: cuốc cần {km} để đạt mục tiêu")
        print()

    # Cố vấn chiến lược: So sánh & Phân tích 4 kế hoạch
    advisor = consult_driver_advisor(output)
    print("=" * 80)
    print("[PHÂN TÍCH & ĐỐI CHIẾU TỪ CỐ VẤN CHIẾN LƯỢC]")
    print("=" * 80)
    print(f"• Tình thế bối cảnh : {advisor['situation_assessment']}")
    print(f"• Hướng dẫn lựa chọn: {advisor['decision_guide']}")
    print(f"• Phương án dự phòng: {advisor['contingency_plan']}")

    print("\n" + "=" * 80)
    print(f"Lời nhắc bất biến: \"{output.final_note}\"")
    print("=" * 80 + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
