"""
Adaptation Planner
==================

Paper reference: Section 4.4 — Plan

Responsibility (SRP): generate the set of feasible candidate adaptations to
hand off to the Decision Engine (Simulation Gate → Utility Evaluator →
Policy Manager).

This module does NOT simulate outcomes, score utility, dispatch commands, or
classify fault types. Those belong to simulation_runtime, utility_evaluator,
execute, and fault_classifier respectively.

Candidates (paper §4.3):
  C1 — Fan / AC On (physical temperature reduction)
  C2 — Exhaust On (CO2 / ventilation)
  C3 — Recalibrate Temperature (epistemic: sensor drift correction)
  C4 — Recalibrate CO2   (epistemic: sensor drift correction)
  C5 — Defer Action      (aleatoric: wait for better data, e.g., S7/S8)
  C6 — Reroute Actuator  (epistemic: bypass failed actuator, e.g., S6)

Extracted from: decision_arms.py (original) — candidate list construction
inside decide_sa_dt() (line 176) and the S4 pruning logic (lines 247-248).
"""

from __future__ import annotations

from typing import Optional


# ---------------------------------------------------------------------------
# Full candidate set (constant — matches paper §4.3 description)
# ---------------------------------------------------------------------------

ALL_CANDIDATES: list[str] = ["C1", "C2", "C3", "C4", "C5", "C6"]


# ---------------------------------------------------------------------------
# Adaptation Planner
# ---------------------------------------------------------------------------

class AdaptationPlanner:
    """
    Paper §4.4 — Plan: "synthesizes feasible candidate adaptations C1-C6 and
    transfers them to the Decision Engine."

    The planner also applies early hard-constraint pruning for scenarios where
    a subset of candidates is known to be physically infeasible or unsafe.
    This pruning is distinct from the PolicyManager's safety gate (which applies
    after utility scoring); here it reduces the search space before simulation.

    Extracted from: decision_arms.py lines 176 and 247-248.
    """

    def generate_candidates(self, scenario_id: str) -> list[str]:
        """
        Return the list of feasible candidates for this scenario.

        For most scenarios → all six candidates.
        For S4 (Stuck Sensor) → pruned to {C3, C4, C6}:
          A stuck sensor means the physical actuators (C1, C2) would act on
          a frozen reading, causing potentially dangerous over-actuation.
          Defer (C5) is also excluded since the sensor state is known to be
          stale, not just uncertain.

        Extracted from: decision_arms.py lines 247-248.

        Parameters
        ----------
        scenario_id : str
            The current fault scenario label (e.g., "S4(temperature)").

        Returns
        -------
        list[str]
            Ordered list of candidate identifiers to pass to the Decision Engine.
        """
        if "S4" in scenario_id:
            # Paper §4.3 / decision_arms.py L247-248:
            # "Stuck Sensor: Flag divergence, use cross-signal or recalibrate.
            #  Pruned options: skip naive C1/C2"
            return ["C3", "C4", "C6"]
        return list(ALL_CANDIDATES)
