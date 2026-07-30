"""
Policy Manager
==============

Paper reference: Section 4.3 — Policy Manager

Responsibility (SRP): intercept the utility-ranked candidate list BEFORE commands
are committed to the Command Orchestrator, enforcing absolute hardware safety
constraints, power budgets, and mechanical actuation limits.

Current implementation status (see docs/missing_components.md §2.1):
  The original code embedded candidate pruning for S4 only, inline inside
  decide_sa_dt(). That pruning has been extracted to AdaptationPlanner
  (pre-simulation candidate generation). The PolicyManager here generalizes the
  gate concept into a callable class that can be extended for additional safety
  rules without modifying any mode strategy code.

  No hard safety constraint rules beyond the S4 pre-simulation pruning existed
  in the original code. This class is therefore a minimal but architecturally
  correct stub: it applies no further filtering by default, but provides the
  correct extension point that matches the paper's description.

This module does NOT score utility, classify faults, or simulate candidates.

Extracted from: decision_arms.py (original) — the S4 pruning concept embedded
in lines 247-248 (now in AdaptationPlanner), generalized into this class.
"""

from __future__ import annotations

from typing import Optional


class PolicyManager:
    """
    Paper §4.3 — Policy Manager: "intercepts utility rankings before commands are
    committed to the Command Orchestrator, enforcing absolute hardware safety
    constraints, power budgets, and mechanical actuation limits."

    Interface: `filter(candidate, scenario_id) -> str | None`

    If the selected candidate violates a hard constraint, returns None (veto).
    Otherwise passes it through unchanged.

    Extending this class (OCP):
        Override `_check_constraints()` to add new safety rules without
        modifying any existing mode strategy code.
    """

    def filter(
        self,
        candidate: Optional[str],
        scenario_id: str,
    ) -> Optional[str]:
        """
        Apply hard safety constraint filtering after utility selection.

        Parameters
        ----------
        candidate   : str or None — the utility-argmax candidate to check.
        scenario_id : str — current fault scenario (for context).

        Returns
        -------
        str or None — the candidate if it passes all constraints, else None.

        Current rules: no additional post-scoring vetoes beyond what
        AdaptationPlanner already pruned pre-simulation.
        (Original code had no generalized hard-constraint gate.)
        """
        if candidate is None:
            return None

        # Extension point: add hard constraint checks here.
        # Example (not in original paper evaluation):
        #   if candidate == "C1" and _power_budget_exceeded():
        #       return None
        #
        # For now, all candidates that survive AdaptationPlanner pre-pruning
        # and UtilityEvaluator scoring are approved.
        return candidate
