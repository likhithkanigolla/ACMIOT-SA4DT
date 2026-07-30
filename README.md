# Digital Twins for Uncertainty Mitigation in Self-Adaptive Smart City IoT Systems

Artifact package accompanying the paper submitted to:  
**IoT '26 — 16th International Conference on the Internet of Things**  
Newcastle upon Tyne, United Kingdom, November 17–20, 2026.

---

## Overview

This repository contains the modular evaluation pipeline for a self-adaptive IoT architecture in which a **Digital Twin (DT) serves as an explicit simulation-based validation gate** inserted between the Plan and Execute phases of the MAPE-K loop. A dedicated **Proactive Decision Engine** evaluates candidate adaptations against DT-simulated outcomes — scoring each by predicted fault resolution and resource cost — before any command reaches real actuators.

The framework introduces a two-class uncertainty taxonomy (epistemic S1–S6 / aleatoric S7–S11) that routes disruptions to appropriate mitigation strategies at runtime. It is evaluated on a smart-room IoT living-lab testbed across four temporal scales (1–30 days) with 5 randomly seeded trials per scale (20 runs/condition).

**Key results:**
- **Integrated Recovery Error (IRE)** reduced by 65–81% for epistemic faults and 65–76% for aleatoric faults relative to a reactive baseline ($p < 0.001$, Wilcoxon)
- **Actuation cost savings** of 46–71% via simulation-gate filtering of unnecessary commands
- **Negligible planning overhead:** $T_P \approx 0.007\text{ ms}$ vs. $\sim 50\text{ ms}$ OTA dispatch latency

---

## Quick-Start for Paper Reviewers (`run.py`)

A single unified entry point is provided at the root of the repository (`run.py`) to easily verify and exercise the MAPE-K + Digital Twin pipeline end-to-end.

### 1. Run a Step-by-Step Component Trace
To observe the exact sequential component execution described in Figure 1 of the paper (**Monitor → Analyse → Plan → [DT Simulation Gate] → Decision Engine → Execute → Shared Knowledge**):

```bash
# Run a 1-day evaluation with step-by-step trace output enabled
python run.py --mode sa_dt --scale 1 --seed 42 --trace
```

### 2. Run All Three Modes & Generate Analysis Reports
```bash
# Run Reactive, SA-Only, and SA-DT baselines sequentially on a 1-day trace and generate metrics
python run.py --mode all --scale 1 --seed 42
# Output: results/run_output/trial_summary.csv, raw_episodes.jsonl, paper_tables.tex, and figures/
```

### 3. Reproduce Paper Tables & Figures
You can automatically reproduce any specific table or figure from Section 5 of the paper across all scales ($1, 7, 15, 30\text{ days}$) and seeds:

```bash
# Reproduce Table 2 (Cumulative SR, TTR, IRE across all scales and modes)
python run.py --reproduce-table 2

# Reproduce Figure 2 (Adaptation Success Rate by Uncertainty Class)
python run.py --reproduce-figure 2
```

Supported flags for reproduction:
- `--reproduce-table {2, 3, 4}`
  - `2`: Table 2 — Cumulative SR, TTR, IRE, and Cost results
  - `3`: Table 3 — Runtime Latency Breakdown ($T_M$, $T_P$, $T_E$, $T_E^{\dagger}$)
  - `4`: Table 4 — Multi-Scale Performance Trends
- `--reproduce-figure {2, 3, 4, 5}`
  - `2`: Figure 2 — Success Rate by Uncertainty Class
  - `3`: Figure 3 — Integrated Recovery Error by Uncertainty Class
  - `4`: Figure 4 — Runtime Latency Stacked Bar
  - `5`: Figure 5 — Multi-Scale Success Rate and IRE Trend

---

## Repository Structure & Modular Architecture

The repository is structured into single-responsibility (SRP) Object-Oriented modules mapping directly to the layers of the paper:

