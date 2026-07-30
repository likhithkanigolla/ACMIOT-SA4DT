"""
Proactive Engine — Predictive Analytics Engine
===============================================

Paper reference: Section 4.2 — Predictive Analytics Engine;
                 T_forecast = 55 s; θ_proactive = 95% of nominal safety limit

Responsibility (SRP): determine whether the current risk trajectory warrants
a PROACTIVE adaptation trigger before the hard decision threshold is crossed.

Implementation status (see docs/missing_components.md §1.3):
  The paper describes a sliding-window linear risk projection over T_forecast=55s.
  What is implemented here (faithful to the original code) is a point-in-time
  threshold-band check: if `proactive_trigger < r <= decision_threshold`, the
  episode is flagged as proactive. The forward-projection function is documented
  as a TODO stub without altering any existing numerical behavior.

Extracted from: decision_arms.py (original), lines 166-168 (proactive check
inside decide_sa_dt()).
"""

from __future__ import annotations

from src.managing_system.shared_knowledge.knowledge_store import Config


class ProactiveEngine:
    """
    Paper §4.2 — Predictive Analytics Engine: "computes linear risk trajectories
    over sliding telemetry windows and projects anticipated operational stress
    across a proactive forecasting horizon T_forecast < T_horizon."

    Current implementation: point-in-time threshold band check.

    T_forecast = 55 s is not explicitly named in code; the proactive check fires
    one step before the hard decision threshold, which corresponds to one
    60-second episode look-ahead.
    """

    def is_proactive(self, r: float, config: Config) -> bool:
        """
        Return True if the current risk r falls in the proactive trigger band:
            proactive_trigger < r <= decision_threshold

        Extracted from: decision_arms.py lines 166-168.

        Parameters
        ----------
        r      : float — current composite risk score from risk_aggregator.
        config : Config — holds proactive_trigger and decision_threshold.

        Returns
        -------
        bool : True if proactive episode.

        TODO (future work): replace this point-in-time check with a
        sliding-window linear projection that computes risk trajectory over
        T_forecast = 55 s and fires when the projected trajectory crosses
        θ_proactive = 95% of the nominal safety limit.
        """
        return config.proactive_trigger < r <= config.decision_threshold
