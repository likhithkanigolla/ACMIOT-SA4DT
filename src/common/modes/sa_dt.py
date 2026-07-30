"""
SA-DT — Execution Mode Strategy (Proposed Architecture)
=========================================================

Paper reference: Section 4 — SA-DT (Self-Adaptive + Digital Twin)

The full proposed architecture: MAPE-K + Digital Twin simulation gate +
Utility Evaluator + Uncertainty Routing + Policy Manager.

Pipeline per episode:
  Monitor → Analyse (FaultClassifier) → Plan (AdaptationPlanner)
  → [DT Simulation Gate: UncertaintyRoutingEngine routes to strategy]
  → Utility Evaluator (argmax Eq. 2) → Policy Manager (safety filter)
  → Execute

The DT simulation gate is what distinguishes SA-DT from SA-Only: instead
of static rules, candidates are evaluated via DT simulation + utility scoring
before any command reaches the physical actuators.

This class depends on injected components (Dependency Injection):
  - UncertaintyRoutingEngine  (routes scenario → simulation strategy)
  - AdaptationPlanner         (generates pruned candidate set)
  - ProactiveEngine           (detects proactive trigger)
  - FaultClassifier           (epistemic/aleatoric classification)
  - PolicyManager             (post-scoring safety filter)
  - KnowledgeStore            (provides adjusted tau)

Extracted from: decision_arms.py (original), lines 158-282 (decide_sa_dt),
restructured to use injected components instead of inline imports.
"""

from __future__ import annotations

from typing import Optional

from src.common.adaptation_mode import AdaptationMode
from src.managing_system.shared_knowledge.knowledge_store import (
    Config,
    KnowledgeStore,
    SensorReading,
)
from src.digital_twin.semantic_context_manager.risk_aggregator import risk_score
from src.digital_twin.predictive_analytics.proactive_engine import ProactiveEngine
from src.managing_system.plan.adaptation_planner import AdaptationPlanner
from src.managing_system.analyse.fault_classifier import (
    FaultClassifier,
    get_uncertainty_class,
    ground_truth_candidate,
)
from src.decision_engine.uncertainty_routing.routing_engine import UncertaintyRoutingEngine
from src.decision_engine.policy_manager.policy_manager import PolicyManager


class SADT(AdaptationMode):
    """
    Paper §4 — SA-DT: "MAPE-K → DT simulate → DE (Decision Engine)."

    Full proposed architecture. Implements advanced strategies for all S1-S11
    scenarios matching theoretical expectations documented in the paper.

    Extracted from: decision_arms.py lines 158-282 (decide_sa_dt),
    re-wired to use injected components.
    """

    def __init__(self, knowledge_store: KnowledgeStore):
        self._store = knowledge_store
        self._planner = AdaptationPlanner()
        self._router = UncertaintyRoutingEngine()
        self._proactive = ProactiveEngine()
        self._classifier = FaultClassifier()
        self._policy = PolicyManager()

    @property
    def name(self) -> str:
        return "sa_dt"

    def evaluate_and_act(
        self,
        reading: SensorReading,
        fault_hint: str,
        prior_state: Optional[dict],
        config: Config,
    ) -> dict:
        """
        Full MAPE-K + DT simulation gate + utility selection + policy filter.

        Extracted verbatim in logic from: decision_arms.py lines 158-282.
        """
        perceived_state = reading.__dict__
        r = risk_score(perceived_state, config)

        # Proactive trigger check (Predictive Analytics Engine)
        proactive = self._proactive.is_proactive(r, config)

        candidate: Optional[str] = None
        r_hat: Optional[float] = None
        best_u: float = -float("inf")

        if r > config.decision_threshold or proactive:
            scenario = fault_hint if fault_hint else ""
            base_state = perceived_state.copy()
            if prior_state:
                if base_state.get("temperature") is None:
                    base_state["temperature"] = prior_state.get("temperature")
                if base_state.get("co2") is None:
                    base_state["co2"] = prior_state.get("co2")

            # Plan: generate feasible candidate set (with S4 pruning)
            candidates = self._planner.generate_candidates(scenario)

            # DT Simulation Gate: route to scenario-specific strategy
            # Uses KnowledgeStore for adjusted tau (S2/S5 re-estimation)
            adjusted_tau = self._store.get_adjusted_tau(scenario)
            candidate, best_u, r_hat = self._router.route_and_simulate(
                candidates=candidates,
                base_state=base_state,
                sensor=reading,
                scenario_id=scenario,
                adjusted_tau=adjusted_tau,
                config=config,
            )

            # Policy Manager: post-scoring safety filter
            candidate = self._policy.filter(candidate, scenario)

        # Classification for accuracy metrics
        gt_class = (
            get_uncertainty_class(fault_hint)
            if fault_hint and fault_hint.startswith("S")
            else None
        )
        gt = (
            ground_truth_candidate(fault_hint)
            if fault_hint and fault_hint.startswith("S")
            else None
        )
        guessed_class = self._classifier.classify(reading, fault_hint, config)

        return {
            "candidate_selected": candidate,
            "selection_method": "utility_de",
            "r_measured": r,
            "r_hat": r_hat,
            "utility": best_u if candidate else None,
            "proactive": proactive,
            "is_top1": (candidate == gt) if gt else False,
            "routing_correct": (guessed_class == gt_class) if gt_class else None,
        }

    def reset(self) -> None:
        """Clear classifier history between independent traces."""
        self._classifier.reset()
