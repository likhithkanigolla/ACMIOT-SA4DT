"""
Experiment Trace Runner
========================

Paper reference: Section 5 — Experimental Design

This module implements the core MAPE-K trace loop — reading one CSV row per
episode and wiring Monitor → Analyse → Plan → DT Gate → Execute → Knowledge.

It replaces the monolithic experiment_runner.py (which encoded all components
inline) with a clean orchestration loop that delegates each responsibility to
the correct component.

The loop is algorithm-identical to the original experiment_runner.py so that
numerical outputs are bit-for-bit equivalent on the same input data and seed.
"""

from __future__ import annotations

import csv
import json
import time
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from src.managing_system.shared_knowledge.knowledge_store import Config, KnowledgeStore
from src.managing_system.monitor.telemetry_monitor import TelemetryMonitor, PhysicalState
from src.managing_system.execute.action_executor import ActionExecutor
from src.common.adaptation_mode import AdaptationMode
from src.common.reporting import compute_trial_summary


def run_trace(
    csv_path: str,
    mode: AdaptationMode,
    config: Config,
    knowledge_store: KnowledgeStore,
    trace: bool = False,
) -> list:
    """
    Run one MAPE-K trace over the full telemetry CSV.

    This is the refactored equivalent of the original experiment_runner.py
    run_trace() function. Algorithm is identical — only the component
    boundaries are now explicit.

    Parameters
    ----------
    csv_path       : Path to telemetry.csv.
    mode           : AdaptationMode instance (ReactiveBaseline, SAOnly, or SADT).
    config         : Shared Config from KnowledgeStore.
    knowledge_store: KnowledgeStore — used by ActionExecutor to record residuals.
    trace          : If True, print step-by-step MAPE-K component trace.

    Returns
    -------
    list[Episode] — all anomaly-row episodes for this trace.
    """
    if trace:
        print(f"\n{'='*60}")
        print(f"[run_trace] MODE: {mode.name} | CSV: {csv_path}")
        print(f"{'='*60}")

    df = pd.read_csv(csv_path)

    live_tel_url = getattr(config, "live_telemetry_url", None)
    monitor = TelemetryMonitor(live_endpoint_url=live_tel_url)
    executor = ActionExecutor(knowledge_store)
    physical_state = PhysicalState()

    episodes = []
    current_incident_start: Optional[int] = None
    current_incident_label: Optional[str] = None
    consecutive_recovered: int = 0
    episodes_to_recover: Optional[int] = None

    for idx, row in df.iterrows():
        label = str(row["anomaly_label"])

        # ── MONITOR ──────────────────────────────────────────────────
        perceived_reading, t_m = monitor.ingest_row(row, idx, physical_state)
        if trace:
            print(
                f"[Monitor  ] ep={idx:5d} | label={label:<20s} | "
                f"T={perceived_reading.temperature:.1f}°C  CO2={perceived_reading.co2:.0f}ppm  "
                f"lag={perceived_reading.lag_seconds:.0f}s  T_M={t_m:.1f}ms"
            )

        # ── ANALYSE / PLAN / EXECUTE (fault episodes only) ────────────
        if label != "Normal":
            if current_incident_label is None:
                current_incident_start = idx
                current_incident_label = label
                consecutive_recovered = 0
                episodes_to_recover = None

            prior_state = episodes[-1].true_state if len(episodes) > 0 else None

            # ── ANALYSE + PLAN + DT GATE + DECISION ENGINE ────────────
            t_start = time.perf_counter()
            decision_result = mode.evaluate_and_act(
                reading=perceived_reading,
                fault_hint=label,
                prior_state=prior_state,
                config=config,
            )
            t_end = time.perf_counter()
            t_p = (t_end - t_start) * 1000.0  # ms

            candidate = decision_result.get("candidate_selected")
            r_measured = decision_result["r_measured"]

            if trace:
                print(
                    f"[{mode.name:<8s}] ep={idx:5d} | r={r_measured:.3f} | "
                    f"candidate={candidate}  method={decision_result.get('selection_method')}  "
                    f"T_P={t_p:.3f}ms  proactive={decision_result.get('proactive', False)}"
                )

            # ── EXECUTE ───────────────────────────────────────────────
            raw_temp = float(row["temperature"]) if not pd.isna(row["temperature"]) else None
            raw_co2  = float(row["co2_ppm"])     if not pd.isna(row["co2_ppm"])     else None

            ep, t_e = executor.apply_and_record(
                candidate=candidate,
                perceived_reading=perceived_reading,
                raw_temp=raw_temp,
                raw_co2=raw_co2,
                physical_state=physical_state,
                config=config,
                decision_result=decision_result,
                episode_meta={
                    "episode_index": idx,
                    "scenario_id": label,
                    "mode": mode.name,
                    "severity": 1.0,
                    "prior_state": prior_state or perceived_reading.__dict__,
                    "t_m": t_m,
                    "t_p": t_p,
                    "r_measured": r_measured,
                },
            )

            if trace:
                print(
                    f"[Execute  ] ep={idx:5d} | T_E={t_e:.1f}ms  "
                    f"risk_drift={ep.risk_drift}"
                )

            # ── SHARED KNOWLEDGE: track recovery ─────────────────────
            if episodes_to_recover is None:
                if r_measured < config.recovery_threshold:
                    consecutive_recovered += 1
                    if consecutive_recovered >= config.recovery_persistence:
                        episodes_to_recover = idx - current_incident_start
                else:
                    consecutive_recovered = 0

            episodes.append(ep)

        else:
            # Normal row — close out any open incident
            if current_incident_label is not None:
                success = episodes_to_recover is not None
                if not success:
                    episodes_to_recover = idx - current_incident_start

                for e in reversed(episodes):
                    if e.scenario_id == current_incident_label:
                        e.episodes_to_recover = episodes_to_recover
                        e.episode_success = success
                    else:
                        break

                current_incident_start = None
                current_incident_label = None
                physical_state.clear_recalibration()

            # Natural decay between fault episodes
            physical_state.apply_natural_decay(config.tau)

    # Edge case: dataset ends exactly on an anomaly
    if current_incident_label is not None:
        success = episodes_to_recover is not None
        if not success:
            episodes_to_recover = len(df) - current_incident_start
        for e in reversed(episodes):
            if e.scenario_id == current_incident_label:
                e.episodes_to_recover = episodes_to_recover
                e.episode_success = success
            else:
                break

    if trace:
        print(f"\n[run_trace] Complete. Total anomaly episodes: {len(episodes)}")

    return episodes


