# Verification Checklist

Paper: "Digital Twins for Uncertainty Mitigation in Self-Adaptive Smart City IoT Systems"

---

## 1. Fault Scenarios (S1-S11)

| Scenario | Description | Class | Injection Code | Status |
|----------|-------------|-------|----------------|--------|
| S1 | Sensor Drift | Epistemic | `make_test_data.py` L100-111 | PRESENT |
| S2 | Model Error | Epistemic | `make_test_data.py` L113-124 | PRESENT |
| S3 | Actuation Deviation | Epistemic | `make_test_data.py` L126-137 | PRESENT |
| S4 | Stuck Sensor | Epistemic | `make_test_data.py` L139-150 | PRESENT |
| S5 | Behavioral Drift | Epistemic | `make_test_data.py` L152-164 | PRESENT |
| S6 | Actuator Failure | Epistemic | `make_test_data.py` L166-176 | PRESENT |
| S7 | Measurement Noise | Aleatoric | `make_test_data.py` L178-191 | PRESENT |
| S8 | Packet Loss | Aleatoric | `make_test_data.py` L207-241 | PRESENT |
| S9 | Network Instability | Aleatoric | `make_test_data.py` L244-260 | PRESENT |
| S10 | Reconnection Events | Aleatoric | `make_test_data.py` L224-234 (linked to S8) | PRESENT |
| S11 | Environmental Variability | Aleatoric | `make_test_data.py` L193-205 | PRESENT |

NOTE: S12 (Clock Sync Failure) is also injected (L262-271) but is NOT in the paper taxonomy
(Table 1). It is labelled "Clock_Sync_Fail" in outputs and may appear in raw logs.

Result: [x] All 11 fault scenarios have corresponding injection logic

---

## 2. Execution Modes

| Mode | Function | File | Independently Runnable? |
|------|----------|------|------------------------|
| Reactive | `decide_reactive()` | `decision_arms.py` L74-95 | YES - via `experiment_runner.py --csv-path` |
| SA-Only | `decide_sa_only()` | `decision_arms.py` L97-150 | YES - same runner, mode="sa_only" |
| SA-DT | `decide_sa_dt()` | `decision_arms.py` L158-282 | YES - same runner, mode="sa_dt" |

All three modes are iterated in `run_all_traces()` (`experiment_runner.py` L207-212).

Result: [x] All 3 execution modes are implemented and runnable independently

---

## 3. Equations from Paper

| Equation | Description | File | Function/Lines | Status |
|----------|-------------|------|----------------|--------|
| Eq. 1: r_hat'(a) = r_hat(a) * (1 - min(gamma_max, d/d_max)) | Sync lag confidence penalty | `evaluation_pipeline.py` L66-67; `decision_arms.py` L209-212 | `sync_penalty(lag)`; applied inline for S9 | PARTIAL - lag*0.01 without gamma_max cap |
| Eq. 2: U(a) = alpha*delta_r(a) - (1-alpha)*c(a) | Utility scoring | `evaluation_pipeline.py` L69-70; `decision_arms.py` L152-156 | `utility(r_hat, cost)` and `cost_of(c)` | PARTIAL - numerically equivalent but alpha not explicit |
| Eq. 3: r = max(0, 1/M * sum(s_i)) | Composite risk index | `evaluation_pipeline.py` L56-64 | `risk_score(state, config)` | PRESENT - temperature and CO2 deviations normalized |
| Eq. 4: T_hat_{t+k} = T_out + (T_t - T_out)*exp(-k/tau) - c*u*k | Thermal model for forward simulation | `physical_simulator.py` L19-24; `evaluation_pipeline.py` L72-93 | `step_physical_world()` and `simulate_candidate()` | PRESENT - first-order cooling implemented; tau/c values differ from paper calibration |
| Eq. 5: Delta_% = (M_baseline - M_mode) / M_baseline * 100 | Percentage savings formula | `analysis.py` L101-104 | `calc_savings()` | PRESENT |

Result: [/] Equations 1-5 are implemented (Eq.1 and Eq.2 partially - missing gamma_max cap and explicit alpha parameter)

---

## 4. Configurable Parameters vs. Section 6 Values

| Parameter | Paper (Sec.6) | Code | Exact Match? |
|-----------|--------------|------|--------------|
| tau = 300s | 300 s | Config.tau = 1.0 | NO - units differ |
| c = 0.04 degC/s | 0.04 | Config.c_cooling = 0.5 | NO - values differ |
| T_horizon = 60s | 60 s | Not explicitly set | NO - implicit only |
| T_forecast = 55s | 55 s | Not present | NO - absent |
| theta_proactive = 0.95 | 0.95 | Config.proactive_trigger = 0.38 | NO - scale differs |
| alpha = 0.9 | 0.9 | utility(): cost*0.1 implicit | YES - numerically |
| d_max = 180s | 180 s | lag_seconds = 180.0 for S9 | YES |
| gamma_max = 0.35 | 0.35 | No cap applied | NO - missing |
| recovery threshold | r<0.2 | Config.recovery_threshold = 0.10 | NO - 0.10 vs 0.20 |
| decision threshold | ~0.40 | Config.decision_threshold = 0.40 | YES |

Result: [ ] Parameters do NOT exactly match Section 6 values (tau, c, T_horizon, T_forecast, theta_proactive, gamma_max, recovery threshold differ)

---

