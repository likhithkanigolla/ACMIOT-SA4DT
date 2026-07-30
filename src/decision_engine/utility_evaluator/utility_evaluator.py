"""
Utility Evaluator
=================

Paper reference: Section 4.3 — Utility Evaluator; Equation 2

    U(a) = α · Δr(a) − (1 − α) · c(a)

Responsibility (SRP): score each candidate adaptation by predicted risk
reduction minus actuation cost, and select the argmax.

Implements Eq. 2 with α = 0.9 (implicit in the formulation
`utility = −r_hat − cost × 0.1`, which is numerically equivalent to
`α=0.9, Δr = r_current − r_hat, cost term weighted by (1−α) = 0.1`).

This module does NOT classify faults, generate candidates, simulate state
forks, or enforce hard safety constraints. Those belong to fault_classifier,
adaptation_planner, simulation_runtime, and policy_manager.

Extracted from: evaluation_pipeline.py (original), lines 69-70 (utility);
                decision_arms.py (original), lines 152-156 (cost_of).
"""

from __future__ import annotations

from typing import Optional


# ---------------------------------------------------------------------------
# Cost table (paper §4.3, Table 2 candidate costs)
# ---------------------------------------------------------------------------

_CANDIDATE_COSTS: dict[str, float] = {
    "C1": 1.0,   # Fan/AC On         — moderate energy cost
    "C2": 1.0,   # Exhaust On        — moderate energy cost
    "C6": 1.0,   # Reroute Actuator  — same as C1 (bypass)
    "C3": 2.0,   # Recalibrate Temp  — higher cost (disruptive recal)
    "C4": 2.0,   # Recalibrate CO2   — higher cost
    "C5": 0.1,   # Defer Action      — cheap (wait)
}


def cost_of(candidate: str) -> float:
    """
    Return actuation cost c(a) for candidate a.

    Paper §4.3 Eq. 2, cost term.
    Extracted from: decision_arms.py lines 152-156.
    """
    return _CANDIDATE_COSTS.get(candidate, 1.0)


def utility(r_hat: float, cost: float) -> float:
    """
    Utility score U(a) = −r̂ − 0.1 × c(a) (Eq. 2, α = 0.9 implicit).

    Higher utility = lower predicted risk + lower cost.

    Parameters
    ----------
    r_hat : float — predicted risk after applying the candidate (from simulate_candidate).
    cost  : float — actuation cost c(a) from cost_of().

    Returns
    -------
    float : Utility score (higher is better).

    Extracted from: evaluation_pipeline.py lines 69-70.
    """
    return -r_hat - (cost * 0.1)


# ---------------------------------------------------------------------------
# UtilityEvaluator — full scoring + selection interface
# ---------------------------------------------------------------------------

class UtilityEvaluator:
    """
    Paper §4.3 — Utility Evaluator: "scores candidate adaptations by predicted
    risk reduction minus actuation cost" (Eq. 2).

    Exposes a minimal, focused interface:
        `select_best(candidates, simulated_states) -> (best_candidate, best_utility, best_r_hat)`

    This is the ONLY class that depends on `utility()` and `cost_of()` — no
    other component should import these functions directly.
    """

    def select_best(
        self,
        candidates: list[str],
        simulated_states: dict[str, dict],
    ) -> tuple[Optional[str], float, Optional[float]]:
        """
        Score all candidates and return the argmax by Eq. 2.

        Parameters
        ----------
        candidates       : list of candidate IDs to evaluate.
        simulated_states : dict mapping candidate_id → simulated_state_dict.
                           The simulated state must contain 'r_hat' key (predicted risk).

        Returns
        -------
        best_candidate : str or None
        best_utility   : float (−∞ if no candidates)
        best_r_hat     : float or None
        """
        best_candidate: Optional[str] = None
        best_utility: float = -float("inf")
        best_r_hat: Optional[float] = None

        for c in candidates:
            if c not in simulated_states:
                continue
            r_h = simulated_states[c].get("r_hat")
            if r_h is None:
                continue
            u = utility(r_h, cost_of(c))
            if u > best_utility:
                best_utility = u
                best_candidate = c
                best_r_hat = r_h

        return best_candidate, best_utility, best_r_hat