def run_all_modes(
    csv_path: str,
    output_dir: str,
    config: Config,
    modes: list[AdaptationMode],
    trace: bool = False,
) -> list:
    """
    Run all three modes over the same telemetry CSV and write output files.

    Produces:
      raw_episodes.csv / .jsonl — per-episode records
      trial_summary.csv         — per-trial aggregated metrics

    This is the refactored equivalent of experiment_runner.py run_all_traces().
    """
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    raw_episodes_csv   = out_path / "raw_episodes.csv"
    raw_episodes_jsonl = out_path / "raw_episodes.jsonl"
    trial_summary_file = out_path / "trial_summary.csv"

    all_episodes = []
    for mode in modes:
        # Each mode gets a fresh KnowledgeStore to avoid cross-mode contamination
        ks = KnowledgeStore(config)
        eps = run_trace(csv_path, mode, config, ks, trace=trace)
        all_episodes.extend(eps)

    # Write raw outputs
    with open(raw_episodes_csv, "w", newline="") as f_raw, \
         open(raw_episodes_jsonl, "w") as f_jsonl:

        raw_writer = None
        for ep in all_episodes:
            d = ep.__dict__
            if raw_writer is None:
                raw_writer = csv.DictWriter(f_raw, fieldnames=d.keys())
                raw_writer.writeheader()
            out_d = d.copy()
            out_d["true_state"] = str(d["true_state"])
            out_d["perceived_state"] = str(d["perceived_state"])
            raw_writer.writerow(out_d)
            f_jsonl.write(json.dumps(d) + "\n")

    # Write trial summary
    with open(trial_summary_file, "w", newline="") as f_sum:
        sum_writer = csv.writer(f_sum)
        sum_writer.writerow([
            "scenario", "mode", "severity", "trial_seed",
            "episodes_to_recover", "episode_success",
            "mean_risk_drift", "mean_cost", "proactive_count", "integrated_risk", "lead_time",
        ])

        current_chunk = []
        trial_id = 0
        current_mode: Optional[str] = None

        for i, ep in enumerate(all_episodes):
            if current_mode != ep.mode:
                trial_id = 0
                current_mode = ep.mode

            current_chunk.append(ep)
            is_last = i == len(all_episodes) - 1

            if not is_last:
                next_ep = all_episodes[i + 1]
                chunk_breaks = (
                    next_ep.mode != ep.mode
                    or next_ep.scenario_id != ep.scenario_id
                    or next_ep.episode_index != ep.episode_index + 1
                )
            else:
                chunk_breaks = True

            if chunk_breaks and current_chunk:
                summary = compute_trial_summary(current_chunk, config)
                trial_id += 1
                sum_writer.writerow([
                    ep.scenario_id, ep.mode, 1.0, trial_id,
                    summary["episodes_to_recover"],
                    summary["episode_success"],
                    summary["mean_risk_drift"],
                    summary["mean_cost"],
                    summary["proactive_count"],
                    summary["integrated_risk"],
                    summary["lead_time"],
                ])
                current_chunk = []

    return all_episodes
