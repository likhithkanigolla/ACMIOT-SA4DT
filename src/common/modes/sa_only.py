"""
SA-Only — Execution Mode Strategy
===================================

Paper reference: Section 4 (SA-Only condition)

Implements MAPE-K with static routing rules — but WITHOUT Digital Twin
simulation. Faults are classified by heuristic rules and a fixed rulebook maps
fault types to candidates. This deliberately fails in edge cases (S2, S4, S8)
to demonstrate the improvement SA-DT provides.

Failure modes that the paper exploits for comparison:
  S8  → blindly assumes C1 (packet loss, no bracketing)
  S9  → ignores sync lag, acts immediately
  S7  → reacts to every noise crossing (actuation churn)
  S4  → doesn't detect stuck sensor, applies physical cooling
  S2  → can't update tau, keeps applying C1

Extracted from: decision_arms.py (original), lines 97-150 (decide_sa_only).
"""

from __future__ import annotations

from typing import Optional

from src.common.adaptation_mode import AdaptationMode
from src.managing_system.shared_knowledge.knowledge_store import Config, SensorReading
from src.digital_twin.semantic_context_manager.risk_aggregator import risk_score
from src.managing_system.analyse.fault_classifier import (
    FaultClassifier,
    get_uncertainty_class,
    ground_truth_candidate,
)


class SAOnly(AdaptationMode):
    """
    Paper §4 — SA-Only: "MAPE-K → rule pick. Classifies fault type using basic
    rules (NO simulation)."

    Extracted from: decision_arms.py lines 97-150 (decide_sa_only).
    """

    def __init__(self):
        self._classifier = FaultClassifier()

    @property
    def name(self) -> str:
        return "sa_only"

    def evaluate_and_act(
        self,
        reading: SensorReading,
        fault_hint: str,
        prior_state: Optional[dict],
        config: Config,
    ) -> dict:
        """
        Apply MAPE-K routing rules WITHOUT DT simulation.

        Extracted verbatim from: decision_arms.py lines 97-150.
        """
        r = risk_score(reading.__dict__, config)
        candidate = None
        scenario = fault_hint if fault_hint else ""

        if r > config.decision_threshold:
            # Rule 1: Missing data (S8) → default unsafe action C1
            if reading.temperature is None or "S8" in scenario:
                candidate = "C1"

            # Rule 2: Network instability (S9) → ignores lag, acts immediately
            elif "S9" in scenario:
                candidate = "C1"

            # Rule 3: Measurement noise (S7) → reacts to every crossing (churn)
            elif "S7" in scenario:
                candidate = "C1"

            # Rule 4: Stuck sensor (S4) → doesn't know it's stuck, cools physically
            elif "S4" in scenario:
                candidate = "C1"

            # Rule 5: Model error (S2) → can't update tau, keeps using C1
            elif "S2" in scenario:
                candidate = "C1"

            # Rule 6: Sensor drift (S1) or behavioral drift (S5) → recalibrate
            elif "S1" in scenario or "S5" in scenario:
                candidate = "C3"

            else:
                candidate = "C1"  # Fallback

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
            "selection_method": "routing_rule",
            "r_measured": r,
            "r_hat": None,
            "utility": None,
            "proactive": False,
            "is_top1": (candidate == gt) if gt else False,
            "routing_correct": (guessed_class == gt_class) if gt_class else None,
        }

    def reset(self) -> None:
        """Clear classifier history between independent traces."""
        self._classifier.reset()
