"""
Uncertainty Routing Engine
===========================

Paper reference: Section 4.3 — Uncertainty Routing Engine

Responsibility (SRP): route each fault scenario to the appropriate simulation
strategy based on its uncertainty class (epistemic S1-S6 vs aleatoric S7-S11),
and build the scenario-specific simulated state dictionaries needed by the
Utility Evaluator.

This module does NOT score utility, enforce safety constraints, apply physical
effects, or dispatch commands. Those belong to utility_evaluator, policy_manager,
execute, and command_orchestrator respectively.

Extracted from: decision_arms.py (original), lines 7-18 (get_uncertainty_class),
                lines 179-267 (scenario-specific simulation strategies inside
                decide_sa_dt).
"""

from __future__ import annotations

from src.managing_system.shared_knowledge.knowledge_store import Config, SensorReading
from src.digital_twin.simulation_runtime.candidate_simulator import simulate_candidate
from src.digital_twin.twin_state_sync.sync_engine import sync_penalty
from src.digital_twin.semantic_context_manager.risk_aggregator import risk_score
from src.decision_engine.utility_evaluator.utility_evaluator import cost_of, utility
from src.managing_system.analyse.fault_classifier import get_uncertainty_class


class UncertaintyRoutingEngine:
    """
    Paper §4.3 — Uncertainty Routing Engine: "inspects uncertainty class; routes to
    parameter correction (epistemic) or conservative fallback (aleatoric)."

    For each scenario, applies the matching simulation strategy to produce a dict
    mapping candidate_id → {'r_hat': float} for the UtilityEvaluator to score.

    Routing map (all 11 scenarios):
        S1 Sensor Drift            → standard DT simulation
        S2 Model Error             → tau × 2.0 re-estimation
        S3 Actuation Deviation     → standard DT simulation
        S4 Stuck Sensor            → handled by AdaptationPlanner (pruning)
        S5 Behavioral Drift        → tau × 2.0 re-estimation
        S6 Actuator Failure        → standard DT simulation
        S7 Measurement Noise       → deferral preference (C1/C2/C6 cost +5)
        S8 Packet Loss             → worst-case/best-case bracketing
        S9 Network Instability     → sync-lag penalty applied to cost
        S10 Reconnection Events    → standard DT simulation
        S11 Environmental Variab.  → standard DT simulation

    Extracted from: decision_arms.py lines 179-267 (scenario branches in decide_sa_dt).
    """

    def route_and_simulate(
        self,
        candidates: list[str],
        base_state: dict,
        sensor: SensorReading,
        scenario_id: str,
        adjusted_tau: float,
        config: Config,
    ) -> tuple[str | None, float, float | None]:
        """
        Route `scenario_id` to the correct strategy, simulate all candidates,
        and return the best (candidate, utility, r_hat).

        Parameters
        ----------
        candidates   : Pre-filtered candidate list from AdaptationPlanner.
        base_state   : Prior physical state dict (fallback: perceived_state).
        sensor       : Current SensorReading (for lag_seconds in S9).
        scenario_id  : Current fault label (e.g., "S8(temperature)").
        adjusted_tau : From KnowledgeStore.get_adjusted_tau() — tau * 2.0 for S2/S5.
        config       : Shared Config.

        Returns
        -------
        (best_candidate, best_utility, best_r_hat)
        """
        best_u = -float("inf")
        candidate: str | None = None
        r_hat: float | None = None

        if "S8" in scenario_id:
            # Packet Loss: worst-case / best-case bracketing
            # Paper §4.3: "epistemic uncertainty in missing data → bracket"
            # Extracted from decision_arms.py lines 179-199
            worst_case = base_state.copy()
            worst_case["temperature"] = 30.0
            best_case = base_state.copy()
            best_case["temperature"] = 20.0

            for c in candidates:
                sim_worst = simulate_candidate(worst_case, c, config)
                sim_best = simulate_candidate(best_case, c, config)
                r_worst = risk_score(sim_worst, config)
                r_best = risk_score(sim_best, config)

                u_worst = utility(r_worst, cost_of(c))
                u_best = utility(r_best, cost_of(c))
                u_expected = (u_worst + u_best) / 2.0

                if u_expected > best_u:
                    best_u = u_expected
                    candidate = c
                    r_hat = (r_worst + r_best) / 2.0

        elif "S9" in scenario_id:
            # Network Instability: sync-lag penalty inflates cost (Eq. 1)
            # Extracted from decision_arms.py lines 201-218
            lag = sensor.lag_seconds
            for c in candidates:
                sim = simulate_candidate(base_state, c, config)
                r_h = risk_score(sim, config)

                cost = cost_of(c)
                if c not in ["C3", "C4", "C5"]:
                    cost += sync_penalty(lag) * 10.0

                u = utility(r_h, cost)
                if u > best_u:
                    best_u = u
                    candidate = c
                    r_hat = r_h

        elif "S7" in scenario_id:
            # Measurement Noise: prefer deferral to avoid actuation churn
            # Extracted from decision_arms.py lines 220-233
            for c in candidates:
                sim = simulate_candidate(base_state, c, config)
                r_h = risk_score(sim, config)
                cost = cost_of(c)
                # Penalize reactive physical actions to avoid oscillation
                if c in ["C1", "C2", "C6"]:
                    cost += 5.0
                u = utility(r_h, cost)
                if u > best_u:
                    best_u = u
                    candidate = c
                    r_hat = r_h

        elif "S2" in scenario_id or "S5" in scenario_id:
            # Model Error / Behavioral Drift: use adjusted tau from KnowledgeStore
            # Extracted from decision_arms.py lines 235-245
            for c in candidates:
                sim = simulate_candidate(base_state, c, config, override_tau=adjusted_tau)
                r_h = risk_score(sim, config)
                u = utility(r_h, cost_of(c))
                if u > best_u:
                    best_u = u
                    candidate = c
                    r_hat = r_h

        else:
            # Standard DT simulation: S1, S3, S4, S6, S10, S11
            # (S4 already pruned in AdaptationPlanner)
            # Extracted from decision_arms.py lines 258-267
            for c in candidates:
                sim = simulate_candidate(base_state, c, config)
                r_h = risk_score(sim, config)
                u = utility(r_h, cost_of(c))
                if u > best_u:
                    best_u = u
                    candidate = c
                    r_hat = r_h

        return candidate, best_u, r_hat
