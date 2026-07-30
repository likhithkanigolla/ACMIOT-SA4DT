"""
Data Generator — Fault Scenario Injector
==========================================

Paper reference: Section 5 — Experimental Design; Table 1 (S1-S11 scenarios)

Responsibility: generate synthetic multi-node telemetry with controlled fault
injection for all 11 uncertainty scenarios (S1-S11) plus Clock Sync Failure.

This module wraps the original make_test_data.py logic into a callable
`generate_dataset()` function so that run.py can invoke it directly (rather
than via subprocess) with a controllable random seed.

IMPORTANT: All fault injection logic is extracted VERBATIM from
experiments/fault_scenarios/make_test_data.py — no algorithmic changes.
The original file is retained as a standalone CLI entry point for backward
compatibility; this module adds the callable API on top.

Original file: experiments/fault_scenarios/make_test_data.py
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Core generation logic (extracted verbatim from make_test_data.py)
# ---------------------------------------------------------------------------

def _apply_label(df: pd.DataFrame, start: int, end: int, label: str) -> None:
    """Apply anomaly label to a range of rows (verbatim from make_test_data.py L6-12)."""
    mask = df["anomaly_label"] == "Normal"
    new_labels_for_anomalous = df.loc[start:end, "anomaly_label"] + "|" + label
    df.loc[start:end, "anomaly_label"] = np.where(
        mask.loc[start:end], label, new_labels_for_anomalous
    )


def _generate_baseline(config: dict, num_samples: int, freq_min: int, rng) -> np.ndarray:
    """Generate one parameter's baseline signal (verbatim from make_test_data.py L14-56)."""
    base = config["base"]
    amp = config["amplitude"]
    noise = config["noise"]
    ptype = config["type"]

    samples_per_day = 24 * 60 // freq_min
    t = np.linspace(0, num_samples / samples_per_day * 2 * np.pi, num_samples)

    if ptype == "continuous":
        daily_cycle = amp * np.sin(t - np.pi / 2)
        weather_cycle = (amp / 2) * np.sin(t / 4)
        ar_noise = np.zeros(num_samples)
        for i in range(1, num_samples):
            ar_noise[i] = 0.85 * ar_noise[i - 1] + rng.normal(0, noise)
        signal = base + daily_cycle + weather_cycle + ar_noise

    elif ptype == "daynight":
        daily_cycle = amp * np.sin(t - np.pi / 2)
        daily_cycle = np.clip(daily_cycle, 0, None)
        cloud_cover = np.clip(rng.normal(1.0, 0.3, num_samples), 0.2, 1.0)
        signal = base + (daily_cycle * cloud_cover) + rng.normal(0, noise, num_samples)
        signal = np.clip(signal, 0, None)

    elif ptype == "binary":
        base_prob = 0.05 + 0.1 * np.sin(t - np.pi / 2)
        base_prob = np.clip(base_prob, 0.01, 1.0)
        signal = rng.binomial(1, base_prob, num_samples) * amp

    else:
        signal = np.full(num_samples, base) + rng.normal(0, noise, num_samples)

    return signal


