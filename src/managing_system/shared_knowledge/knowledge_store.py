"""
Shared Knowledge Store
======================

Paper reference: Section 4.4 — Managing System (Shared Knowledge)

This is the SINGLE canonical module that defines all shared data structures
(Config, SensorReading, Episode) and the KnowledgeStore that accumulates
episode-by-episode residuals.

ALL other components (Monitor, Analyse, Plan, Execute, Digital Twin modules,
Decision Engine modules) import from this module. Nothing is copied.

Design note — honest accounting (see docs/missing_components.md §1.4):
  The paper describes fully online parameter refinement (continuous tau/c
  updates from physical residuals). What is implemented here is a minimal
  faithful skeleton: a KnowledgeStore that accumulates residuals and exposes
  a `get_adjusted_tau()` helper that applies the one hard-coded multiplier
  (tau * 2.0 for S2/S5) that existed in the original decide_sa_dt() code.
  The accumulation dict is present and wired, so extending to true online
  learning requires only adding an update rule to `record_residual()`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Dict, List


# ---------------------------------------------------------------------------
# Core configuration (paper §5, Table 5 — Parameter calibration)
# ---------------------------------------------------------------------------

@dataclass
class Config:
    """
    All tuneable parameters for the SA-DT evaluation pipeline.

    Paper §5 parameter notes (see docs/missing_components.md §3 for
    discrepancies between paper values and these simulation-unit values):
      tau             = 1.0   (paper: 300 s; code uses normalized episode units)
      c_cooling       = 0.5   (paper: 0.04 degC/s; code uses normalized units)
      decision_threshold = 0.40  (paper: implied ~0.40) [MATCH]
      proactive_trigger  = 0.38  (paper: 95% of nominal safety limit)
      recovery_threshold = 0.10  (paper: r < 0.2 for 3 episodes) [DIFFERS]
    """
    tau: float = 1.0
    c_cooling: float = 0.5
    decision_threshold: float = 0.40
    proactive_trigger: float = 0.38
    recovery_threshold: float = 0.10
    recovery_persistence: int = 3
    injection_duration_s: int = 300
    max_drift_degrees: float = 10.0
    noise_std: float = 2.0
    max_gap_episodes: int = 10


# ---------------------------------------------------------------------------
# Runtime data structures
# ---------------------------------------------------------------------------

@dataclass
class SensorReading:
    """
    One telemetry snapshot from the managed room environment.

    Paper §4.4 — Monitor: "ingests streaming telemetry, appends quality /
    staleness tags, and records T_M."
    """
    temperature: float = 25.0
    co2: float = 400.0
    occupancy: int = 0
    timestamp: float = 0.0
    lag_seconds: float = 0.0   # injected for S9 (network instability)


@dataclass
class Episode:
    """
    One MAPE-K decision cycle's full record — fed to the Execute phase and
    persisted in KnowledgeStore for residual learning.

    Paper §4.4 — Execute: "conveys measured physical outcome residuals back to
    Shared Knowledge to refine adaptive models."
    """
    episode_index: int
    scenario_id: str
    mode: str
    severity: float
    true_state: dict
    perceived_state: dict
    candidate_selected: Optional[str]
    selection_method: str
    r_measured: float
    r_hat: Optional[float]
    utility: Optional[float]
    proactive: bool
    is_top1: bool
    episodes_to_recover: Optional[int] = None
    episode_success: bool = False

    # Extended metrics (Reviewer 3 additions)
    risk_drift: Optional[float] = None
    routing_correct: Optional[bool] = None
    proactive_lead_episodes: int = 0
    t_m: float = 0.0   # Monitoring latency (ms)
    t_p: float = 0.0   # DT + Decision latency (ms)
    t_e: float = 0.0   # OTA Actuation latency (ms)
    lag_seconds: float = 0.0


# ---------------------------------------------------------------------------
# Knowledge Store
# ---------------------------------------------------------------------------

class KnowledgeStore:
    """
    Accumulates episode-level residuals and exposes adjusted parameters for
    future utility evaluations.

    Paper §4.4: "accumulates episode-by-episode physical outcome residuals …
    and parameterizes future utility evaluations."

    Current implementation status (see docs/missing_components.md §1.4):
      - Residuals dict is accumulated per scenario.
      - `get_adjusted_tau()` applies the S2/S5 tau multiplier that was
        previously hard-coded inline in decide_sa_dt().
      - True online EMA-based learning is marked as a TODO without
        altering any existing numerical behavior.

    Usage
    -----
    store = KnowledgeStore(config)
    store.record_residual(episode)
    tau = store.get_adjusted_tau(scenario_id)
    """

    def __init__(self, config: Config):
        self.config = config
        # Maps scenario_id -> list of (r_measured, r_hat) pairs
        self._residuals: Dict[str, List[tuple]] = {}

    def record_residual(self, episode: Episode) -> None:
        """
        Persist the residual between predicted and measured risk for this
        episode so future utility evaluations can be parameterized.

        TODO (future work): apply an exponential moving average update rule:
            tau_new = (1-alpha) * tau_old + alpha * tau_estimated_from_residual
        Currently the residual is stored but no online update is applied —
        this faithfully matches what the original code implemented.
        """
        sid = episode.scenario_id
        if sid not in self._residuals:
            self._residuals[sid] = []
        if episode.r_hat is not None:
            self._residuals[sid].append((episode.r_measured, episode.r_hat))

    def get_adjusted_tau(self, scenario_id: str) -> float:
        """
        Returns the tau value to use for DT simulation for this scenario.

        For S2 (Model Error) and S5 (Behavioral Drift), the thermal model
        is known to under-estimate the actual cooling time constant, so tau
        is doubled — this was previously hard-coded inline in decide_sa_dt().

        Paper §4.2: "online tau re-estimation" for S2/S5.
        """
        if "S2" in scenario_id or "S5" in scenario_id:
            return self.config.tau * 2.0
        return self.config.tau

    def get_residuals(self, scenario_id: str) -> list:
        """Return all stored (r_measured, r_hat) pairs for a scenario."""
        return self._residuals.get(scenario_id, [])
