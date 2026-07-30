"""
Risk Aggregator — Semantic Context Manager
==========================================

Paper reference: Section 4.2 — Semantic Context Manager; Equation 3

Responsibility (SRP): aggregate heterogeneous sensor readings into one
composite risk index r ∈ [0, 1] using Eq. 3.

    r = min(1, temp_risk + co2_risk)
    where:
        temp_risk = max(0, (T - 26) / 10)
        co2_risk  = max(0, (CO2 - 1000) / 1000)

This module does NOT classify faults, simulate candidates, or generate
adaptations.

Extracted from: evaluation_pipeline.py (original), lines 56-64 (risk_score).
"""

from __future__ import annotations

from src.managing_system.shared_knowledge.knowledge_store import Config


def risk_score(state: dict, config: Config) -> float:
    """
    Composite risk index r (Eq. 3, paper §4.2).

    Normalizes temperature and CO2 deviations from nominal and sums them,
    clamped to [0, 1]. Equal weighting matches paper description.

    Parameters
    ----------
    state  : dict with keys 'temperature' and 'co2' (may be None for missing data).
    config : Config — unused directly but kept for interface consistency with
             other pipeline stages.

    Returns
    -------
    float : Composite risk r ∈ [0, 1].

    Extracted from: evaluation_pipeline.py lines 56-64.
    """
    temp = state.get("temperature")
    if temp is None:
        temp = 25.0  # default nominal — missing data treated as no-risk

    co2 = state.get("co2")
    if co2 is None:
        co2 = 400.0  # default nominal

    temp_risk = max(0.0, (temp - 26.0) / 10.0)
    co2_risk = max(0.0, (co2 - 1000.0) / 1000.0)
    return min(1.0, temp_risk + co2_risk)