def generate_dataset(
    days: int,
    seed: Optional[int],
    profile_path: Path,
    out_file: Optional[Path] = None,
) -> pd.DataFrame:
    """
    Generate a synthetic telemetry dataset with S1-S11 fault injection.

    This is the callable API wrapping make_test_data.py's main() logic.
    All fault injection logic is verbatim — no behavioral changes.

    Parameters
    ----------
    days         : int — number of simulation days.
    seed         : int or None — random seed for reproducibility (None = unseeded).
    profile_path : Path — path to uncertainty_profile.json.
    out_file     : Path or None — if provided, save CSV to this path.

    Returns
    -------
    pd.DataFrame : The generated telemetry with 'anomaly_label' column.
    """
    with open(profile_path) as f:
        profile = json.load(f)

    rng = np.random.default_rng(seed)
    freq_min = profile["frequency_minutes"]
    num_samples = days * 24 * 60 // freq_min

    all_dfs = []
    params = profile["parameters"]
    scenarios = profile.get("scenarios", {})

    for node_id in profile["nodes"]:
        timestamps = pd.date_range("2026-01-01", periods=num_samples, freq=f"{freq_min}min")
        df_node = pd.DataFrame({
            "timestamp": timestamps,
            "node_id": node_id,
            "anomaly_label": "Normal",
        })

        for p_name, p_conf in params.items():
            df_node[p_name] = _generate_baseline(p_conf, num_samples, freq_min, rng)

        cols = [c for c in df_node.columns if c != "anomaly_label"] + ["anomaly_label"]
        df_node = df_node[cols]

        # ---- S1: Sensor Drift ----
        if "S1_Sensor_Drift" in scenarios:
            conf = scenarios["S1_Sensor_Drift"]
            n_inc = max(1, int(days * conf["prob_per_day"]))
            dur = conf["duration_samples"]
            mag = conf.get("magnitude", 15.0)
            for _ in range(n_inc):
                p = rng.choice(list(params.keys()))
                s = rng.integers(0, max(1, len(df_node) - dur))
                e = min(s + dur - 1, len(df_node) - 1)
                df_node.loc[s:e, p] += np.linspace(0, mag, e - s + 1)
                _apply_label(df_node, s, e, f"S1({p})")

        # ---- S2: Model Error ----
        if "S2_Model_Error" in scenarios:
            conf = scenarios["S2_Model_Error"]
            n_inc = max(1, int(days * conf["prob_per_day"]))
            dur = conf["duration_samples"]
            bias = conf.get("bias", 2.5)
            for _ in range(n_inc):
                p = rng.choice(list(params.keys()))
                s = rng.integers(0, max(1, len(df_node) - dur))
                e = min(s + dur - 1, len(df_node) - 1)
                df_node.loc[s:e, p] += bias
                _apply_label(df_node, s, e, f"S2({p})")

        # ---- S3: Actuation Deviation ----
        if "S3_Actuation_Deviation" in scenarios:
            conf = scenarios["S3_Actuation_Deviation"]
            n_inc = max(1, int(days * conf["prob_per_day"]))
            dur = conf["duration_samples"]
            offset = conf.get("offset", -10.0)
            for _ in range(n_inc):
                p = rng.choice(list(params.keys()))
                s = rng.integers(0, max(1, len(df_node) - dur))
                e = min(s + dur - 1, len(df_node) - 1)
                df_node.loc[s:e, p] += offset
                _apply_label(df_node, s, e, f"S3({p})")

        # ---- S4: Stuck Sensor ----
        if "S4_Stuck_Sensor" in scenarios:
            conf = scenarios["S4_Stuck_Sensor"]
            n_inc = max(1, int(days * conf["prob_per_day"]))
            dur = conf["duration_samples"]
            for _ in range(n_inc):
                p = rng.choice(list(params.keys()))
                s = rng.integers(0, max(1, len(df_node) - dur))
                e = min(s + dur - 1, len(df_node) - 1)
                stuck_val = df_node.loc[s, p]
                df_node.loc[s:e, p] = stuck_val
                _apply_label(df_node, s, e, f"S4({p})")

        # ---- S5: Behavioral Drift ----
        if "S5_Behavioral_Drift" in scenarios:
            conf = scenarios["S5_Behavioral_Drift"]
            n_inc = max(1, int(days * conf["prob_per_day"]))
            dur = conf["duration_samples"]
            amp_mult = conf.get("amplitude_multiplier", 0.5)
            for _ in range(n_inc):
                p = rng.choice(list(params.keys()))
                s = rng.integers(0, max(1, len(df_node) - dur))
                e = min(s + dur - 1, len(df_node) - 1)
                decay = np.linspace(1.0, amp_mult, e - s + 1)
                df_node.loc[s:e, p] *= decay
                _apply_label(df_node, s, e, f"S5({p})")

        # ---- S6: Actuator Failure ----
        if "S6_Actuator_Failure" in scenarios:
            conf = scenarios["S6_Actuator_Failure"]
            n_inc = max(1, int(days * conf["prob_per_day"]))
            dur = conf["duration_samples"]
            for _ in range(n_inc):
                p = rng.choice(list(params.keys()))
                s = rng.integers(0, max(1, len(df_node) - dur))
                e = min(s + dur - 1, len(df_node) - 1)
                df_node.loc[s:e, p] = 0.0
                _apply_label(df_node, s, e, f"S6({p})")

        # ---- S7: Measurement Noise ----
        if "S7_Measurement_Noise" in scenarios:
            conf = scenarios["S7_Measurement_Noise"]
            n_inc = max(1, int(days * conf["prob_per_day"]))
            dur = conf["duration_samples"]
            mag_mult = conf.get("magnitude_multiplier", 5.0)
            for _ in range(n_inc):
                p = rng.choice(list(params.keys()))
                s = rng.integers(0, max(1, len(df_node) - dur))
                e = min(s + dur - 1, len(df_node) - 1)
                noise_lvl = params[p]["noise"] * mag_mult
                if noise_lvl == 0:
                    noise_lvl = mag_mult
                df_node.loc[s:e, p] += rng.normal(0, noise_lvl, e - s + 1)
                _apply_label(df_node, s, e, f"S7({p})")

        # ---- S11: Environmental Variability ----
        if "S11_Environmental_Variability" in scenarios:
            conf = scenarios["S11_Environmental_Variability"]
            n_inc = max(1, int(days * conf["prob_per_day"]))
            dur = conf["duration_samples"]
            mag = conf.get("magnitude", 20.0)
            for _ in range(n_inc):
                s = rng.integers(0, max(1, len(df_node) - dur))
                e = min(s + dur - 1, len(df_node) - 1)
                for p, p_conf in params.items():
                    if p_conf["type"] != "binary":
                        df_node.loc[s:e, p] += np.sin(np.linspace(0, np.pi, e - s + 1)) * mag
                _apply_label(df_node, s, e, "S11_Env_Var")

        # ---- S8 + S10: Packet Loss + Reconnection Events ----
        if "S8_Packet_Loss" in scenarios:
            conf = scenarios["S8_Packet_Loss"]
            s10_conf = scenarios.get("S10_Reconnection_Events")
            n_inc = max(1, int(days * conf["prob_per_day"]))
            dur = conf["duration_samples"]
            drop_indices = []
            reconnect_rows = []
            for _ in range(n_inc):
                s = rng.integers(0, max(1, len(df_node) - dur - 10))
                e = min(s + dur, len(df_node))
                drop_indices.extend(range(s, e))
                if s10_conf:
                    recon_dur = s10_conf["duration_samples"]
                    burst_start_time = df_node.loc[min(e, len(df_node) - 1), "timestamp"]
                    burst_row_template = df_node.iloc[min(e, len(df_node) - 1)].copy()
                    for i in range(1, recon_dur + 1):
                        new_row = burst_row_template.copy()
                        new_row["timestamp"] = burst_start_time + pd.Timedelta(seconds=i)
                        new_row["anomaly_label"] = "S10_Reconnect"
                        reconnect_rows.append(pd.DataFrame([new_row]))
            drop_indices = list(set(drop_indices))
            df_node = df_node.drop(index=drop_indices).reset_index(drop=True)
            if reconnect_rows:
                burst_df = pd.concat(reconnect_rows, ignore_index=True)
                df_node = (
                    pd.concat([df_node, burst_df])
                    .sort_values("timestamp")
                    .reset_index(drop=True)
                )

        # ---- S9: Network Instability ----
        if "S9_Network_Instability" in scenarios:
            conf = scenarios["S9_Network_Instability"]
            n_inc = max(1, int(days * conf["prob_per_day"]))
            dur = conf["duration_samples"]
            for _ in range(n_inc):
                s = rng.integers(0, max(1, len(df_node) - dur))
                _apply_label(df_node, s, min(s + dur - 1, len(df_node) - 1), "S9_Net_Instab")
                chunk = df_node.iloc[s:s + dur].copy()
                df_node = pd.concat(
                    [df_node.iloc[: s + dur], chunk, df_node.iloc[s + dur:]]
                ).reset_index(drop=True)
                shuffle_idx = np.arange(s, min(s + 2 * dur, len(df_node)))
                rng.shuffle(shuffle_idx)
                df_node.iloc[s:s + len(shuffle_idx)] = df_node.iloc[shuffle_idx].values

        # ---- Clock Sync Failure ----
        if "Clock_Sync_Failure" in scenarios:
            conf = scenarios["Clock_Sync_Failure"]
            n_inc = max(1, int(days * conf["prob_per_day"]))
            dur = conf["duration_samples"]
            for _ in range(n_inc):
                s = rng.integers(0, max(1, len(df_node) - dur))
                e = min(s + dur - 1, len(df_node) - 1)
                df_node.loc[s:e, "timestamp"] = pd.to_datetime("1970-01-01 00:00:00")
                _apply_label(df_node, s, e, "Clock_Sync_Fail")

        all_dfs.append(df_node)

    final_df = pd.concat(all_dfs, ignore_index=True)

    if out_file is not None:
        final_df.to_csv(out_file, index=False)

    return final_df
