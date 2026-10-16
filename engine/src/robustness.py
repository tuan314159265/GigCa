"""Sensitivity analysis for rankings (deterministic — no random sampling).

Every ranking in the engine rests on assumed parameters (speeds, penalties, weights). Instead of pretending the
top-1 is certain, we perturb each parameter one at a time by +/-pct and measure how often the top-1 survives,
and how thin the margin over the runner-up is.
"""

from __future__ import annotations

from typing import Any, Callable


def perturbation_sets(base: dict[str, float], pct: float) -> list[dict[str, float]]:
    sets = [dict(base)]
    for key in sorted(base):
        for sign in (-1.0, 1.0):
            p = dict(base)
            p[key] = base[key] * (1.0 + sign * pct / 100.0)
            sets.append(p)
    return sets


def analyze_top1(
    ids: list[str],
    score_fn: Callable[[str, dict[str, float]], float],
    base_params: dict[str, float],
    cfg: dict[str, Any],
) -> dict[str, Any] | None:
    """score_fn(id, params) -> higher is better. Ties broken by id for determinism."""
    if not ids:
        return None
    pct = float(cfg["perturbation_pct"])

    def ranking(params: dict[str, float]) -> list[tuple[str, float]]:
        scored = [(i, float(score_fn(i, params))) for i in ids]
        return sorted(scored, key=lambda t: (-t[1], t[0]))

    base_rank = ranking(base_params)
    top1, s1 = base_rank[0]
    runner_up, margin_pct = None, None
    if len(base_rank) > 1:
        runner_up, s2 = base_rank[1]
        denom = max(abs(s1), 1e-9)
        margin_pct = (s1 - s2) / denom * 100.0

    sets = perturbation_sets(base_params, pct)
    flips: dict[str, int] = {}
    kept = 0
    for params in sets:
        winner = ranking(params)[0][0]
        if winner == top1:
            kept += 1
        else:
            flips[winner] = flips.get(winner, 0) + 1
    share = kept / len(sets)
    return {
        "method": f"dao động từng tham số ±{pct:g}% (một-tham-số-một-lần)",
        "parameters": sorted(base_params),
        "runs": len(sets),
        "perturbation_pct": pct,
        "top1": top1,
        "top1_share": round(share, 3),
        "runner_up": runner_up,
        "margin_pct": None if margin_pct is None else round(margin_pct, 2),
        "stable": share >= float(cfg["top1_share_min"]),
        "contested": margin_pct is not None and margin_pct < float(cfg["tie_margin_pct"]),
        "flips_to": dict(sorted(flips.items())),
    }


def describe(rb: dict[str, Any] | None, names: dict[str, str] | None = None) -> str | None:
    """One human sentence about ranking reliability; None when there is nothing useful to say."""
    if not rb:
        return None
    names = names or {}
    top = names.get(rb["top1"], rb["top1"])
    if rb["runner_up"] is None:
        return "Chỉ có 1 ứng viên hợp lệ nên chưa có gì để so sánh."
    ru = names.get(rb["runner_up"], rb["runner_up"])
    if rb["contested"]:
        return (
            f"Hạng 1 ({top}) chỉ hơn hạng 2 ({ru}) ~{rb['margin_pct']:.1f}% — hai lựa chọn gần như ngang nhau, "
            "đừng coi thứ hạng là chắc chắn."
        )
    if not rb["stable"]:
        flips = ", ".join(names.get(k, k) for k in rb["flips_to"]) or "ứng viên khác"
        return (
            f"Hạng 1 ({top}) giữ vị trí ở {rb['top1_share']*100:.0f}% kịch bản giả định dao động ±{rb['perturbation_pct']:g}%; "
            f"đổi sang {flips} khi tham số lệch — kết quả nhạy với giả định."
        )
    return (
        f"Hạng 1 ({top}) giữ vị trí ở {rb['top1_share']*100:.0f}% kịch bản giả định dao động ±{rb['perturbation_pct']:g}% "
        f"(hơn hạng 2 ~{rb['margin_pct']:.1f}%)."
    )
