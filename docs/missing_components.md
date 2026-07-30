# Missing / Unverified Components

This document flags architectural components described in the paper that have no corresponding
file in this repository, as well as discrepancies between paper-stated parameter values and
code-level values.

---

## 1. Completely Absent Components

### 1.1 IoT Node Firmware / Microcontroller Code
- **Paper reference:** Section 5 (§Testbed and hardware): "OTA commands are dispatched
  asynchronously over Wi-Fi to an ESP32 microcontroller"; sensors include SI7021, VEML7700,
  SGP30, PIR; actuators are PWM ventilation fans, RGB status indicators, acoustic buzzers.
- **What is missing:** No ESP32 firmware, no sensor driver code, no OTA communication
  protocol implementation is present in this repository.
- **Impact:** The managed-system (physical sensing-actuation) side of the architecture cannot
  be reproduced from this codebase alone. The evaluation pipeline simulates OTA round-trip
  latency (50ms ± 5ms) rather than exercising real hardware.

### 1.2 Interoperability Layer (oneM2M client/adapter)
- **Paper reference:** Section 4.1: "an Interoperability Layer provides a standardized IoT
  communications interface (such as oneM2M)"; Section 5: "communicates with a centralised DT
  simulation framework over a secured oneM2M interoperability interface".
- **What is missing:** No oneM2M adapter, CSE client, or interoperability glue code is present.
- **Impact:** Live data ingestion from the smart city living lab cannot be exercised. The pipeline
  reads from CSV files instead.

### 1.3 Sliding-Window Linear Risk Projection (Predictive Analytics Engine)
- **Paper reference:** Section 4.2: "computes linear risk trajectories over sliding telemetry
  windows and projects anticipated operational stress across a proactive forecasting horizon
  T_forecast < T_horizon."
- **What is missing:** No sliding-window projection function exists in any file. The proactive
  trigger in `decide_sa_dt()` checks whether the current risk r is in the range
  (proactive_trigger, decision_threshold), which is a point-in-time check, not a forward
  trajectory projection.
- **Impact:** The Predictive Analytics Engine as described (projecting future risk across
  T_forecast=55s) is not fully implemented. The proactive rate of 3.94% reported in the paper
  results from the threshold-band check, not from genuine forward projection.

### 1.4 Persistent Shared Knowledge Store
- **Paper reference:** Section 4.4: "Execute... conveys measured physical outcome residuals back
  to shared Knowledge to refine adaptive models and parameterize future utility evaluations."
- **What is missing:** No persistent store (file, dictionary, or database) accumulates
  episode-by-episode residuals across trials. The Config dataclass in `evaluation_pipeline.py`
  holds fixed parameters; tau re-estimation in `decide_sa_dt()` is a one-shot hard-coded
  multiplier (tau * 2.0) for S2/S5, not a continuously refined learning store.
- **Impact:** Adaptive learning described in the paper (Section 4.2: "internal parameterizations
  are continuously refined episode-by-episode using measured physical residuals") is not
  implemented as an accumulating online learner.

---

## 2. Partially Implemented Components

### 2.1 Policy Manager
- **Paper reference:** Section 4.3: "intercepts utility rankings before commands are committed to
  the Command Orchestrator, enforcing absolute hardware safety constraints, power budgets, and
  mechanical actuation limits."
- **What exists:** Candidate pruning is embedded inline inside `decide_sa_dt()` for S4 only
  (reduces candidates to {C3, C4, C6}). No separate, generalized constraint-checking function
  or class exists.
- **Impact:** Hard safety constraints are scenario-specific, not a general safety gate.

### 2.2 Command Orchestrator (Real OTA Dispatch)
- **Paper reference:** Section 4.2: "translates abstract candidate identifiers into concrete
  hardware actuator set-points, formats protocol-compliant OTA payloads, dispatches commands
  asynchronously to physical controllers, and captures precise hardware acknowledgment
  timestamps."
- **What exists:** `experiment_runner.py` simulates OTA latency via
  `ota_latency = 50.0 + np.random.normal(0, 5.0)` ms. No actual payload formatting or
  ESP32 communication is implemented.
- **Impact:** T_E values reported in the paper are simulated, not measured from real OTA rounds.

---

## 3. Parameter Value Discrepancies

The following parameters are stated in Section 5 (§Parameter calibration) of the paper but
differ from or are absent in the code:

| Parameter | Paper Value | Code Value | Location | Discrepancy |
|-----------|------------|------------|----------|-------------|
| tau (thermal time constant) | 300 s | Config.tau = 1.0 | evaluation_pipeline.py L6 | Paper calibrated from 5-min commissioning test; code uses a normalized simulation unit. |
| c (cooling rate coefficient) | 0.04 degC/s | Config.c_cooling = 0.5 | evaluation_pipeline.py L7 | Mismatch in physical units; code likely uses a normalized episode-scale unit. |
| T_horizon | 60 s | Not explicitly set | -- | Implied by 1-minute CSV row frequency; no variable named T_horizon. |
| T_forecast | 55 s | Not found in code | -- | Proactive check is point-in-time only; T_forecast not implemented as a named variable. |
| theta_proactive | 95% of nominal | Config.proactive_trigger = 0.38 | evaluation_pipeline.py L9 | Paper expresses as 95% of the nominal safety limit; code uses an absolute risk score. |
| gamma_max | 0.35 | Not applied | sync_penalty() | The sync_penalty function returns lag * 0.01 with no upper bound cap at 0.35. |
| recovery threshold | r < 0.2 | Config.recovery_threshold = 0.10 | evaluation_pipeline.py L10 | Paper states r < 0.2; code uses 0.10. This affects TTR and SR computation. |

### Consequence Note
Because tau and c are the primary parameters of the thermal model (Eq. 4: T_hat_{t+k}), the
discrepancy between paper values (tau=300, c=0.04) and code values (tau=1.0, c=0.5) means
that `simulate_candidate()` and `physical_simulator.py` operate with episode-normalized units
rather than real physical seconds. The simulation produces qualitatively correct ordering of
candidate outcomes but not quantitatively correct absolute temperature predictions matching
the commissioning characterization.

---

## 4. Scope Notes (Not Gaps)

The following items are explicitly out of scope for this repository (single-room testbed,
simulation-based evaluation only) and are flagged as future work in the paper:

- Multi-room or district-scale deployment
- Non-thermal domains (water, traffic)
- Non-linear thermal modeling
- External held-out validation against independently audited industrial datasets
- Live hardware OTA across multiple vendor sensor networks
