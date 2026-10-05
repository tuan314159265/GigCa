"""Readiness Gate — entrance control before any objective scorer runs.

Implements Section 4 of engine/spec.md.
A scorer must never decide its own readiness mode; the gate determines
FULL, PARTIAL, or INSUFFICIENT based on objective_readiness and data_status.
"""

from __future__ import annotations

from engine.src.config import OBJECTIVE_DATA_DEPENDENCIES
from engine.src.types import (
    DataStatusValue,
    ObjectiveKey,
    ObjectiveStatus,
    ReadinessMode,
)


def resolve_readiness(
    objective: ObjectiveKey,
    data_status: dict[str, DataStatusValue],
    objective_readiness: dict[ObjectiveKey, ObjectiveStatus],
) -> ReadinessMode:
    """Resolve the execution mode (FULL, PARTIAL, INSUFFICIENT) for an objective.

    Rules:
    - If declared readiness is 'insufficient_data', returns 'INSUFFICIENT'.
    - If declared readiness is 'partial', returns 'PARTIAL'.
    - Even if declared is 'available', each required data dependency is inspected:
      if any dependency is 'missing', 'stale', or 'not_integrated', it degrades to 'PARTIAL'.
    - Returns 'FULL' only if declared is 'available' and all dependencies are 'available'.
    """
    declared = objective_readiness.get(objective)
    if declared == "insufficient_data":
        return "INSUFFICIENT"
    if declared == "partial":
        return "PARTIAL"

    required_groups = OBJECTIVE_DATA_DEPENDENCIES.get(objective, [])
    for group in required_groups:
        status = data_status.get(group)
        if status in ("missing", "stale", "not_integrated", None):
            return "PARTIAL"

    return "FULL" if declared == "available" else "PARTIAL"
