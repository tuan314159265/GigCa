"""Thompson-sampling bandit over zones — handles the "you only see zones you visited" selection bias.

The driver's log only contains zones the driver chose to wait in. Ranking zones by their past mean yield (greedy) can
lock the driver into a mediocre zone forever because better ones were never tried. Each zone is an ARM with a Normal
posterior on its mean cycle yield:
    prior  : the driver's overall mean, worth `prior_k` pseudo-observations (same idea as the engine's shrinkage)
    update : the zone's own realised cycle yields
`p_best` = Monte-Carlo probability (fixed seed -> deterministic) that the zone has the highest true mean. A zone with
little evidence but a real chance of being best is flagged "explore": try it a few times instead of trusting the past.
This is a statement about what the driver's OWN history can and cannot tell, not a forecast of demand.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np


def posterior_table(
    rewards: dict[str, list[float]], prior_k: float, draws: int, seed: int,
    explore_p_best: float = 0.15, explore_max_n: int = 12,
) -> dict[str, dict[str, Any]]:
    """Per arm: posterior mean/sd of its mean reward, p_best, evidence count and the explore flag."""
    arms = sorted(a for a, r in rewards.items() if len(r) >= 1)
    if not arms:
        return {}
    allr = np.asarray([x for a in arms for x in rewards[a]], dtype=float)
    mu0 = float(allr.mean())
    var = float(allr.var(ddof=1)) if len(allr) > 1 else 1.0  # pooled noise variance of one cycle
    post: dict[str, tuple[float, float]] = {}
    for a in arms:
        n = len(rewards[a])
        m = (prior_k * mu0 + float(np.sum(rewards[a]))) / (prior_k + n)
        sd = math.sqrt(var / (prior_k + n))
        post[a] = (m, sd)
    rng = np.random.default_rng(seed)
    samples = np.column_stack([rng.normal(post[a][0], post[a][1], draws) for a in arms])
    winners = np.bincount(np.argmax(samples, axis=1), minlength=len(arms)) / draws
    best_mean = max(m for m, _ in post.values())
    out: dict[str, dict[str, Any]] = {}
    for i, a in enumerate(arms):
        n = len(rewards[a])
        out[a] = {
            "posterior_mean_vnd_per_hour": int(round(post[a][0])),
            "posterior_sd_vnd_per_hour": int(round(post[a][1])),
            "p_best": round(float(winners[i]), 3),
            "evidence_n": n,
            "explore": bool(n <= explore_max_n and winners[i] >= explore_p_best and post[a][0] < best_mean),
        }
    return out
