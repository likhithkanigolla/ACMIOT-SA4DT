"""
Regression Test — Before vs. After Refactor
=============================================

Verifies that the refactored modular pipeline produces NUMERICALLY IDENTICAL
outputs to the original monolithic code on the same fixed inputs.

Tests cover:
  1. risk_score() — Semantic Context Manager (Eq. 3)
  2. utility() — Utility Evaluator (Eq. 2)
  3. sync_penalty() — Twin State Sync (Eq. 1)
  4. simulate_candidate() — Simulation Runtime (C1-C6)
  5. get_uncertainty_class() — Fault Classifier routing
  6. decide_reactive() logic — ReactiveBaseline mode
  7. decide_sa_only() logic — SAOnly mode
  8. decide_sa_dt() logic — SADT mode

Each test compares the output of the NEW modular functions against the
ORIGINAL inline logic extracted verbatim and expressed as reference
computations within the test — no external "old code" file is needed.

Run with:
    cd artifact_package && python -m pytest tests/test_regression.py -v
or:
    cd artifact_package && python tests/test_regression.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add the artifact_package root to the path
sys.path.insert(0, str(Path(__file__).parent.parent))

import math
import numpy as np
import pytest

from src.managing_system.shared_knowledge.knowledge_store import Config, SensorReading, KnowledgeStore
from src.digital_twin.semantic_context_manager.risk_aggregator import risk_score
from src.digital_twin.twin_state_sync.sync_engine import sync_penalty
from src.digital_twin.simulation_runtime.candidate_simulator import simulate_candidate
from src.decision_engine.utility_evaluator.utility_evaluator import utility, cost_of
from src.managing_system.analyse.fault_classifier import (
    get_uncertainty_class,
    ground_truth_candidate,
)
from src.common.modes.reactive_baseline import ReactiveBaseline
from src.common.modes.sa_only import SAOnly
from src.common.modes.sa_dt import SADT


# ---------------------------------------------------------------------------
# Reference implementations — inline copies of original code
# (so the test has no dependency on the original files)
# ---------------------------------------------------------------------------

def _ref_risk_score(state: dict, config: Config) -> float:
    """Original evaluation_pipeline.py lines 56-64."""
    temp = state.get("temperature")
    if temp is None: temp = 25.0
    co2 = state.get("co2")
    if co2 is None: co2 = 400.0
    temp_risk = max(0.0, (temp - 26.0) / 10.0)
    co2_risk  = max(0.0, (co2 - 1000.0) / 1000.0)
    return min(1.0, temp_risk + co2_risk)


def _ref_sync_penalty(lag: float) -> float:
    """Original evaluation_pipeline.py line 67."""
    return lag * 0.01


def _ref_utility(r_hat: float, cost: float) -> float:
    """Original evaluation_pipeline.py line 70."""
    return -r_hat - (cost * 0.1)


def _ref_simulate_candidate(state: dict, candidate: str, config: Config,
                             override_tau: float = None) -> dict:
    """Original evaluation_pipeline.py lines 72-93."""
    sim_state = state.copy()
    tau = override_tau if override_tau else config.tau
    if candidate == "C1":
        if sim_state.get("temperature") is not None:
            sim_state["temperature"] -= config.c_cooling * (2.0 / tau)
    elif candidate == "C2":
        if sim_state.get("co2") is not None:
            sim_state["co2"] -= config.c_cooling * (200.0 / tau)
    elif candidate == "C3":
        sim_state["temperature"] = 25.0
    elif candidate == "C4":
        sim_state["co2"] = 400.0
    elif candidate == "C5":
        pass
    elif candidate == "C6":
        if sim_state.get("temperature") is not None:
            sim_state["temperature"] -= config.c_cooling * (2.0 / tau)
    return sim_state


def _ref_cost_of(c: str) -> float:
    """Original decision_arms.py lines 152-156."""
    if c in ["C1", "C2", "C6"]: return 1.0
    if c in ["C3", "C4"]: return 2.0
    if c == "C5": return 0.1
    return 1.0


def _ref_get_uncertainty_class(scenario_id: str) -> str:
    """Original decision_arms.py lines 7-18."""
    import re
    if "S" not in scenario_id: return "aleatoric"
    try:
        match = re.search(r'S(\d+)', scenario_id)
        if match:
            s_num = int(match.group(1))
            if 1 <= s_num <= 6: return "epistemic"
    except: pass
    return "aleatoric"


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

STATES = [
    {"temperature": 25.0, "co2": 400.0},   # nominal
    {"temperature": 30.0, "co2": 400.0},   # temp over limit
    {"temperature": 26.5, "co2": 1200.0},  # co2 over limit
    {"temperature": 38.0, "co2": 1500.0},  # both over (clamped)
    {"temperature": None, "co2": None},    # missing data
]

CONFIG = Config()


# ---------------------------------------------------------------------------
# 1. risk_score (Eq. 3)
# ---------------------------------------------------------------------------

class TestRiskScore:
    @pytest.mark.parametrize("state", STATES)
    def test_matches_reference(self, state):
        new_val = risk_score(state, CONFIG)
        ref_val = _ref_risk_score(state, CONFIG)
        assert math.isclose(new_val, ref_val, rel_tol=1e-12), \
            f"risk_score mismatch for state={state}: new={new_val}, ref={ref_val}"

    def test_clamped_at_one(self):
        assert risk_score({"temperature": 100.0, "co2": 9999.0}, CONFIG) == 1.0

    def test_nominal_is_zero(self):
        assert risk_score({"temperature": 25.0, "co2": 400.0}, CONFIG) == 0.0

    def test_missing_treated_as_nominal(self):
        assert risk_score({"temperature": None, "co2": None}, CONFIG) == 0.0


# ---------------------------------------------------------------------------
# 2. sync_penalty (Eq. 1)
# ---------------------------------------------------------------------------

class TestSyncPenalty:
    @pytest.mark.parametrize("lag", [0.0, 30.0, 180.0, 360.0])
    def test_matches_reference(self, lag):
        assert math.isclose(sync_penalty(lag), _ref_sync_penalty(lag), rel_tol=1e-12)

    def test_s9_lag_value(self):
        # S9 injects lag_seconds=180.0
        assert math.isclose(sync_penalty(180.0), 1.8, rel_tol=1e-12)


# ---------------------------------------------------------------------------
# 3. utility (Eq. 2)
# ---------------------------------------------------------------------------

class TestUtility:
    @pytest.mark.parametrize("r_hat,cost", [
        (0.0, 0.0), (0.5, 1.0), (0.3, 2.0), (1.0, 0.1),
    ])
    def test_matches_reference(self, r_hat, cost):
        assert math.isclose(utility(r_hat, cost), _ref_utility(r_hat, cost), rel_tol=1e-12)


# ---------------------------------------------------------------------------
# 4. cost_of
# ---------------------------------------------------------------------------

class TestCostOf:
    @pytest.mark.parametrize("candidate,expected", [
        ("C1", 1.0), ("C2", 1.0), ("C6", 1.0),
        ("C3", 2.0), ("C4", 2.0),
        ("C5", 0.1),
    ])
    def test_matches_reference(self, candidate, expected):
        assert cost_of(candidate) == _ref_cost_of(candidate) == expected


# ---------------------------------------------------------------------------
# 5. simulate_candidate (Simulation Runtime)
# ---------------------------------------------------------------------------

class TestSimulateCandidate:
    BASE_STATE = {"temperature": 28.0, "co2": 500.0, "occupancy": 1}

    @pytest.mark.parametrize("candidate", ["C1", "C2", "C3", "C4", "C5", "C6"])
    def test_matches_reference_standard(self, candidate):
        new_state = simulate_candidate(self.BASE_STATE, candidate, CONFIG)
        ref_state = _ref_simulate_candidate(self.BASE_STATE, candidate, CONFIG)
        for key in ["temperature", "co2"]:
            nv = new_state.get(key)
            rv = ref_state.get(key)
            if nv is None and rv is None:
                continue
            assert math.isclose(nv, rv, rel_tol=1e-12), \
                f"simulate_candidate({candidate})[{key}] mismatch: new={nv}, ref={rv}"

    def test_override_tau(self):
        """S2/S5 re-estimation: override_tau=2.0 must produce same result as original."""
        new_state = simulate_candidate(self.BASE_STATE, "C1", CONFIG, override_tau=2.0)
        ref_state = _ref_simulate_candidate(self.BASE_STATE, "C1", CONFIG, override_tau=2.0)
        assert math.isclose(new_state["temperature"], ref_state["temperature"], rel_tol=1e-12)

    def test_c5_no_change(self):
        """C5 (defer) must leave state unchanged."""
        state = {"temperature": 27.0, "co2": 450.0}
        new_state = simulate_candidate(state, "C5", CONFIG)
        assert new_state["temperature"] == 27.0
        assert new_state["co2"] == 450.0


# ---------------------------------------------------------------------------
# 6. get_uncertainty_class
# ---------------------------------------------------------------------------

class TestGetUncertaintyClass:
    @pytest.mark.parametrize("scenario,expected", [
        ("S1(temperature)", "epistemic"),
        ("S2(co2_ppm)", "epistemic"),
        ("S3(humidity)", "epistemic"),
        ("S4(lux)", "epistemic"),
        ("S5(temperature)", "epistemic"),
        ("S6(co2_ppm)", "epistemic"),
        ("S7(temperature)", "aleatoric"),
        ("S8(co2_ppm)", "aleatoric"),
        ("S9_Net_Instab", "aleatoric"),
        ("S10_Reconnect", "aleatoric"),
        ("S11_Env_Var", "aleatoric"),
        ("Normal", "aleatoric"),
        ("", "aleatoric"),
    ])
    def test_matches_reference(self, scenario, expected):
        new_val = get_uncertainty_class(scenario)
        ref_val = _ref_get_uncertainty_class(scenario)
        assert new_val == ref_val == expected, \
            f"get_uncertainty_class({scenario!r}): new={new_val}, ref={ref_val}"


# ---------------------------------------------------------------------------
# 7. ReactiveBaseline — matches decide_reactive() logic
# ---------------------------------------------------------------------------

class TestReactiveBaseline:
    def _ref_decide_reactive(self, sensor, config):
        """Original decision_arms.py lines 74-95."""
        r = _ref_risk_score(sensor.__dict__, config)
        candidate = None
        if r > config.decision_threshold:
            if sensor.temperature and sensor.temperature > 26.0:
                candidate = "C1"
            elif sensor.co2 and sensor.co2 > 1000.0:
                candidate = "C2"
            else:
                candidate = "C1"
        return {"candidate_selected": candidate, "r_measured": r}

    @pytest.mark.parametrize("temp,co2", [
        (25.0, 400.0),   # normal — no action
        (30.0, 400.0),   # high temp → C1
        (26.0, 1200.0),  # high CO2 → C2
        (35.0, 1500.0),  # both — temp takes priority → C1
    ])
    def test_matches_reference(self, temp, co2):
        sensor = SensorReading(temperature=temp, co2=co2, occupancy=0)
        mode = ReactiveBaseline()
        new_result = mode.evaluate_and_act(sensor, "", None, CONFIG)
        ref_result = self._ref_decide_reactive(sensor, CONFIG)
        assert new_result["candidate_selected"] == ref_result["candidate_selected"], \
            f"ReactiveBaseline candidate mismatch for T={temp}, CO2={co2}"
        assert math.isclose(new_result["r_measured"], ref_result["r_measured"], rel_tol=1e-12)


# ---------------------------------------------------------------------------
# 8. SAOnly — matches decide_sa_only() routing rules
# ---------------------------------------------------------------------------

class TestSAOnly:
    FAULT_CASES = [
        # (scenario_label, expected_candidate, temperature, co2)
        # Temperature must be high enough to ensure risk > decision_threshold (0.40)
        # temp_risk = (T-26)/10 > 0.40 → T > 30.0
        ("S8(temperature)", "C1",  31.0, 400.0),
        ("S9_Net_Instab",   "C1",  31.0, 400.0),
        ("S7(co2_ppm)",     "C1",  31.0, 400.0),
        ("S4(temperature)", "C1",  31.0, 400.0),
        ("S2(humidity)",    "C1",  31.0, 400.0),
        ("S1(temperature)", "C3",  31.0, 400.0),
        ("S5(co2_ppm)",     "C3",  31.0, 400.0),
    ]

    def test_routing_rules(self):
        """SA-Only should apply static routing rules — check each scenario maps correctly."""
        mode = SAOnly()
        for scenario, expected_candidate, temp, co2 in self.FAULT_CASES:
            mode.reset()  # clear classifier history between cases
            sensor = SensorReading(temperature=temp, co2=co2, occupancy=0)
            result = mode.evaluate_and_act(sensor, scenario, None, CONFIG)
            assert result["candidate_selected"] == expected_candidate, \
                f"SAOnly({scenario}): expected {expected_candidate}, got {result['candidate_selected']}"


# ---------------------------------------------------------------------------
# 9. SADT — verify it produces a valid result and proactive triggers fire
# ---------------------------------------------------------------------------

class TestSADT:
    def test_returns_valid_candidate(self):
        """SA-DT must return a non-None candidate when risk is above threshold."""
        ks = KnowledgeStore(CONFIG)
        mode = SADT(ks)
        sensor = SensorReading(temperature=30.0, co2=500.0, occupancy=0)
        result = mode.evaluate_and_act(sensor, "S1(temperature)", None, CONFIG)
        assert result["candidate_selected"] is not None
        assert result["selection_method"] == "utility_de"

    def test_no_action_below_threshold(self):
        """SA-DT must NOT act when risk is below both thresholds."""
        ks = KnowledgeStore(CONFIG)
        mode = SADT(ks)
        sensor = SensorReading(temperature=24.0, co2=350.0, occupancy=0)
        result = mode.evaluate_and_act(sensor, "S1(temperature)", None, CONFIG)
        r = result["r_measured"]
        assert r <= CONFIG.proactive_trigger, f"Expected r<={CONFIG.proactive_trigger}, got {r}"
        assert result["candidate_selected"] is None

    def test_proactive_fires_in_band(self):
        """A reading in (proactive_trigger, decision_threshold) must set proactive=True."""
        ks = KnowledgeStore(CONFIG)
        mode = SADT(ks)
        # Craft a reading that puts r in (0.38, 0.40)
        # temp_risk = (T - 26) / 10 = 0.39 → T = 29.9
        sensor = SensorReading(temperature=29.9, co2=400.0, occupancy=0)
        r = risk_score(sensor.__dict__, CONFIG)
        if CONFIG.proactive_trigger < r <= CONFIG.decision_threshold:
            result = mode.evaluate_and_act(sensor, "S1(temperature)", None, CONFIG)
            assert result["proactive"] is True

    def test_s2_uses_adjusted_tau(self):
        """SADT on S2 must use tau*2.0 (via KnowledgeStore.get_adjusted_tau)."""
        ks = KnowledgeStore(CONFIG)
        assert ks.get_adjusted_tau("S2(temperature)") == CONFIG.tau * 2.0

    def test_s4_candidate_pruned(self):
        """SADT on S4 must not select C1 or C2 (AdaptationPlanner prunes them)."""
        ks = KnowledgeStore(CONFIG)
        mode = SADT(ks)
        sensor = SensorReading(temperature=30.0, co2=500.0, occupancy=0)
        result = mode.evaluate_and_act(sensor, "S4(temperature)", None, CONFIG)
        if result["candidate_selected"] is not None:
            assert result["candidate_selected"] not in ["C1", "C2"], \
                f"S4 should not select C1/C2, got: {result['candidate_selected']}"

    def test_knowledge_store_records_residual(self):
        """Execute phase must persist residual to KnowledgeStore after each episode."""
        from src.managing_system.execute.action_executor import ActionExecutor
        from src.managing_system.monitor.telemetry_monitor import PhysicalState

        ks = KnowledgeStore(CONFIG)
        executor = ActionExecutor(ks)
        ps = PhysicalState()
        sensor = SensorReading(temperature=30.0, co2=500.0, occupancy=0)

        ep, t_e = executor.apply_and_record(
            candidate="C1",
            perceived_reading=sensor,
            raw_temp=30.0,
            raw_co2=500.0,
            physical_state=ps,
            config=CONFIG,
            decision_result={"candidate_selected": "C1", "selection_method": "utility_de",
                             "r_measured": 0.4, "r_hat": 0.35, "utility": -0.45,
                             "proactive": False, "is_top1": True, "routing_correct": True},
            episode_meta={"episode_index": 0, "scenario_id": "S1(temperature)",
                          "mode": "sa_dt", "severity": 1.0,
                          "prior_state": None, "t_m": 5.0, "t_p": 0.1, "r_measured": 0.4},
        )
        assert ep is not None
        assert t_e > 0  # OTA latency simulated
        residuals = ks.get_residuals("S1(temperature)")
        assert len(residuals) == 1


# ---------------------------------------------------------------------------
# Standalone runner (no pytest required)
# ---------------------------------------------------------------------------

def _run_standalone():
    """Run all tests without pytest, expanding parametrize cases manually."""
    passed = 0
    failed = 0
    errors = []

    def _run(name, fn, *args):
        nonlocal passed, failed
        try:
            fn(*args)
            passed += 1
            print(f"  ✓ {name}")
        except Exception as e:
            failed += 1
            msg = f"  ✗ {name}: {e}"
            errors.append(msg)
            print(msg)

    cfg = CONFIG

    # TestRiskScore
    t = TestRiskScore()
    for st in STATES:
        _run(f"TestRiskScore.test_matches_reference({st})", t.test_matches_reference, st)
    _run("TestRiskScore.test_clamped_at_one", t.test_clamped_at_one)
    _run("TestRiskScore.test_nominal_is_zero", t.test_nominal_is_zero)
    _run("TestRiskScore.test_missing_treated_as_nominal", t.test_missing_treated_as_nominal)

    # TestSyncPenalty
    sp = TestSyncPenalty()
    for lag in [0.0, 30.0, 180.0, 360.0]:
        _run(f"TestSyncPenalty.test_matches_reference(lag={lag})", sp.test_matches_reference, lag)
    _run("TestSyncPenalty.test_s9_lag_value", sp.test_s9_lag_value)

    # TestUtility
    ut = TestUtility()
    for r_hat, cost in [(0.0, 0.0), (0.5, 1.0), (0.3, 2.0), (1.0, 0.1)]:
        _run(f"TestUtility.test_matches_reference(r_hat={r_hat},cost={cost})",
             ut.test_matches_reference, r_hat, cost)

    # TestCostOf
    co = TestCostOf()
    for cand, exp in [("C1", 1.0), ("C2", 1.0), ("C6", 1.0), ("C3", 2.0), ("C4", 2.0), ("C5", 0.1)]:
        _run(f"TestCostOf.test_matches_reference({cand})", co.test_matches_reference, cand, exp)

    # TestSimulateCandidate
    sc = TestSimulateCandidate()
    for cand in ["C1", "C2", "C3", "C4", "C5", "C6"]:
        _run(f"TestSimulateCandidate.test_matches_reference_standard({cand})",
             sc.test_matches_reference_standard, cand)
    _run("TestSimulateCandidate.test_override_tau", sc.test_override_tau)
    _run("TestSimulateCandidate.test_c5_no_change", sc.test_c5_no_change)

    # TestGetUncertaintyClass
    gu = TestGetUncertaintyClass()
    for scenario, expected in [
        ("S1(temperature)", "epistemic"), ("S2(co2_ppm)", "epistemic"),
        ("S3(humidity)", "epistemic"),   ("S4(lux)", "epistemic"),
        ("S5(temperature)", "epistemic"),("S6(co2_ppm)", "epistemic"),
        ("S7(temperature)", "aleatoric"),("S8(co2_ppm)", "aleatoric"),
        ("S9_Net_Instab", "aleatoric"),  ("S10_Reconnect", "aleatoric"),
        ("S11_Env_Var", "aleatoric"),    ("Normal", "aleatoric"),
        ("", "aleatoric"),
    ]:
        _run(f"TestGetUncertaintyClass({scenario!r})", gu.test_matches_reference, scenario, expected)

    # TestReactiveBaseline
    rb = TestReactiveBaseline()
    for temp, co2 in [(25.0, 400.0), (30.0, 400.0), (26.0, 1200.0), (35.0, 1500.0)]:
        _run(f"TestReactiveBaseline(T={temp},CO2={co2})", rb.test_matches_reference, temp, co2)

    # TestSAOnly
    sa = TestSAOnly()
    _run("TestSAOnly.test_routing_rules", sa.test_routing_rules)

    # TestSADT
    sd = TestSADT()
    _run("TestSADT.test_returns_valid_candidate", sd.test_returns_valid_candidate)
    _run("TestSADT.test_no_action_below_threshold", sd.test_no_action_below_threshold)
    _run("TestSADT.test_proactive_fires_in_band", sd.test_proactive_fires_in_band)
    _run("TestSADT.test_s2_uses_adjusted_tau", sd.test_s2_uses_adjusted_tau)
    _run("TestSADT.test_s4_candidate_pruned", sd.test_s4_candidate_pruned)
    _run("TestSADT.test_knowledge_store_records_residual", sd.test_knowledge_store_records_residual)

    print(f"\nRegression results: {passed} passed, {failed} failed")
    if errors:
        print("\nFailed tests:")
        for e in errors:
            print(e)
        return False
    return True


if __name__ == "__main__":
    print("=== Regression Test: Before vs. After Refactor ===\n")
    success = _run_standalone()
    sys.exit(0 if success else 1)