```
artifact_package/
├── run.py                             <- Unified CLI entry point for trace testing & paper reproduction
├── README.md                          <- This file
├── LICENSE                            <- License
├── CITATION.cff                       <- Citation metadata
│
├── docs/
│   ├── architecture_mapping.md        <- Component-to-file cross-reference mapping
│   ├── refactor_log.md                <- Architectural refactoring log & regression verification
│   ├── missing_components.md          <- Documented parameter divergences and hardware gaps
│   └── verification_checklist.md      <- Presence/absence audit checklist
│
├── src/
│   ├── common/                        <- Shared strategies, utilities, and orchestration
│   │   ├── adaptation_mode.py         <- Abstract Base Class (Strategy pattern) for modes
│   │   ├── analysis.py                <- Callable statistical analysis pipeline (Wilcoxon, CIs, LaTeX)
│   │   ├── data_generator.py          <- Callable fault scenario generator with reproducible seeding
│   │   ├── reporting.py               <- Metric calculation and trial summarization utilities
│   │   ├── trace_runner.py            <- MAPE-K trace orchestration loop
│   │   └── modes/                     <- Concrete mode strategy implementations
│   │       ├── reactive_baseline.py   <- Baseline 1: Static rules without MAPE-K or DT
│   │       ├── sa_only.py             <- Baseline 2: MAPE-K loop without DT simulation gate
│   │       └── sa_dt.py               <- Proposed: Full MAPE-K + DT Simulation Gate + Utility Evaluator
│   │
│   ├── digital_twin/                  <- Digital Twin layer modules
│   │   ├── command_orchestrator/
│   │   │   └── ota_dispatcher.py      <- OTADispatcher (simulated OTA dispatch & ACK timestamps)
│   │   ├── predictive_analytics/
│   │   │   └── proactive_engine.py    <- ProactiveEngine (early warnings at theta_proactive=95%)
│   │   ├── semantic_context_manager/
│   │   │   └── risk_aggregator.py     <- risk_score() (Paper Eq. 3: composite risk index)
│   │   ├── simulation_runtime/
│   │   │   └── candidate_simulator.py <- CandidateSimulator (T_horizon=60s state fork per candidate)
│   │   ├── twin_state_sync/
│   │   │   └── sync_engine.py         <- sync_penalty() (Paper Eq. 1: confidence discount)
│   │   └── virtual_asset_model/
│   │       └── thermal_model.py       <- step_physical_world() (Paper Eq. 4: thermal dynamics)
│   │
│   ├── decision_engine/               <- Decision Engine modules
│   │   ├── policy_manager/
│   │   │   └── policy_manager.py      <- PolicyManager (hard safety constraint pruning for S4)
│   │   ├── uncertainty_routing/
│   │   │   └── routing_engine.py      <- RoutingEngine (epistemic S1-S6 vs aleatoric S7-S11 taxonomy)
│   │   └── utility_evaluator/
│   │       └── utility_evaluator.py   <- UtilityEvaluator, utility(), cost_of() (Paper Eq. 2)
│   │
│   └── managing_system/               <- Managing System (MAPE-K loop)
│       ├── monitor/
│       │   └── telemetry_monitor.py   <- TelemetryMonitor & PhysicalState (ingestion, T_M recording)
│       ├── analyse/
│       │   ├── fault_classifier.py    <- FaultClassifier (inline runtime anomaly categorization)
│       │   └── uncertainty_engine.py  <- Retained standalone Stage-1 research identification script
│       ├── plan/
│       │   └── adaptation_planner.py  <- AdaptationPlanner (synthesizes C1-C6 candidate actions)
│       ├── execute/
│       │   └── action_executor.py     <- ActionExecutor (coordinates dispatch, persists residuals)
│       └── shared_knowledge/
│           └── knowledge_store.py     <- Canonical Shared Knowledge: Config, SensorReading, Episode
│
├── tests/
│   └── test_regression.py             <- 55 automated tests proving bit-for-bit numerical parity
│
├── config/
│   ├── uncertainty_profile.json       <- Scenario injection parameters (S1-S11 probabilities)
│   ├── mapping_config.json            <- Column-to-domain mapping for telemetry CSV
│   └── THRESHOLDS.md                  <- Sensor threshold constants across verticals
│
├── results/                           <- Output directory for generated CSVs, LaTeX tables, and PDF figures
└── environment/
    └── requirements.txt               <- Python dependencies (numpy, pandas, scipy, matplotlib, seaborn)
```

