"""
Adaptation Mode — Abstract Strategy Interface
==============================================

Paper reference: Section 4 — three evaluation conditions:
  1. Reactive Baseline (no MAPE-K, no DT)
  2. SA-Only (MAPE-K, no DT simulation)
  3. SA-DT (full MAPE-K + DT simulation gate)

This abstract base class defines the single interface that all execution
modes must implement:

    evaluate_and_act(reading, fault_hint, prior_state, config) -> dict

This allows the main orchestration loop (run.py) and the experiment runner
to swap modes without any conditional branching — consistent with the
Open-Closed Principle (OCP):
  - Open for extension: add a new mode by subclassing AdaptationMode.
  - Closed for modification: the orchestration loop never changes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from src.managing_system.shared_knowledge.knowledge_store import Config, SensorReading


class AdaptationMode(ABC):
    """
    Abstract strategy for one MAPE-K decision cycle.

    All three modes (Reactive, SA-Only, SA-DT) implement this interface.
    The orchestration loop depends only on `AdaptationMode` — never on a
    concrete implementation (Dependency Inversion Principle).

    Return dict contract (fields used by ActionExecutor and metrics):
        candidate_selected : str or None
        selection_method   : str
        r_measured         : float
        r_hat              : float or None   (SA-DT only)
        utility            : float or None   (SA-DT only)
        proactive          : bool
        is_top1            : bool
        routing_correct    : bool or None    (SA-DT / SA-Only)
    """

    @abstractmethod
    def evaluate_and_act(
        self,
        reading: SensorReading,
        fault_hint: str,
        prior_state: Optional[dict],
        config: Config,
    ) -> dict:
        """
        Run one full MAPE-K decision cycle and return a result dict.

        Parameters
        ----------
        reading     : Current perceived SensorReading (from TelemetryMonitor).
        fault_hint  : Scenario label for this episode (e.g., "S1(temperature)").
        prior_state : Prior episode's true_state (used by SA-DT for DT base state).
        config      : Shared Config from KnowledgeStore.

        Returns
        -------
        dict : Decision result with at minimum 'candidate_selected'.
        """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name of the mode (for tracing and logging)."""
