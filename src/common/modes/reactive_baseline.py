"""
Reactive Baseline — Execution Mode Strategy
============================================

Paper reference: Section 4 (Reactive Baseline condition)

Implements the simplest baseline: threshold → execute, with no MAPE-K loop,
no fault classification, and no Digital Twin simulation.

Fixed rules:
  - If r > decision_threshold AND temperature > 26°C → C1 (Fan/AC On)
  - If r > decision_threshold AND co2 > 1000 ppm   → C2 (Exhaust On)
  - Otherwise (default)                              → C1

This is the static threshold-rule baseline used to measure how much value
the SA-Only and SA-DT architectures add over pure reactive control.

Extracted from: decision_arms.py (original), lines 74-95 (decide_reactive).
"""

from __future__ import annotations

from typing import Optional

from src.common.adaptation_mode import AdaptationMode
from src.managing_system.shared_knowledge.knowledge_store import Config, SensorReading
from src.digital_twin.semantic_context_manager.risk_aggregator import risk_score


class ReactiveBaseline(AdaptationMode):
    """
    Paper §4 — Reactive Baseline: "threshold → execute. No MAPE-K, no DT."

    Extracted from: decision_arms.py lines 74-95 (decide_reactive).
    """

    @property
    def name(self) -> str:
        return "reactive"

    def evaluate_and_act(
        self,
        reading: SensorReading,
        fault_hint: str,
        prior_state: Optional[dict],
        config: Config,
    ) -> dict:
        """
        Apply fixed threshold rules. No classification, no simulation.

        Extracted verbatim from: decision_arms.py lines 74-95.
        """
        r = risk_score(reading.__dict__, config)
        candidate = None

        if r > config.decision_threshold:
            # Fixed rule based on context — no uncertainty awareness
            if reading.temperature and reading.temperature > 26.0:
                candidate = "C1"
            elif reading.co2 and reading.co2 > 1000.0:
                candidate = "C2"
            else:
                candidate = "C1"

        return {
            "candidate_selected": candidate,
            "selection_method": "threshold_rule",
            "r_measured": r,
            "r_hat": None,
            "utility": None,
            "proactive": False,
            "is_top1": False,
            "routing_correct": None,
        }