---

## Requirements / Environment Setup

**Python version:** 3.10 or later

```bash
# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate     # macOS / Linux
# or: venv\Scripts\activate  # Windows

# Install dependencies
pip install -r environment/requirements.txt
```

---

## Automated Regression & Parity Verification

To guarantee that decomposing the original monolithic code into modular OOP components did not introduce any algorithmic drift or numerical discrepancies, a comprehensive regression test suite is provided.

```bash
# Run the 55 automated bit-for-bit regression tests
python -m pytest tests/test_regression.py -v
# or standalone:
python tests/test_regression.py
```

The suite verifies that every formula (Eq. 1–4), adaptation decision branch, utility calculation, and latency metric matches the reference pre-refactor implementation across nominal, anomaly, and edge-case inputs.

---

## Parameter Reference Table (Section 5 Values)

| Parameter | Symbol | Paper Value | Code Value | File / Module | Notes |
|-----------|--------|-------------|------------|---------------|-------|
| Thermal time constant | $\tau$ | $300\text{ s}$ | `Config.tau = 1.0` | `knowledge_store.py` | Paper: calibrated from 5-min commissioning test. Code uses normalized episode-scale unit. |
| Ventilation cooling rate | $c$ | $0.04\text{ }^\circ\text{C/s}$ | `Config.c_cooling = 0.5` | `knowledge_store.py` | Code uses normalized episode units. |
| Simulation horizon | $T_{\text{horizon}}$ | $60\text{ s}$ | Implicit ($1\text{ row} = 1\text{ min}$) | `trace_runner.py` | Implied by MAPE-K episode cadence. |
| Proactive warning threshold | $\theta_{\text{proactive}}$ | $95\%$ of nominal | `Config.proactive_trigger = 0.38` | `knowledge_store.py` | Paper uses $\%$ of physical limit; code uses absolute risk index scale. |
| Utility weight | $\alpha$ | $0.9$ | Implicit: $\text{cost} \times 0.1$ | `utility_evaluator.py` | Numerically equivalent: $(1 - 0.9) = 0.1$. |
| Max sync delay | $d_{\max}$ | $180\text{ s}$ | `lag_seconds = 180.0` | `sync_engine.py` | Exact match for S9 network instability. |
| Max prediction discount | $\gamma_{\max}$ | $0.35$ | Not capped | `sync_engine.py` | `sync_penalty(lag)` has no upper bound cap in code; intentionally retained for numerical parity. |
| Recovery risk threshold | $r_{\text{rec}}$ | $r < 0.20$ | `Config.recovery_threshold = 0.10` | `knowledge_store.py` | Code uses $0.10$ vs $0.20$ in paper text. |
| Recovery persistence | — | $3\text{ episodes}$ | `Config.recovery_persistence = 3` | `knowledge_store.py` | Exact match. |
| Decision threshold | — | $\sim 0.40$ | `Config.decision_threshold = 0.40` | `knowledge_store.py` | Exact match. |

---

## Citation

```bibtex
@inproceedings{anonymous2026dt,
  title     = {Digital Twins for Uncertainty Mitigation in Self-Adaptive Smart City IoT Systems},
  author    = {Anonymous Authors},
  booktitle = {Proceedings of the 16th International Conference on the Internet of Things (IoT '26)},
  year      = {2026},
  location  = {Newcastle upon Tyne, United Kingdom},
  publisher = {ACM}
}
```
