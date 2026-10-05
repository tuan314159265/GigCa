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

from engine.src.adapter import load_engine_input_from_file
from engine.src.advisor import consult_driver_advisor
from engine.src.engine import run_driver_engine
from engine.src.mock_data import (
    create_default_driver_context,
    create_default_driver_preferences,
    create_mock_engine_input,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Chạy thử GigCa Decision Engine với bối cảnh tài xế tùy chỉnh")
    parser.add_argument(
        "--rain",
        choices=["low", "medium", "high"],
        default="medium",
        help="Mức chịu mưa của tài xế (mặc định: medium)",
    )
    parser.add_argument(
        "--idle",
        type=int,
        default=25,
        help="Thời gian tài xế đã rảnh chờ cuốc (phút, mặc định: 25)",
    )
    parser.add_argument(
        "--horizon",
        type=int,
        default=180,
        help="Khung giờ lập kế hoạch tiếp theo (phút, mặc định: 180)",
    )
    parser.add_argument(
        "--snapshot",
        type=str,
        default=None,
        help="Đường dẫn file snapshot JSON cụ thể",
    )
    parser.add_argument(
        "--baseline",
        action="store_true",
        help="Chạy ở chế độ dữ liệu ban đầu (thiếu dữ liệu giá cước và cuốc xe)",
    )
    args = parser.parse_args()

    full_sim_path = ROOT / "data" / "fixtures" / "hcmc_full_simulated_snapshot.json"

    # 1. Khởi tạo Input
    if args.snapshot:
        snapshot_path = Path(args.snapshot)
        if not snapshot_path.exists():
            print(f"[LỖI] Không tìm thấy file snapshot tại: {snapshot_path}")
            return 1
        print(f"-> Đang nạp dữ liệu từ snapshot: {snapshot_path}")
        engine_input = load_engine_input_from_file(snapshot_path)
    elif args.baseline:
        print("-> Đang dùng bộ dữ liệu ban đầu (Baseline: thiếu dữ liệu giá cước/booking)")
        engine_input = create_mock_engine_input()
    elif full_sim_path.exists():
        print(f"-> Đang dùng bộ dữ liệu mô phỏng hoàn chỉnh cả 4 hướng (Full Simulation): {full_sim_path.name}")
        engine_input = load_engine_input_from_file(full_sim_path)
    else:
        print("-> Đang dùng bộ dữ liệu mô phỏng mặc định")
        engine_input = create_mock_engine_input()


    # 2. Khởi tạo ngữ cảnh và tùy chọn tài xế
    ctx = create_default_driver_context(
        lat=10.7769,
        lng=106.7009,
        idle_min=args.idle,
        horizon_min=args.horizon,
    )
    prefs = create_default_driver_preferences(rain_tolerance=args.rain)

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
