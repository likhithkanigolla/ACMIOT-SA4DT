"""
Candidate Simulator — Simulation Runtime
=========================================

Paper reference: Section 4.2 — Simulation Runtime; T_horizon = 60 s

Responsibility (SRP): create isolated virtual state forks per candidate and
execute one step of forward simulation to produce predicted post-actuation states.

The simulation runtime does NOT score utility, classify faults, or dispatch
commands. Those belong to utility_evaluator, fault_classifier, and execute.

Extracted from: evaluation_pipeline.py (original), lines 72-93 (simulate_candidate).
"""

from __future__ import annotations

from src.managing_system.shared_knowledge.knowledge_store import Config


def simulate_candidate(
    state: dict,
    candidate: str,
    config: Config,
    override_tau: float = None,
) -> dict:
    """
    Forward-simulate one MAPE-K step under candidate action `candidate`.

    Creates an isolated copy of `state`, applies Newtonian cooling / actuator
    effect, and returns the predicted post-actuation state.

    This implements the T_horizon = 60 s simulation fork described in paper §4.2:
    "creates isolated virtual state forks per candidate; executes forward simulation."

    Parameters
    ----------
    state        : dict — current perceived state {'temperature', 'co2', ...}.
    candidate    : str  — one of C1-C6.
    config       : Config — holds tau and c_cooling parameters.
    override_tau : float — if provided, overrides config.tau (used by S2/S5
                   online re-estimation via KnowledgeStore.get_adjusted_tau()).

    Returns
    -------
    dict : Predicted post-actuation state.

    Extracted from: evaluation_pipeline.py lines 72-93.
    """
    sim_state = state.copy()
    tau = override_tau if override_tau is not None else config.tau

    if candidate == "C1":  # Fan / AC On
        if sim_state.get("temperature") is not None:
            sim_state["temperature"] -= config.c_cooling * (2.0 / tau)

    elif candidate == "C2":  # Exhaust On
        if sim_state.get("co2") is not None:
            sim_state["co2"] -= config.c_cooling * (200.0 / tau)

    elif candidate == "C3":  # Recalibrate Temperature
        sim_state["temperature"] = 25.0

    elif candidate == "C4":  # Recalibrate CO2
        sim_state["co2"] = 400.0

    elif candidate == "C5":  # Defer Action (wait for better data)
        pass  # No physical change — used for S7/S8 noise bridging

    elif candidate == "C6":  # Reroute Actuator (bypass failure)
        if sim_state.get("temperature") is not None:
            sim_state["temperature"] -= config.c_cooling * (2.0 / tau)

    return sim_state
