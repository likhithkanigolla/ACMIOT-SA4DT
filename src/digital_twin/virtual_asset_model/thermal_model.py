"""
Thermal Model — Virtual Asset Model
=====================================

Paper reference: Section 4.2 — Virtual Asset Model; Equation 4

Responsibility (SRP): advance the TRUE physical room state by one simulation
step using the first-order Newtonian thermal equation (Eq. 4).

    T(t+1) = T(t) + (T_ambient - T(t)) / tau   +   occupancy_contribution

This models what actually happens in the physical room (the ground truth),
which may differ from what the Digital Twin believes if a model error (S2) or
behavioral drift (S5) is active.

This module does NOT classify faults, score utility, or generate candidates.

Extracted from: physical_simulator.py (original), lines 1-51 (step_physical_world).
"""

from __future__ import annotations

from src.managing_system.shared_knowledge.knowledge_store import Config


def step_physical_world(true_state: dict, candidate: str | None, config: Config) -> dict:
    """
    Advance the true room state by one episode using Eq. 4 (Newtonian cooling).

    This simulates the actual physical environment — what the sensors SHOULD
    read absent measurement errors. The DT's `simulate_candidate()` models what
    the DT PREDICTS; this function models what the physical world DOES.

    Parameters
    ----------
    true_state : dict — current true physical state, including optional keys:
        'tau_true'          : override for config.tau (S2 model error simulation)
        'c_cooling_true'    : override for config.c_cooling
        'ambient_temp'      : ambient temperature (default 22.0°C)
        'occupancy'         : number of occupants
        'actuation_multiplier' : multiplier for actuation effect (S3)
        'drop_command'      : bool — if True, actuator commands are dropped (S6)
    candidate  : str or None — adaptation command to apply to the physical world.
    config     : Config — default parameters.

    Returns
    -------
    dict : Updated true_state after one episode.

    Extracted from: physical_simulator.py lines 3-51.
    """
    updated_state = true_state.copy()

    # Ground truth parameters (may differ from DT belief under S2/S5)
    tau = true_state.get("tau_true", config.tau)
    c_cooling = true_state.get("c_cooling_true", config.c_cooling)
    ambient_temp = true_state.get("ambient_temp", 22.0)

    current_temp = updated_state.get("temperature", 25.0)
    current_co2 = updated_state.get("co2", 400.0)

    # Eq. 4: T(t+1) = T(t) + (T_ambient - T(t)) / tau
    next_temp = current_temp + (ambient_temp - current_temp) / tau
    # CO2 natural decay to ambient (~400 ppm)
    next_co2 = current_co2 + (400.0 - current_co2) / tau

    # Occupancy contribution (body heat + CO2 generation)
    occupancy = updated_state.get("occupancy", 0)
    next_temp += occupancy * 0.1
    next_co2 += occupancy * 50.0

    # Apply candidate actuation (with S3 actuation_multiplier and S6 drop_command)
    act_mult = updated_state.get("actuation_multiplier", 1.0)
    drop_cmd = updated_state.get("drop_command", False)

    if not drop_cmd and candidate:
        if candidate == "C1":   # HVAC / Fan on
            next_temp -= c_cooling * act_mult
            next_co2 -= (c_cooling * 100.0) * act_mult
        elif candidate == "C2":  # Window open
            next_temp -= (c_cooling * 0.5) * act_mult
            next_co2 -= (c_cooling * 250.0) * act_mult

    updated_state["temperature"] = next_temp
    updated_state["co2"] = next_co2

    # Clear per-step fault flags so they don't persist past one step
    updated_state.pop("actuation_multiplier", None)
    updated_state.pop("drop_command", None)

    return updated_state
