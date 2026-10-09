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
import random
from typing import Any

import numpy as np

from engine.src.ml.simulate import ZONES, cycle_yield


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


# --------------------------------------------------------------------------- simulation against a known truth
def simulate_policies(
    horizon: int = 300, seeds: int = 30, hour: int = 18, rain_mm: float = 0.0,
    epsilon: float = 0.1, prior_k: float = 5.0, truth_draws: int = 20000,
) -> dict[str, Any]:
    """Cumulative regret (VND/hour lost vs always picking the truly best zone) of greedy, epsilon-greedy and Thompson.

    Rewards come from the ground-truth cycle sampler in `simulate.py`; the policies see only what they have pulled."""
    names = sorted(ZONES)
    truth_rng = random.Random(1234)
    mu = {z: sum(cycle_yield(truth_rng, z, hour, rain_mm) for _ in range(truth_draws)) / truth_draws for z in names}
    best = max(mu.values())
    policies = ("greedy", "epsilon_greedy", "thompson")
    regret = {p: np.zeros(horizon) for p in policies}
    best_pick = {p: 0.0 for p in policies}
    for sd in range(seeds):
        for pol in policies:
            rng = random.Random(10_000 + sd)
            hist: dict[str, list[float]] = {z: [] for z in names}
            cum = 0.0
            for t in range(horizon):
                untried = [z for z in names if not hist[z]]
                if untried:
                    arm = untried[0]  # every policy starts with one pull per zone
                elif pol == "greedy":
                    arm = max(names, key=lambda z: sum(hist[z]) / len(hist[z]))
                elif pol == "epsilon_greedy":
                    arm = rng.choice(names) if rng.random() < epsilon else max(names, key=lambda z: sum(hist[z]) / len(hist[z]))
                else:
                    allr = [x for z in names for x in hist[z]]
                    mu0 = sum(allr) / len(allr)
                    var = (sum((x - mu0) ** 2 for x in allr) / max(1, len(allr) - 1)) or 1.0
                    draws = {}
                    for z in names:
                        n = len(hist[z])
                        m = (prior_k * mu0 + sum(hist[z])) / (prior_k + n)
                        draws[z] = rng.gauss(m, math.sqrt(var / (prior_k + n)))
                    arm = max(names, key=lambda z: draws[z])
                hist[arm].append(cycle_yield(rng, arm, hour, rain_mm))
                cum += best - mu[arm]
                regret[pol][t] += cum / seeds
                if t >= horizon - 50 and mu[arm] == best:
                    best_pick[pol] += 1.0 / (50 * seeds)
    return {
        "horizon": horizon, "seeds": seeds, "context": {"hour": hour, "rain_mm": rain_mm},
        "true_mean_yield_vnd_per_hour": {z: int(round(v)) for z, v in mu.items()}, "best_zone": max(mu, key=mu.get),
        "cumulative_regret_vnd_per_hour": {p: int(round(float(regret[p][-1]))) for p in policies},
        "best_zone_pick_rate_last_50": {p: round(best_pick[p], 3) for p in policies},
    }
