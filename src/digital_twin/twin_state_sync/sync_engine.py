"""
Twin State Synchronisation — Sync Engine
=========================================

Paper reference: Section 4.2 — Twin State Synchronisation; Equation 1

Responsibility (SRP): compute the sync-penalty discount that is applied when
the measured sensor data arrives with a known communication lag d.

    sync_penalty(d) = d × 0.01

Paper §4.2: "aligns virtual state with live sensor streams; computes sync lag d;
applies sync-penalty discount" (Eq. 1).

Note (docs/missing_components.md §3): The paper specifies a cap at γ_max = 0.35
(max discount = 35%). The original code did not apply this cap. That behavior is
preserved here without change.

Extracted from: evaluation_pipeline.py (original), lines 66-67 (sync_penalty).
"""

from __future__ import annotations


def sync_penalty(lag: float) -> float:
    """
    Synchronisation penalty for a given communication lag (Eq. 1).

    Parameters
    ----------
    lag : float — lag in seconds (d in the paper).

    Returns
    -------
    float — penalty value. Inflated into the cost term inside decide_sa_dt()
            for S9 (Network Instability).

    Note: paper specifies γ_max = 0.35 cap; not applied here to preserve
    original numerical behavior (see docs/missing_components.md §3).

    Extracted from: evaluation_pipeline.py line 66-67.
    """
    return lag * 0.01
