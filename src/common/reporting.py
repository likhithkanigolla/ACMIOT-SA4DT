"""
Common Reporting Utilities
===========================

Paper reference: Section 5 — Metrics (SR, TTR, IRE, Cost)

Responsibility (SRP): compute per-trial summary statistics from a contiguous
block of episodes for the same (scenario, mode) pair.

The trial-summary computation was duplicated verbatim TWICE in the original
experiment_runner.py (lines 257-276 and lines 279-298 — identical logic for
the "middle" and "last" chunk cases). This module extracts that logic once.

Definitions (paper §5):
  SR  — Success Rate: fraction of trials where fault was resolved
  TTR — Time-to-Recovery: number of episodes until r < recovery_threshold
        for recovery_persistence consecutive readings
  IRE — Integrated Recovery Error: sum(r_measured) over the incident
  Cost — Mean actuation cost per episode
"""

from __future__ import annotations

from typing import Optional

import numpy as np


def compute_trial_summary(chunk: list, config) -> dict:
    """
    Compute one row of the trial summary CSV from a contiguous episode chunk.

    Parameters
    ----------
    chunk  : list[Episode] — all episodes from one contiguous (scenario, mode) block.
    config : Config — for decision_threshold (lead time computation).

    Returns
    -------
    dict with keys:
        episodes_to_recover, episode_success, mean_risk_drift, mean_cost,
        proactive_count, integrated_risk, lead_time

    Extracted from: experiment_runner.py lines 257-276 and 279-298
    (the two identical blocks that computed chunk summaries).
    """
    if not chunk:
        return {}

    e_rec: Optional[int] = chunk[0].episodes_to_recover
    succ: bool = chunk[0].episode_success

    mean_risk: float = float(np.mean([e.r_measured for e in chunk]))
    integrated_risk: float = float(np.sum([e.r_measured for e in chunk]))

    total_cost = sum(
        _episode_cost(e.candidate_selected) for e in chunk
    )
    mean_cost: float = total_cost / len(chunk)
    proactive_count: int = sum(1 for e in chunk if e.proactive)

    # Lead time: episodes between first proactive action and first threshold crossing
    first_proactive_idx = next(
        (i for i, e in enumerate(chunk) if e.proactive), -1
    )
    first_reactive_idx = next(
        (i for i, e in enumerate(chunk) if e.r_measured > config.decision_threshold),
        -1,
    )
    lead_time: int = (
        first_reactive_idx - first_proactive_idx
        if (
            first_proactive_idx != -1
            and first_reactive_idx != -1
            and first_proactive_idx < first_reactive_idx
        )
        else 0
    )

    return {
        "episodes_to_recover": e_rec if e_rec is not None else -1,
        "episode_success": succ,
        "mean_risk_drift": mean_risk,
        "mean_cost": mean_cost,
        "proactive_count": proactive_count,
        "integrated_risk": integrated_risk,
        "lead_time": lead_time,
    }


def _episode_cost(candidate: Optional[str]) -> float:
    """
    Map candidate → actuation cost for trial summary.

    Extracted from: experiment_runner.py lines 262 and 285
    (the inline cost expression duplicated in both chunk-handling blocks).
    """
    if candidate in ("C1", "C2", "C6"):
        return 1.0
    if candidate in ("C3", "C4"):
        return 2.0
    if candidate == "C5":
        return 0.1
    return 0.0  # None / no action