## 5. Multi-Scale Trial Support (4 scales x 5 seeds = 20 runs/condition)

- `run_multi_scale.py` L8-9: `scales = [1, 7, 15, 30]` and `trials = 5`
- Outer loop: `for days in scales: for trial in range(trials):`
- Total per mode: 4 * 5 = 20 runs
- NOTE: Random seed is NOT explicitly passed to each trial. `make_test_data.py` L69 removed
  the fixed seed: `rng = np.random.default_rng()` (unseeded). Reproducibility requires
  adding explicit seed control via `--seed` argument.

Result: [x] 4 temporal scales x 5 trials = 20 runs/condition is supported structurally
Result: [ ] Explicit per-trial seeding is NOT implemented (trials are random, not seeded)

---

## 6. Metrics Computation

| Metric | Formula | Implementation | File + Lines |
|--------|---------|----------------|--------------|
| SR (Success Rate) | proportion of episodes reaching stable recovery | `episode_success` flag; mean per group | `experiment_runner.py` L162-171; `analysis.py` L287 |
| TTR (Time-to-Recover) | avg episodes from anomaly onset to confirmed recovery | `episodes_to_recover` counter | `experiment_runner.py` L127-133; `analysis.py` L291 |
| IRE (Integrated Recovery Error) | sum(r_t) from t0 to t_rec | `integrated_risk = np.sum([e.r_measured])` | `experiment_runner.py` L260; `analysis.py` L289 |
| Cost | mean normalized actuation cost per action | `mean_cost` = total_cost/n_episodes | `experiment_runner.py` L262-263; `analysis.py` L293 |

Result: [x] All 4 metrics computed matching their paper formulas

---

## 7. Statistical Tests

- Wilcoxon signed-rank: `analysis.py` -> `wilcoxon_test()` (L33-53) using scipy.stats.wilcoxon
- Rank-biserial effect size: `effect_r = 1 - (2*W) / (n*(n+1)/2)` (L49-50)
- Applied to 3 metrics (episode_success, integrated_risk, episodes_to_recover_valid)
  for both SA-DT vs Reactive and SA-DT vs SA-Only comparisons (L123-145)

Result: [x] Statistical test (Wilcoxon + rank-biserial) implementation exists

---

## 8. Latency Instrumentation

| Component | Variable | Capture Method | File + Lines |
|-----------|----------|----------------|--------------|
| T_M (Monitoring) | ep.t_m | `monitoring_latency = 5.0 + np.random.normal(0,1.0)` | `experiment_runner.py` L71, L152 |
| T_P (Processing/Decision) | ep.t_p | `time.perf_counter()` around decision call | `experiment_runner.py` L74-83 |
| T_E (Execution/OTA) | ep.t_e | `ota_latency = 50.0 + np.random.normal(0,5.0)` | `experiment_runner.py` L86-88, L154 |
| T_E-conditioned | T_E_cond | Filtered to episodes with physical actuation | `analysis.py` L229-231 |

Result: [x] Latency instrumentation for T_M, T_P, T_E, T_E-conditioned is captured

---

## 9. Output Artifacts Reproducing Paper Tables and Figures

| Artifact | File | Status |
|----------|------|--------|
| Table 2 (Main Results) | `results/tables/paper_tables.tex` -> Table 1 in LaTeX | PRESENT |
| Table 3 (Statistical Tests) | `results/tables/paper_tables.tex` -> Table 2 in LaTeX | PRESENT |
| Table 4 (Latency) | `results/tables/paper_tables.tex` -> Table 3 in LaTeX | PRESENT |
| Multi-scale Table | `results/tables/paper_tables.tex` -> Table 4 in LaTeX | PRESENT |
| Figure 2 (Success Rate) | `results/figures/fig_success_rate.pdf/.png` | PRESENT |
| Figure 3 (IRE) | `results/figures/fig_integrated_error.pdf/.png` | PRESENT |
| Figure 4 (Recovery Time) | `results/figures/fig_recovery_time.pdf/.png` | PRESENT |
| Figure 5 (Latency Breakdown) | `results/figures/fig_latency_breakdown.pdf/.png` | PRESENT |
| Multi-scale Figure | `results/figures/fig_multi_scale_trend.pdf/.png` | PRESENT |
| Raw data | `results/metrics/trial_summary.csv`, `results/metrics/per_scenario_breakdown.csv` | PRESENT |
| Statistical results | `results/metrics/statistical_tests.csv` | PRESENT |
| Confidence intervals | `results/metrics/confidence_intervals.csv` | PRESENT |

Result: [x] Output artifacts reproduce Tables 2-4 and Figures 2-5

---

## Summary

| Check | Status |
|-------|--------|
| All 11 fault scenarios have injection logic | PASS |
| All 3 execution modes implemented and runnable | PASS |
| Equations 1-5 implemented and locatable | PARTIAL (Eq.1 missing gamma_max cap; Eq.2 alpha implicit) |
| Configurable parameters match Section 6 values exactly | FAIL (6 of 10 parameters differ) |
| 4 scales x 5 seeds = 20 runs supported | PASS (structure); PARTIAL (no explicit seed control) |
| Metrics SR, TTR, IRE, Cost computed correctly | PASS |
| Statistical test (Wilcoxon + rank-biserial) exists | PASS |
| Latency instrumentation captured | PASS |
| Output artifacts reproduce Tables 2-4 and Figures 2-5 | PASS |
