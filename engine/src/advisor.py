"""Driver Strategic Advisor — AI Reasoning and Copilot Layer.

Provides structured executive reasoning on top of deterministic engine outputs.
Supports Google Gemini API when available, with a built-in deterministic
Rule-Based Expert System fallback for offline/test environments.
"""

from __future__ import annotations

import os
from typing import Any

from engine.src.types import DriverRecommendationOutput


def build_expert_reasoning(output: DriverRecommendationOutput, custom_query: str | None = None) -> dict[str, Any]:
    """Generate deterministic, rule-based strategic advice analyzing the 4 direction plans."""
    trip_res = output.objectives.get("max_trip_value")
    pos_res = output.objectives.get("maintain_position")
    rest_res = output.objectives.get("rest_spot")
    safety_res = output.objectives.get("safety_comfort")

    # 1. Situation Assessment
    # Weather wording follows the engine's signal; missing forecast is never described as "good weather".
    weather_desc = "chưa có dự báo mưa phủ khung thời gian đang xét nên chưa đánh giá được rủi ro mưa"
    signal = safety_res.weather_action_signal if safety_res else None
    if signal == "THOI_TIET_THUAN_LOI":
        weather_desc = "dự báo không vượt mức chịu mưa của bạn trong khung thời gian đang xét"
    elif signal in ("TRU_MUA_NGAY", "DI_CHUYEN_TRUOC_KHI_MUA") and safety_res and safety_res.rain_flags:
        windows = ", ".join(f.window or f.valid_time for f in safety_res.rain_flags if f.exceeds_tolerance)
        weather_desc = f"dự báo có mưa vượt mức chịu đựng trong khung {windows}"

    rest_cand_count = len(rest_res.candidates) if rest_res else 0
    top_cand = rest_res.candidates[0] if (rest_res and rest_cand_count > 0) else None

    rest_desc = (
        f"Có {rest_cand_count} điểm dừng nghỉ có routing hợp lệ trong bán kính cho phép."
        if rest_cand_count else "Chưa có điểm dừng nghỉ nào có routing hợp lệ."
    )
    situation = f"Khu vực hiện tại: {weather_desc}. {rest_desc}"

    # 2. Extract and compare the 4 Direction Plans
    plans_overview: dict[str, Any] = {}
    tactical_steps: list[str] = []

    if trip_res and trip_res.plan:
        plans_overview["max_trip_value"] = {
            "title": trip_res.plan.direction_title,
            "target": trip_res.plan.target_location,
            "summary": trip_res.plan.summary,
            "trade_offs": trip_res.plan.trade_offs,
        }
        tactical_steps.append(f"Hướng 1 (Đón cuốc đi xa & cước cao): {trip_res.plan.summary}")

    if pos_res and pos_res.plan:
        plans_overview["maintain_position"] = {
            "title": pos_res.plan.direction_title,
            "target": pos_res.plan.target_location,
            "summary": pos_res.plan.summary,
            "trade_offs": pos_res.plan.trade_offs,
        }
        tactical_steps.append(f"Hướng 2 (Bám trung tâm): {pos_res.plan.summary}")

    if rest_res and rest_res.plan:
        plans_overview["rest_spot"] = {
            "title": rest_res.plan.direction_title,
            "target": rest_res.plan.target_location,
            "summary": rest_res.plan.summary,
            "trade_offs": rest_res.plan.trade_offs,
        }
        tactical_steps.append(f"Hướng 3 (Nghỉ ngơi): {rest_res.plan.summary}")

    if safety_res and safety_res.plan:
        plans_overview["safety_comfort"] = {
            "title": safety_res.plan.direction_title,
            "target": safety_res.plan.target_location,
            "summary": safety_res.plan.summary,
            "trade_offs": safety_res.plan.trade_offs,
        }
        tactical_steps.append(f"Hướng 4 (Lưu thông an toàn, né mưa & né kẹt xe): {safety_res.plan.summary}")

    # 3. Decision Guidance (Helping the driver choose, never forcing)
    decision_guide = (
        "Engine đề xuất 4 kế hoạch hành động hoàn chỉnh độc lập. "
        "Nếu ưu tiên đón cuốc đi xa & cước cao: Chọn Kế hoạch 1 (Định vị tại chốt đón tiềm năng). "
        "Nếu ưu tiên vòng quay nhanh & bám phố: Chọn Kế hoạch 2 (Bám trụ vùng lõi trung tâm). "
        "Nếu cảm thấy mệt mỏi, cần phục hồi: Chọn Kế hoạch 3 (Dừng chân nạp năng lượng). "
        "Nếu muốn chạy xe đỡ mệt, né mưa lớn & kẹt xe: Ưu tiên Kế hoạch 4 (Hành lang lưu thông thông thoáng)."
    )

    priority_rows = output.direction_priority or []
    order_names = {
        "max_trip_value": "Hướng 1 (cuốc giá trị cao)",
        "maintain_position": "Hướng 2 (giữ vị trí)",
        "rest_spot": "Hướng 3 (nghỉ ngơi)",
        "safety_comfort": "Hướng 4 (an toàn/né mưa)",
    }
    recommended_order = [
        {"rank": r["rank"], "direction": order_names[r["objective"]], "reason": r["reason"]}
        for r in priority_rows if r.get("rankable")
    ]
    if recommended_order:
        decision_guide += (
            " Thứ tự nên xem xét trước (chỉ là thứ tự chú ý theo quy tắc rõ ràng, không phải điểm tổng): "
            + "; ".join(f"{r['rank']}. {r['direction']} — {r['reason']}" for r in recommended_order) + "."
        )

    # 4. Contingency / Backup Plan
    backup_plan = (
        "Nếu thời tiết chuyển biến xấu đột ngột hoặc điểm dừng mục tiêu kín chỗ: "
        + (
            f"Chuyển ngay sang điểm dự phòng: {rest_res.candidates[1].name} ({round(rest_res.candidates[1].distance_m)}m)."
            if (rest_res and rest_cand_count > 1 and rest_res.candidates[1].distance_m is not None)
            else "Tấp ngay vào cây xăng hoặc điểm có mái che gần nhất trên tuyến đường."
        )
    )

    # 5. Data Caveats & Grounding
    caveats = [
        "Mọi kế hoạch dựa trên dữ liệu mô hình và snapshot hiện tại; không bịa đặt số liệu booking.",
        "Tài xế là người quyết định cuối cùng dựa trên thể trạng thực tế và mục tiêu cá nhân.",
    ] + list(output.data_quality_warnings)

    return {
        "summary": "4 Kế hoạch hành động độc lập — Tài xế toàn quyền lựa chọn theo ưu tiên cá nhân",
        "situation_assessment": situation,
        "plans_overview": plans_overview,
        "decision_guide": decision_guide,
        "recommended_order": recommended_order,
        "action_steps": tactical_steps,
        "contingency_plan": backup_plan,
        "data_caveats": caveats,
        # v3: structured, number-backed context for the UI/pitch (all optional, None when not computed)
        "tradeoff_matrix": output.tradeoff_matrix,
        "decision_boundaries": output.decision_boundaries,
        "data_roadmap": output.data_roadmap,
        "personal_model": output.personal_model,
        "advisor_mode": "deterministic_expert_system",
    }


