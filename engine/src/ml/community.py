"""Community pool (tier 3 of the data ladder) — PROTOTYPE, not wired into the engine.

Many drivers contribute anonymous (cell, value) records. The pool keeps a cell only if at least `k_min` DISTINCT drivers
contributed to it (k-anonymity) and publishes just the mean of the per-driver means, the between-driver spread and the
number of drivers — never a per-driver value, and a heavy contributor cannot dominate (each driver counts once).
A new driver with a short history then shrinks their own zone mean toward the community mean with weights from an
empirical-Bayes (normal-normal) model: little own data -> lean on the community, lots of own data -> trust yourself.

Limits (stated, not hidden): k-anonymity of aggregates is NOT differential privacy (an attacker who already knows k-1
contributors can still infer the last one); a community mean says nothing about THIS driver's tariff or vehicle, which is
why the shrinkage weight comes from the observed between-driver variance instead of being fixed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np

CellKey = tuple[int, int]


@dataclass(frozen=True)
class Contribution:
    driver_id: str
    cell: CellKey
    value: float


def pool(contribs: Iterable[Contribution], k_min: int) -> dict[str, Any]:
    """Aggregate by cell. Returns {"cells": {cell: stats}, "suppressed_cells": n}; cells below k_min are dropped entirely."""
    per: dict[CellKey, dict[str, list[float]]] = {}
    for c in contribs:
        if c.value != c.value:  # NaN is never pooled
            continue
        per.setdefault(c.cell, {}).setdefault(c.driver_id, []).append(c.value)
    cells: dict[CellKey, dict[str, Any]] = {}
    suppressed = 0
    for cell, by_driver in per.items():
        if len(by_driver) < k_min:
            suppressed += 1
            continue
        means = np.asarray([float(np.mean(v)) for v in by_driver.values()])
        cells[cell] = {
            "n_drivers": len(by_driver),
            "mean": float(means.mean()),
            "between_driver_var": float(means.var(ddof=1)),
        }
    return {"cells": cells, "suppressed_cells": suppressed, "k_min": k_min}


def shrink_to_community(own: list[float], prior_mean: float, between_var: float, own_noise_var: float | None = None) -> dict[str, float]:
    """Normal-normal posterior mean of the driver's zone mean: weight on the driver's own data = tau2 / (tau2 + sigma2/n)."""
    n = len(own)
    if n == 0:
        return {"estimate": prior_mean, "weight_own": 0.0}
    own_mean = float(np.mean(own))
    sigma2 = own_noise_var if own_noise_var is not None else (float(np.var(own, ddof=1)) if n > 1 else float("inf"))
    tau2 = max(between_var, 1e-9)
    w = 0.0 if math.isinf(sigma2) else tau2 / (tau2 + sigma2 / n)
    return {"estimate": w * own_mean + (1.0 - w) * prior_mean, "weight_own": w}
