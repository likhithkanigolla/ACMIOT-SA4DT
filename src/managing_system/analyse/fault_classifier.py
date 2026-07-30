"""
Fault Classifier
================

Paper reference: Section 4.4 — Analyse; Table 1 (S1-S11 taxonomy)

Responsibility (SRP): runtime fault / uncertainty classification.

  - Classifies each scenario as epistemic (S1-S6: sensor/model/actuation
    faults reducible by better information) or aleatoric (S7-S11: inherent
    randomness requiring conservative strategies).
  - Provides the ground-truth candidate function used for top-1 accuracy
    metrics in the paper's evaluation.
  - Maintains a short rolling history of readings for heuristic classification
    when no explicit scenario ID is available.

This module does NOT compute risk scores, generate candidates, simulate
outcomes, or dispatch commands. Those belong to semantic_context_manager,
plan, simulation_runtime, and execute respectively.

Extracted from: decision_arms.py (original), lines 7-72.
"""

from __future__ import annotations

import re
from typing import Optional

import numpy as np

from src.managing_system.shared_knowledge.knowledge_store import SensorReading, Config


# ---------------------------------------------------------------------------
# Uncertainty class constants
# ---------------------------------------------------------------------------

EPISTEMIC_SCENARIOS = frozenset({"S1", "S2", "S3", "S4", "S5", "S6"})
ALEATORIC_SCENARIOS = frozenset({"S7", "S8", "S9", "S10", "S11"})

# Heuristic classification thresholds (Table 1 / Section 6 constraints)
CLASSIFICATION_THRESHOLDS = {
    "sudden_temp_jump": 2.0,   # > 2°C step → likely epistemic (drift/recal)
    "gradual_temp_drift": 0.5,  # sustained drift → epistemic
    "noise_variance": 1.5,      # high variance → aleatoric (noise)
}


# ---------------------------------------------------------------------------
# Pure functions (stateless — depend only on inputs)
# ---------------------------------------------------------------------------

def get_uncertainty_class(scenario_id: str) -> str:
    """
    Returns 'epistemic' for S1-S6, 'aleatoric' for S7-S11.

    Paper Table 1: S1 Sensor Drift … S6 Actuator Failure → epistemic;
                   S7 Measurement Noise … S11 Environmental Variability → aleatoric.

    Extracted from: decision_arms.py lines 7-18.
    """
    if "S" not in scenario_id:
        return "aleatoric"
    try:
        match = re.search(r"S(\d+)", scenario_id)
        if match:
            s_num = int(match.group(1))
            if 1 <= s_num <= 6:
                return "epistemic"
    except Exception:
        pass
    return "aleatoric"


def ground_truth_candidate(scenario_id: str) -> str:
    """
    Returns the optimal ground-truth candidate for a known scenario.

    Epistemic faults → 'C3' (recalibration addresses the root cause).
    Aleatoric faults → 'C1' (physical actuation is the best available response).

    Used to compute top-1 accuracy (is_top1) in evaluation metrics.
    Extracted from: decision_arms.py lines 20-24.
    """
    if get_uncertainty_class(scenario_id) == "epistemic":
        return "C3"
    return "C1"


# ---------------------------------------------------------------------------
# FaultClassifier (stateful — maintains rolling reading history)
# ---------------------------------------------------------------------------

class FaultClassifier:
    """
    Paper §4.4 — Analyse: "detects anomalies; classifies via taxonomy; computes
    composite risk r."

    Note: the composite risk computation (Eq. 3) lives in
    src.digital_twin.semantic_context_manager.risk_aggregator — this class
    handles only the fault TYPE classification (epistemic vs aleatoric).

    Maintains a rolling window of up to 10 recent SensorReadings to enable
    heuristic classification when no explicit scenario label is available.

    Extracted from: decision_arms.py lines 33-72 (_classify_fault, global
    _recent_readings list), re-structured as an instance with clean state.
    """

    def __init__(self, history_len: int = 10):
        self._recent_readings: list[SensorReading] = []
        self._history_len = history_len

    def classify(self, sensor: SensorReading, fault_hint: str, config: Config) -> str:
        """
        Heuristic classifier — returns 'epistemic' or 'aleatoric'.

        Parameters
        ----------
        sensor     : SensorReading — current perceived reading.
        fault_hint : str — scenario label (e.g., "S1(temperature)") or empty.
        config     : Config — unused directly but kept for interface consistency.

        Extracted from: decision_arms.py lines 35-72 (_classify_fault).
        """
        self._recent_readings.append(sensor)
        if len(self._recent_readings) > self._history_len:
            self._recent_readings.pop(0)

        # Missing data → aleatoric (can't classify without a reading)
        if sensor.temperature is None:
            return "aleatoric"

        # Use fault_hint if explicitly provided (e.g., from scenario label)
        if fault_hint:
            if "epistemic" in fault_hint.lower():
                return "epistemic"
            if "aleatoric" in fault_hint.lower():
                return "aleatoric"
            # Scenario-ID pass-through
            if "S" in fault_hint:
                return get_uncertainty_class(fault_hint)

        # Heuristic based on rolling history
        if len(self._recent_readings) > 2:
            valid = [
                r.temperature
                for r in self._recent_readings
                if r.temperature is not None
            ]
            if len(valid) > 2:
                diff = abs(valid[-1] - valid[-2])
                var = float(np.var(valid))

                # Sudden step change → likely sensor re-calibration event (epistemic)
                if diff > CLASSIFICATION_THRESHOLDS["sudden_temp_jump"]:
                    return "epistemic"
                # High variance → measurement noise (aleatoric)
                if var > CLASSIFICATION_THRESHOLDS["noise_variance"]:
                    return "aleatoric"

        # Default fallback — conservative aleatoric assumption
        return "aleatoric"

    def reset(self) -> None:
        """Clear rolling history (call between independent traces)."""
        self._recent_readings.clear()