def consult_driver_advisor(
    output: DriverRecommendationOutput,
    driver_query: str | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    """Consult the AI Strategic Advisor.

    If an API key is provided and google-genai is installed, can query Gemini.
    Otherwise, cleanly falls back to the deterministic Expert System.
    """
    key = api_key or os.environ.get("GEMINI_API_KEY")
    if not key:
        return build_expert_reasoning(output, driver_query)

    # If API key is available, attempt Gemini Call with fallback
    try:
        from google import genai

        client = genai.Client(api_key=key)
        prompt = f"""
        Bạn là Trợ lý Cố vấn Chiến lược cho tài xế xe công nghệ GigCa.
        Hãy đọc kỹ 4 kế hoạch hành động sau từ Decision Engine và trả lời ngắn gọn, khách quan, thiết thực:
        Dữ liệu 4 Kế hoạch:
        - Hướng 1 (Cước cao): {output.objectives.get('max_trip_value')}
        - Hướng 2 (Giữ vị trí): {output.objectives.get('maintain_position')}
        - Hướng 3 (Điểm nghỉ): {output.objectives.get('rest_spot')}
        - Hướng 4 (An toàn thời tiết): {output.objectives.get('safety_comfort')}
        - Câu hỏi của tài xế (nếu có): {driver_query or 'Hãy phân tích 4 kế hoạch hành động này giúp tôi chọn lựa'}

        Yêu cầu:
        1. Tuyệt đối không chọn thay tài xế; trình bày ưu/nhược điểm từng hướng.
        2. Chia làm 4 phần rõ ràng: Tình thế, So sánh 4 kế hoạch, Kế hoạch dự phòng, Quyền tự quyết của tài xế.
        """
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        return {
            "summary": "Tư vấn & So sánh 4 Kế hoạch Hành động",
            "llm_response": response.text,
            "advisor_mode": "gemini_2.5_flash",
            "fallback_expert": build_expert_reasoning(output, driver_query),
        }
    except Exception:
        # Graceful fallback to expert system
        return build_expert_reasoning(output, driver_query)
