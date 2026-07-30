"""
Action Executor
===============

Paper reference: Section 4.4 — Execute

Responsibility (SRP): apply the selected candidate's physical effect to the
simulated environment state, receive the OTA latency estimate from the Command
Orchestrator, and write the episode residual back to the Shared Knowledge store.

This module does NOT classify faults, score utility, or generate candidates.
Those belong to fault_classifier, utility_evaluator, and adaptation_planner.

Extracted from: experiment_runner.py (original), lines 92-121 (candidate
application → physical deltas) and lines 85-88 (OTA latency simulation,
which is now delegated to the CommandOrchestrator import).
"""

from __future__ import annotations

from src.managing_system.shared_knowledge.knowledge_store import (
    Config,
    Episode,
    KnowledgeStore,
    SensorReading,
)
from src.managing_system.monitor.telemetry_monitor import PhysicalState
from src.digital_twin.command_orchestrator.ota_dispatcher import OTADispatcher


# ---------------------------------------------------------------------------
# Action Executor
# ---------------------------------------------------------------------------

class ActionExecutor:
    """
    Paper §4.4 — Execute: "coordinates OTA dispatch; records T_E; conveys
    residuals back to Shared Knowledge."

    Applies each candidate's physical effect as a delta on `PhysicalState`
    (persistent across episodes within a trace), then stores the episode in
    the KnowledgeStore so future utility evaluations can be parameterized.

    The OTA dispatch simulation is delegated to OTADispatcher (Command
    Orchestrator) — see docs/missing_components.md §2.2 for the honest
    accounting of what OTA latency represents vs real hardware.

    Extracted from: experiment_runner.py lines 92-121 (physical delta
    application) and lines 85-88 (OTA latency delegation).
    """

    # Cost weights for trial summary computation (experiment_runner.py L262)
    _COST_MAP: dict[str, float] = {
        "C1": 1.0,
        "C2": 1.0,
        "C6": 1.0,
        "C3": 2.0,
        "C4": 2.0,
        "C5": 0.1,
    }

    def __init__(self, knowledge_store: KnowledgeStore):
        self._store = knowledge_store
        self._dispatcher = OTADispatcher()

    def apply_and_record(
        self,
        candidate: str | None,
        perceived_reading: SensorReading,
        raw_temp: float | None,
        raw_co2: float | None,
        physical_state: PhysicalState,
        config: Config,
        decision_result: dict,
        episode_meta: dict,
    ) -> tuple[Episode, float]:
        """
        Apply the selected candidate to physical state, simulate OTA dispatch,
        build the Episode record, and persist residual to KnowledgeStore.

        Parameters
        ----------
        candidate        : Selected adaptation (e.g., "C1") or None.
        perceived_reading: SensorReading for this episode.
        raw_temp, raw_co2: Raw sensor values before deltas (used by C3/C4 recal).
        physical_state   : Mutable physical environment state (modified in place).
        config           : Shared Config.
        decision_result  : Dict from the AdaptationMode with utility/r_hat/etc.
        episode_meta     : Dict with keys: episode_index, scenario_id, mode,
                           severity, prior_state, t_m, r_measured.

        Returns
        -------
        Episode : Complete episode record.
        float   : OTA execution latency T_E in milliseconds.
        """
        # Apply candidate to physical environment (Extracted from lines 92-117)
        self._apply_candidate(
            candidate, perceived_reading, raw_temp, raw_co2, physical_state, config
        )

        # Simulate OTA dispatch and capture T_E (Command Orchestrator)
        t_e = self._dispatcher.dispatch(candidate)

        # Compute risk drift (if DT prediction is available)
        from src.digital_twin.semantic_context_manager.risk_aggregator import risk_score
        r_measured = risk_score(perceived_reading.__dict__, config)
        r_hat = decision_result.get("r_hat")
        risk_drift = abs(r_hat - r_measured) if r_hat is not None else None

        ep = Episode(
            episode_index=episode_meta["episode_index"],
            scenario_id=episode_meta["scenario_id"],
            mode=episode_meta["mode"],
            severity=episode_meta.get("severity", 1.0),
            true_state=episode_meta.get("prior_state", perceived_reading.__dict__),
            perceived_state=perceived_reading.__dict__,
            candidate_selected=candidate,
            selection_method=decision_result.get("selection_method", ""),
            r_measured=r_measured,
            r_hat=r_hat,
            utility=decision_result.get("utility"),
            proactive=decision_result.get("proactive", False),
            is_top1=decision_result.get("is_top1", False),
            risk_drift=risk_drift,
            routing_correct=decision_result.get("routing_correct"),
            proactive_lead_episodes=0,
            t_m=episode_meta.get("t_m", 0.0),
            t_p=episode_meta.get("t_p", 0.0),
            t_e=t_e,
            lag_seconds=perceived_reading.lag_seconds,
        )

        # Persist residual to Shared Knowledge (paper §4.4 Execute feedback)
        self._store.record_residual(ep)

        return ep, t_e

    @staticmethod
    def cost_of(candidate: str | None) -> float:
        """
        Return the actuation cost for a candidate.
        Extracted from: decision_arms.py lines 152-156.
        """
        if candidate is None:
            return 0.0
        return ActionExecutor._COST_MAP.get(candidate, 1.0)

    # ------------------------------------------------------------------
    # Private: physical state mutation (extracted from lines 92-117)
    # ------------------------------------------------------------------

    @staticmethod
    def _apply_candidate(
        candidate: str | None,
        perceived_reading: SensorReading,
        raw_temp: float | None,
        raw_co2: float | None,
        state: PhysicalState,
        config: Config,
    ) -> None:
        """
        Modify `state` in-place based on the selected candidate.

        All logic extracted verbatim from experiment_runner.py lines 93-117
        (candidate == "C1" … elif candidate == "C6" branches).
        """
        if candidate == "C1":
            state.temp_delta -= config.c_cooling
            state.co2_delta -= config.c_cooling * 100.0
        elif candidate == "C2":
            state.temp_delta -= config.c_cooling * 0.5
            state.co2_delta -= config.c_cooling * 250.0
        elif candidate == "C3":
            # C3 = Recalibrate Temperature permanently
            if raw_temp is not None:
                state.c3_temp_offset = 25.0 - (raw_temp + state.temp_delta)
            else:
                perceived_reading.temperature = 25.0
        elif candidate == "C4":
            # C4 = Recalibrate CO2 permanently
            if raw_co2 is not None:
                state.c3_co2_offset = 400.0 - (raw_co2 + state.co2_delta)
            else:
                perceived_reading.co2 = 400.0
        elif candidate == "C5":
            # C5 = Defer Action (no physical effect)
            pass
        elif candidate == "C6":
            # C6 = Reroute Actuator (Bypass failed C1)
            state.temp_delta -= config.c_cooling
            state.co2_delta -= config.c_cooling * 100.0
        # candidate == None → no action
