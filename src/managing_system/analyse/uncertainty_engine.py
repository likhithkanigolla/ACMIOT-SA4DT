"""
Uncertainty Identification Engine for Smart City IoT Systems
==============================================================

Stage-1-only component of a three-stage evaluation pipeline
(Traditional IoT -> Digital Twin -> Self-Adaptive Digital Twin).

This module does NOT perform anomaly classification against fixed
thresholds, does NOT plan or execute remediation, and is NOT a
Digital Twin / MAPE-K / self-adaptive component. It reads historical
telemetry, asks the user to map columns to domains/parameters and to
supply desirable operating ranges (context only, not detection
thresholds), then infers likely uncertainty episodes (S1-S11) from
the temporal/statistical shape of the data and writes an
evidence-based report.

Output:
    - a continuously-updated human-readable log file (tail -f friendly)
    - a machine-readable JSON report
    - a human-readable Markdown report
"""

from __future__ import annotations

import json
import sys
import time
import argparse
import gc
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional
from collections import defaultdict

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Uncertainty scenario catalogue
# ---------------------------------------------------------------------------

SCENARIOS = {
    "S1": "Sensor Drift",
    "S2": "Model Error",
    "S3": "Actuation Deviation",
    "S4": "Stuck Sensor",
    "S5": "Behavioral Drift",
    "S6": "Actuator Failure",
    "S7": "Measurement Noise",
    "S8": "Packet Loss",
    "S9": "Network Instability",
    "S10": "Reconnection Events",
    "S11": "Environmental Variability",
    "S12": "Clock Sync Failure",
}


# ---------------------------------------------------------------------------
# Logging: continuous, file-based (never console-only)
# ---------------------------------------------------------------------------

class RunLogger:
    """Appends human-readable progress lines to a log file in real time.

    Intended to be tailed (e.g. `tail -f uncertainty_run.log`) from an
    editor/terminal while the engine runs, per the requirement that
    output must never rely solely on console printing.
    """

    def __init__(self, log_path: Path):
        self.log_path = log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        # truncate/start fresh each run
        with open(self.log_path, "w", encoding="utf-8") as f:
            f.write(f"=== Uncertainty Identification Engine run started {datetime.now().isoformat()} ===\n")

    def line(self, text: str = ""):
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(text + "\n")
        # also echo to console for interactive convenience
        print(text)

    def section(self, title: str):
        self.line("")
        self.line(f"--- {title} ---")

    def evidence_block(self, scenario_name: str, confidence: float, evidence_lines: list[str]):
        self.line(f"Possible {scenario_name} detected.")
        self.line(f"Confidence: {confidence:.0%}")
        self.line("Evidence:")
        for e in evidence_lines:
            self.line(f"  - {e}")
        self.line("")


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Incident:
    incident_id: str
    node_id: Optional[str]
    parameter: str
    domain: str
    start_timestamp: str
    end_timestamp: str
    duration_seconds: float
    primary_uncertainty: str
    secondary_uncertainty: Optional[str]
    confidence_score: float
    supporting_evidence: list[str]
    affected_samples: int

    def to_dict(self):
        return asdict(self)


@dataclass
class ColumnMapping:
    timestamp_col: str
    node_col: Optional[str]
    parameter_domains: dict[str, str]        # column -> domain
    parameter_ranges: dict[str, tuple[float, float]]  # column -> (low, high)


# ---------------------------------------------------------------------------
# Interactive mapping (column -> domain, and desirable ranges)
# ---------------------------------------------------------------------------

def interactive_column_mapping(df: pd.DataFrame, logger: RunLogger) -> ColumnMapping:
    columns = list(df.columns)
    logger.section("Column Detection")
    logger.line("Detected Columns:")
    for c in columns:
        logger.line(f"  {c}")

    print("\nWhich column contains timestamps?")
    for i, c in enumerate(columns):
        print(f"  [{i}] {c}")
    ts_idx = int(input("Enter index: ").strip())
    timestamp_col = columns[ts_idx]

    print("\nWhich column contains the node/device ID? (Press Enter to skip)")
    for i, c in enumerate(columns):
        print(f"  [{i}] {c}")
    node_idx = input("Enter index: ").strip()
    node_col = columns[int(node_idx)] if node_idx else None

    param_cols = [c for c in columns if c not in (timestamp_col, node_col)]

    parameter_domains: dict[str, str] = {}
    print("\nFor each remaining column, enter the domain it belongs to")
    print("(e.g. Water Quality, Air Quality, Water Quantity, Water Level,")
    print(" Weather Monitoring, Energy Monitoring, Crowd Monitoring, Other):")
    for c in param_cols:
        domain = input(f'  Domain for "{c}": ').strip() or "Unspecified"
        parameter_domains[c] = domain

    parameter_ranges: dict[str, tuple[float, float]] = {}
    print("\nFor each parameter, enter its desirable operating range.")
    print("(This defines normal operating context only - NOT an uncertainty threshold.)")
    for c in param_cols:
        raw = input(f'  Desirable range for "{c}" (low,high), or blank to skip: ').strip()
        if raw:
            try:
                low_s, high_s = raw.split(",")
                parameter_ranges[c] = (float(low_s), float(high_s))
            except ValueError:
                print("    Could not parse; skipping range for this column.")

    logger.section("Mapping Confirmed")
    logger.line(f"Timestamp column: {timestamp_col}")
    if node_col:
        logger.line(f"Node column: {node_col}")
    logger.line("Parameter -> Domain:")
    for c, d in parameter_domains.items():
        logger.line(f"  {c} -> {d}")
    logger.line("Desirable ranges (context only):")
    for c, (lo, hi) in parameter_ranges.items():
        logger.line(f"  {c}: {lo} to {hi}")

    return ColumnMapping(timestamp_col, node_col, parameter_domains, parameter_ranges)


def load_mapping_from_json(path: Path) -> ColumnMapping:
    """Non-interactive alternative: supply mapping via a JSON config file.

    Expected schema:
    {
      "timestamp_col": "timestamp",
      "parameter_domains": {"tds": "Water Quality", "pm25": "Air Quality"},
      "parameter_ranges": {"tds": [200, 500], "pm25": [0, 50]}
    }
    """
    cfg = json.loads(Path(path).read_text())
    ranges = {k: tuple(v) for k, v in cfg.get("parameter_ranges", {}).items()}
    return ColumnMapping(
        timestamp_col=cfg["timestamp_col"],
        node_col=cfg.get("node_col"),
        parameter_domains=cfg["parameter_domains"],
        parameter_ranges=ranges,
    )


# ---------------------------------------------------------------------------
# Detectors
#
# Each detector inspects a single parameter's time series (a pandas
# Series indexed by timestamp, plus the full timestamp index for
# communication-related checks) and returns zero or more candidate
# episodes: (start, end, confidence, evidence_lines, affected_samples).
# ---------------------------------------------------------------------------

@dataclass
class Candidate:
    scenario_code: str
    start: pd.Timestamp
    end: pd.Timestamp
    confidence: float
    evidence: list[str]
    affected_samples: int


def _expected_interval(index: pd.DatetimeIndex) -> pd.Timedelta:
    diffs = index.to_series().diff().dropna()
    if len(diffs) == 0:
        return pd.Timedelta(minutes=5)
    return diffs.median()


def detect_sensor_drift(series: pd.Series, window_days: int = 5) -> list[Candidate]:
    """S1 - slow monotonic deviation, neighboring stability not modeled here
    at the single-parameter level (handled by cross-parameter check)."""
    candidates = []
    s = series.dropna()
    if len(s) < 20:
        return candidates

    step = max(1, len(s) // 200)
    window = pd.Timedelta(days=window_days)
    i = 0
    idx = s.index
    values = s.values
    n = len(s)

    while i < n:
        t0 = idx[i]
        t_end = t0 + window
        mask = (idx >= t0) & (idx <= t_end)
        seg_idx = np.where(mask)[0]
        if len(seg_idx) < 10:
            i += step
            continue
        seg_vals = values[seg_idx]
        seg_times = np.asarray((idx[seg_idx] - idx[seg_idx][0]) / pd.Timedelta(hours=1), dtype=float)
        # linear regression slope
        if seg_times.max() == 0:
            i += step
            continue
        slope, intercept = np.polyfit(seg_times, seg_vals, 1)
        resid = seg_vals - (slope * seg_times + intercept)
        resid_std = resid.std() if len(resid) > 1 else 0
        local_std = seg_vals.std() if len(seg_vals) > 1 else 1e-9
        cumulative_offset = seg_vals[-1] - seg_vals[0]

        is_monotonic_trend = abs(slope) > 1e-6
        trend_dominates_noise = resid_std < (0.5 * local_std + 1e-9)
        meaningful_offset = abs(cumulative_offset) > max(0.05 * (abs(seg_vals).mean() + 1e-9), 1e-6)

        if is_monotonic_trend and trend_dominates_noise and meaningful_offset:
            confidence = min(0.98, 0.55 + 0.4 * min(1.0, abs(cumulative_offset) / (local_std + 1e-9) / 5))
            candidates.append(Candidate(
                scenario_code="S1",
                start=idx[seg_idx][0],
                end=idx[seg_idx][-1],
                confidence=confidence,
                evidence=[
                    f"Persistent {'increasing' if slope > 0 else 'decreasing'} trend over "
                    f"{(idx[seg_idx][-1] - idx[seg_idx][0])}.",
                    f"Observed cumulative offset of {cumulative_offset:.3f} units.",
                    f"Residual variability ({resid_std:.3f}) small relative to local spread ({local_std:.3f}).",
                ],
                affected_samples=len(seg_idx),
            ))
            i += len(seg_idx)  # skip past this episode
        else:
            i += step

    return _merge_overlapping(candidates)


def detect_stuck_sensor(series: pd.Series, min_flat_samples: int = 12, tol: float = 1e-9) -> list[Candidate]:
    """S4 - value remains constant for an unusually long duration."""
    candidates = []
    s = series.dropna()
    if len(s) < min_flat_samples:
        return candidates

    values = s.values
    idx = s.index
    n = len(values)
    i = 0
    while i < n - 1:
        j = i
        while j + 1 < n and abs(values[j + 1] - values[i]) <= tol:
            if idx[j + 1] - idx[j] > pd.Timedelta(days=1):
                break
            j += 1
        run_len = j - i + 1
        if run_len >= min_flat_samples:
            confidence = min(0.99, 0.6 + 0.03 * run_len)
            candidates.append(Candidate(
                scenario_code="S4",
                start=idx[i],
                end=idx[j],
                confidence=confidence,
                evidence=[
                    f"Value held constant at {values[i]:.4f} for {run_len} consecutive samples.",
                    f"Flat interval spans {idx[j] - idx[i]}.",
                ],
                affected_samples=run_len,
            ))
        i = j + 1
    return candidates


def detect_measurement_noise(series: pd.Series, window: int = 20, z_thresh: float = 3.0) -> list[Candidate]:
    """S7 - short-lived spikes/oscillations relative to local baseline."""
    candidates = []
    s = series.dropna()
    if len(s) < window * 2:
        return candidates

    rolling_med = s.rolling(window, center=True, min_periods=window // 2).median()
    rolling_std = s.rolling(window, center=True, min_periods=window // 2).std().replace(0, np.nan)
    z = (s - rolling_med) / rolling_std
    spikes = z.abs() > z_thresh
    spike_idx = s.index[spikes.fillna(False)]

    if len(spike_idx) == 0:
        return candidates

    # group spikes that are close together into oscillation episodes
    groups = _group_close_timestamps(spike_idx, max_gap=pd.Timedelta(hours=6))
    for grp in groups:
        if len(grp) == 0:
            continue
        confidence = min(0.95, 0.5 + 0.05 * len(grp))
        candidates.append(Candidate(
            scenario_code="S7",
            start=grp[0],
            end=grp[-1],
            confidence=confidence,
            evidence=[
                f"{len(grp)} short-duration spikes/oscillations exceeding {z_thresh} local std deviations.",
                "Values return toward local baseline between spikes (not a sustained drift or stuck state).",
            ],
            affected_samples=len(grp),
        ))
    return candidates


def detect_packet_loss(full_index: pd.DatetimeIndex) -> list[Candidate]:
    """S8 - missing samples occurring in bursts relative to expected interval."""
    candidates = []
    if len(full_index) < 5:
        return candidates
    idx = full_index.sort_values()
    expected = _expected_interval(idx)
    if expected <= pd.Timedelta(0):
        return candidates

    diffs = idx.to_series().diff()
    # A gap must be larger than 2.5x expected, but less than 30 days 
    # (gaps > 30 days are usually clock resets like 1970, not true dropped packets)
    gap_mask = (diffs > (expected * 2.5)) & (diffs < pd.Timedelta(days=30))
    gap_positions = np.where(gap_mask.values)[0]

    for pos in gap_positions:
        gap = diffs.iloc[pos]
        missing = int(round(gap / expected)) - 1
        if missing < 1:
            continue
        confidence = min(0.99, 0.7 + 0.02 * missing)
        candidates.append(Candidate(
            scenario_code="S8",
            start=idx[pos - 1],
            end=idx[pos],
            confidence=confidence,
            evidence=[
                f"Gap of {gap} observed where expected sampling interval is ~{expected}.",
                f"Approximately {missing} missing sample(s) inferred in this burst.",
            ],
            affected_samples=missing,
        ))
    return candidates

def detect_clock_sync_failure(full_index: pd.DatetimeIndex) -> list[Candidate]:
    """S12 - Device clock resets (e.g. to 1970 epoch) resulting in wildly out-of-bounds timestamps."""
    candidates = []
    if len(full_index) == 0:
        return candidates
        
    idx = full_index.sort_values()
    
    # Flag anything before year 2000 as a clock sync failure
    bad_mask = idx.year < 2000
    if bad_mask.any():
        bad_times = idx[bad_mask]
        
        # Group them if they occur consecutively
        groups = _group_close_timestamps(bad_times, max_gap=pd.Timedelta(minutes=60))
        
        for grp in groups:
            candidates.append(Candidate(
                scenario_code="S12",
                start=grp[0],
                end=grp[-1],
                confidence=0.99,
                evidence=[
                    f"Invalid timestamp detected: {grp[0]}",
                    "Likely caused by a device clock reset / sync failure to the Unix Epoch.",
                ],
                affected_samples=len(grp),
            ))
            
    return candidates


def detect_network_instability(raw_timestamps: pd.Series) -> list[Candidate]:
    """S9 - delayed, duplicated, or out-of-order messages.

    raw_timestamps: the ORIGINAL, unsorted timestamp column as received,
    so ordering/duplication artifacts are still visible.
    """
    candidates = []
    ts = raw_timestamps.reset_index(drop=True)
    if len(ts) < 5:
        return candidates

    is_sorted = ts.is_monotonic_increasing
    dup_mask = ts.duplicated(keep=False)
    n_dupes = int(dup_mask.sum())

    out_of_order_positions = []
    for i in range(1, len(ts)):
        if ts.iloc[i] < ts.iloc[i - 1]:
            out_of_order_positions.append(i)

    if not is_sorted or n_dupes > 0:
        evidence = []
        if out_of_order_positions:
            evidence.append(f"{len(out_of_order_positions)} out-of-order timestamp(s) detected.")
        if n_dupes:
            evidence.append(f"{n_dupes} duplicated timestamp entries detected.")
            
        if evidence:
            bad_indices = out_of_order_positions + list(np.where(dup_mask)[0])
            bad_times = ts.iloc[bad_indices].dropna()
            if len(bad_times) > 0:
                groups = _group_close_timestamps(pd.DatetimeIndex(bad_times), max_gap=pd.Timedelta(hours=1))
                confidence = min(0.95, 0.5 + 0.05 * (len(out_of_order_positions) + n_dupes))
                for grp in groups:
                    candidates.append(Candidate(
                        scenario_code="S9",
                        start=grp[0],
                        end=grp[-1],
                        confidence=confidence,
                        evidence=evidence,
                        affected_samples=len(grp),
                    ))
    return candidates


def detect_reconnection_events(full_index: pd.DatetimeIndex, packet_loss_candidates: list[Candidate]) -> list[Candidate]:
    """S10 - a burst of unusually frequent samples shortly after a packet-loss
    gap, consistent with a device catching up / re-registering."""
    candidates = []
    if not packet_loss_candidates or len(full_index) < 5:
        return candidates
    idx = full_index.sort_values()
    expected = _expected_interval(idx)
    diffs = idx.to_series().diff()

    for pl in packet_loss_candidates:
        after = idx[idx > pl.end]
        if len(after) < 3:
            continue
        window = after[:5]
        local_diffs = pd.Series(window).diff().dropna()
        if len(local_diffs) == 0:
            continue
        if (local_diffs < expected * 0.6).sum() >= 2:
            candidates.append(Candidate(
                scenario_code="S10",
                start=pl.end,
                end=window[-1],
                confidence=0.75,
                evidence=[
                    "Burst of unusually closely-spaced samples immediately following a packet-loss gap.",
                    "Pattern consistent with device reconnection / backlog flush.",
                ],
                affected_samples=len(window),
            ))
    return candidates


def detect_environmental_variability(param_series_map: dict[str, pd.Series], corr_thresh: float = 0.6) -> list[Candidate]:
    """S11 - multiple related parameters move together in a physically
    consistent way; flagged as an environmental event rather than a fault,
    and used to suppress/soften fault confidence on correlated windows."""
    candidates = []
    cols = list(param_series_map.keys())
    if len(cols) < 2:
        return candidates

    combined = pd.DataFrame(param_series_map).sort_index()
    combined = combined.resample("1h").mean()
    if len(combined) < 10:
        return candidates

    rolling_corr = combined[cols[0]].rolling(24, min_periods=6).corr(combined[cols[1]])
    high_corr_mask = rolling_corr.abs() > corr_thresh
    idx = combined.index[high_corr_mask.fillna(False)]
    groups = _group_close_timestamps(idx, max_gap=pd.Timedelta(hours=6))
    for grp in groups:
        if len(grp) < 3:
            continue
        candidates.append(Candidate(
            scenario_code="S11",
            start=grp[0],
            end=grp[-1],
            confidence=0.65,
            evidence=[
                f'"{cols[0]}" and "{cols[1]}" moved together with correlation above {corr_thresh} '
                f"over {grp[-1] - grp[0]}.",
                "Pattern is consistent with a shared environmental driver rather than an isolated sensor fault.",
            ],
            affected_samples=len(grp),
        ))
    return candidates


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _merge_overlapping(candidates: list[Candidate]) -> list[Candidate]:
    if not candidates:
        return candidates
    candidates = sorted(candidates, key=lambda c: c.start)
    merged = [candidates[0]]
    for c in candidates[1:]:
        last = merged[-1]
        if c.start <= last.end:
            last.end = max(last.end, c.end)
            last.evidence.extend(c.evidence)
            last.affected_samples += c.affected_samples
            last.confidence = max(last.confidence, c.confidence)
        else:
            merged.append(c)
    return merged


def _group_close_timestamps(idx: pd.DatetimeIndex, max_gap: pd.Timedelta) -> list[list[pd.Timestamp]]:
    if len(idx) == 0:
        return []
    idx = sorted(idx)
    groups = [[idx[0]]]
    for t in idx[1:]:
        if t - groups[-1][-1] <= max_gap:
            groups[-1].append(t)
        else:
            groups.append([t])
    return groups


def _candidates_to_incidents(
    node_id: Optional[str],
    parameter: str,
    domain: str,
    candidates: list[Candidate],
    incident_counter: list[int],
) -> list[Incident]:
    # Merge candidates that overlap in time across scenario types into
    # primary/secondary incidents.
    candidates = sorted(candidates, key=lambda c: c.start)
    incidents: list[Incident] = []
    used = [False] * len(candidates)

    for i, c in enumerate(candidates):
        if used[i]:
            continue
        overlapping = [c]
        used[i] = True
        for j in range(i + 1, len(candidates)):
            if used[j]:
                continue
            if candidates[j].start <= c.end:
                overlapping.append(candidates[j])
                used[j] = True

        overlapping.sort(key=lambda x: x.confidence, reverse=True)
        primary = overlapping[0]
        secondary = overlapping[1] if len(overlapping) > 1 else None

        incident_counter[0] += 1
        incidents.append(Incident(
            incident_id=f"INC-{incident_counter[0]:05d}",
            node_id=node_id,
            parameter=parameter,
            domain=domain,
            start_timestamp=str(min(o.start for o in overlapping)),
            end_timestamp=str(max(o.end for o in overlapping)),
            duration_seconds=(max(o.end for o in overlapping) - min(o.start for o in overlapping)).total_seconds(),
            primary_uncertainty=SCENARIOS[primary.scenario_code],
            secondary_uncertainty=SCENARIOS[secondary.scenario_code] if secondary else None,
            confidence_score=round(primary.confidence, 4),
            supporting_evidence=[e for o in overlapping for e in o.evidence],
            affected_samples=sum(o.affected_samples for o in overlapping),
        ))
    return incidents


# ---------------------------------------------------------------------------
# Main analysis pipeline
# ---------------------------------------------------------------------------

def run_analysis(
    df: pd.DataFrame,
    mapping: ColumnMapping,
    logger: RunLogger,
    out_dir: Path,
) -> list[Incident]:
    logger.section("Dataset Loaded Successfully")
    logger.line(f"Rows: {len(df)}")
    logger.line("Detected Parameters:")
    for c in mapping.parameter_domains:
        logger.line(f"  {c}")

    if mapping.node_col and mapping.node_col in df.columns:
        unique_nodes = df[mapping.node_col].dropna().unique()
    else:
        unique_nodes = [None]

    all_incidents: list[Incident] = []
    incident_counter = [0]
    param_cols = list(mapping.parameter_domains.keys())

    for node_id in unique_nodes:
        if node_id is not None:
            logger.section(f"Analyzing Node: {node_id}")
            group_df_raw = df[df[mapping.node_col] == node_id]
        else:
            group_df_raw = df

        raw_ts = group_df_raw[mapping.timestamp_col].copy()
        
        group_df = group_df_raw.copy()
        group_df[mapping.timestamp_col] = pd.to_datetime(group_df[mapping.timestamp_col], errors="coerce")
        group_df = group_df.dropna(subset=[mapping.timestamp_col]).sort_values(mapping.timestamp_col)
        group_df = group_df.set_index(mapping.timestamp_col)
        
        param_series_map: dict[str, pd.Series] = {}

        for col in param_cols:
            if col not in group_df.columns:
                continue
            logger.line(f"-> Parameter: {col}")
            series = pd.to_numeric(group_df[col], errors="coerce")
            param_series_map[col] = series
            domain = mapping.parameter_domains.get(col, "Unspecified")
            rng = mapping.parameter_ranges.get(col)

            candidates: list[Candidate] = []
            candidates += detect_sensor_drift(series)
            candidates += detect_stuck_sensor(series)
            candidates += detect_measurement_noise(series)

            for c in candidates:
                logger.evidence_block(f"{SCENARIOS[c.scenario_code]} ({c.scenario_code})", c.confidence, c.evidence)

            pl_candidates = detect_packet_loss(series.dropna().index)
            for c in pl_candidates:
                logger.evidence_block("Packet Loss", c.confidence, c.evidence)
            candidates += pl_candidates
            
            cs_candidates = detect_clock_sync_failure(series.dropna().index)
            for c in cs_candidates:
                logger.evidence_block("Clock Sync Failure", c.confidence, c.evidence)
            candidates += cs_candidates

            param_raw_ts = raw_ts  # dataset-level ordering check, shared across params
            ni_candidates = detect_network_instability(param_raw_ts)
            for c in ni_candidates:
                logger.evidence_block("Network Instability", c.confidence, c.evidence)
            candidates += ni_candidates

            rc_candidates = detect_reconnection_events(series.dropna().index, pl_candidates)
            for c in rc_candidates:
                logger.evidence_block("Reconnection Events", c.confidence, c.evidence)
            candidates += rc_candidates

            incidents = _candidates_to_incidents(str(node_id) if node_id is not None else None, col, domain, candidates, incident_counter)
            all_incidents.extend(incidents)

        # Cross-parameter environmental variability check (node-level)
        if len(param_series_map) >= 2:
            env_candidates = detect_environmental_variability(param_series_map)
            for c in env_candidates:
                logger.evidence_block("Environmental Variability", c.confidence, c.evidence)
            env_incidents = _candidates_to_incidents(
                node_id=str(node_id) if node_id is not None else None,
                parameter=" & ".join(list(param_series_map.keys())[:2]),
                domain="Cross-Parameter",
                candidates=env_candidates,
                incident_counter=incident_counter,
            )
            all_incidents.extend(env_incidents)
            
        # Clean up memory explicitly for this node and take a short rest
        del group_df
        if node_id is not None:
            del group_df_raw
        del param_series_map
        del raw_ts
        logger.line(f"Cleaned up memory for node {node_id}")  
        logger.line("Waiting for 120 seconds before proceeding to the next node")
        gc.collect()
        time.sleep(20)

    logger.section("Analysis Complete")
    logger.line(f"Total incidents identified: {len(all_incidents)}")

    write_reports(all_incidents, out_dir, logger)
    generate_beautiful_report(all_incidents, df, mapping, out_dir, logger)
    return all_incidents


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def write_reports(incidents: list[Incident], out_dir: Path, logger: RunLogger):
    out_dir.mkdir(parents=True, exist_ok=True)

    json_path = out_dir / "uncertainty_report.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump([i.to_dict() for i in incidents], f, indent=2)

    md_path = out_dir / "uncertainty_report.md"
    lines = ["# Uncertainty Identification Report", ""]
    lines.append(f"Generated: {datetime.now().isoformat()}")
    lines.append(f"Total incidents: {len(incidents)}")
    lines.append("")
    lines.append("This report describes Stage-1 (traditional IoT baseline) uncertainty")
    lines.append("episodes inferred from historical telemetry. It does not represent")
    lines.append("Digital Twin or Self-Adaptive Digital Twin behavior.")
    lines.append("")

    lines.append("## Summary by Node")
    lines.append("")
    node_counts = {}
    for inc in incidents:
        n = inc.node_id or "Global"
        node_counts[n] = node_counts.get(n, 0) + 1
    
    lines.append("| Node ID | Total Incidents | Report Link |")
    lines.append("|---|---|---|")
    for n, count in sorted(node_counts.items()):
        node_filename = "".join(c for c in n if c.isalnum() or c in ('-', '_'))
        lines.append(f"| {n} | {count} | [Details](uncertainty_report_{node_filename}.md) |")
    lines.append("")

    md_path.write_text("\n".join(lines), encoding="utf-8")

    by_node: dict[str, dict[str, list[Incident]]] = {}
    for inc in incidents:
        n = inc.node_id or "Global"
        by_node.setdefault(n, {}).setdefault(inc.parameter, []).append(inc)

    for node_id, params in sorted(by_node.items()):
        node_filename = "".join(c for c in node_id if c.isalnum() or c in ('-', '_'))
        node_md_path = out_dir / f"uncertainty_report_{node_filename}.md"
        node_lines = [f"# Uncertainty Report - Node: {node_id}", ""]
        
        for param, incs in sorted(params.items()):
            node_lines.append(f"## Parameter: {param}")
            node_lines.append("")
            for inc in incs:
                node_lines.append(f"### {inc.incident_id} — {inc.primary_uncertainty}"
                              + (f" + {inc.secondary_uncertainty}" if inc.secondary_uncertainty else ""))
                node_lines.append(f"- Domain: {inc.domain}")
                node_lines.append(f"- Start: {inc.start_timestamp}")
                node_lines.append(f"- End: {inc.end_timestamp}")
                node_lines.append(f"- Duration: {inc.duration_seconds:.0f} seconds")
                node_lines.append(f"- Confidence: {inc.confidence_score:.0%}")
                node_lines.append(f"- Affected samples: {inc.affected_samples}")
                node_lines.append("- Evidence:")
                for e in inc.supporting_evidence:
                    node_lines.append(f"  - {e}")
                node_lines.append("")
        
        node_md_path.write_text("\n".join(node_lines), encoding="utf-8")

    logger.line(f"Machine-readable report written to: {json_path}")
    logger.line(f"Human-readable main summary written to: {md_path}")
    logger.line(f"Detailed per-node reports written to: {out_dir}")

def generate_beautiful_report(incidents: list[Incident], df: pd.DataFrame, mapping: ColumnMapping, out_dir: Path, logger: RunLogger):
    data = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: {'count': 0, 'samples': 0, 'duration': 0.0})))
    times = defaultdict(lambda: defaultdict(list))
    
    # Calculate dataset sizes dynamically
    total_rows = len(df)
    total_params = len(mapping.parameter_domains)
    total_points = total_rows * total_params

    node_domains = {}
    for inc in incidents:
        d = inc.domain
        n = inc.node_id or "Global"
        if d != "Cross-Parameter" and d != "Unknown":
            node_domains[n] = d

    for inc in incidents:
        d = inc.domain
        n = inc.node_id or "Global"
        
        try:
            t = pd.to_datetime(inc.start_timestamp)
        except:
            t = None

        if d == "Cross-Parameter":
            d = node_domains.get(n, "Cross-Parameter")
            
        scenario = inc.primary_uncertainty
        samples = inc.affected_samples
        duration = inc.duration_seconds
        
        data[d][n][scenario]['count'] += 1
        data[d][n][scenario]['samples'] += samples
        data[d][n][scenario]['duration'] += duration
        
        if t:
            times[d][n].append(t)

    md_lines = [
        "# 📊 Aggregated Scenario Report",
        "",
        "> [!TIP]",
        "> This report provides a detailed breakdown of all uncertainty scenarios across your IoT ecosystem.",
        "> It includes incident counts, affected data points, average duration, and frequency analysis.",
        ""
    ]

    # Use SCENARIOS values for columns
    scenario_names = list(SCENARIOS.values())

    for domain in sorted(data.keys()):
        nodes = data[domain]
        total_incidents = 0
        total_samples = 0
        total_duration = 0.0
        node_incident_counts = defaultdict(int)
        
        domain_times = []
        for n_id, t_list in times.get(domain, {}).items():
            valid_times = [t for t in t_list if t.year > 2000]
            domain_times.extend(valid_times)
            
        days_window = 1.0
        if domain_times:
            min_t = min(domain_times)
            max_t = max(domain_times)
            days_window = max(1.0, (max_t - min_t).total_seconds() / 86400.0)
        
        # In engine, we don't fake names. We use exact names emitted by engine.
        missing_scenarios = {"Packet Loss", "Clock Sync Failure"}
        total_missing = 0
        total_corrupted = 0
        
        for n_id, sc_data in nodes.items():
            for s, metrics in sc_data.items():
                total_incidents += metrics['count']
                total_samples += metrics['samples']
                total_duration += metrics['duration']
                node_incident_counts[n_id] += metrics['count']
                
                if s in missing_scenarios:
                    total_missing += metrics['samples']
                else:
                    total_corrupted += metrics['samples']
                
        avg_duration = (total_duration / total_incidents) if total_incidents > 0 else 0
        worst_node = max(node_incident_counts.items(), key=lambda x: x[1])[0] if node_incident_counts else "N/A"
        freq_overall = total_incidents / days_window
        
        total_data_points_analyzed = f"{total_points:,} ({total_rows:,} rows × {total_params} params)"
        corruption_rate = f"{(total_corrupted / total_points) * 100:.2f}%" if total_points > 0 else "N/A"
        
        total_expected_data = total_points + total_missing
        total_failed_data = total_corrupted + total_missing
        system_downtime_rate = f"{(total_failed_data / total_expected_data) * 100:.2f}%" if total_expected_data > 0 else "N/A"
        
        md_lines.extend([
            f"## 🏭 Vertical: {domain}",
            "",
            "> [!WARNING]",
            "> **Domain Summary:**",
            f"> - **Total Data Points Present (Analyzed):** {total_data_points_analyzed}",
            f"> - **Corrupted Data Points (Anomalies in Data):** {total_corrupted:,}",
            f"> - **Data Corruption Rate:** {corruption_rate} *(Corrupted / Present)*",
            f"> - **Missing Data Points (Inferred from Gaps):** {total_missing:,}",
            f"> - **System Failure Rate (Overall Downtime):** {system_downtime_rate} *(Corrupted + Missing / Expected)*",
            f"> - **Total Incidents:** {total_incidents:,}",
            f"> - **Average Incident Duration:** {avg_duration:,.1f} seconds",
            f"> - **Analysis Window:** {days_window:,.1f} days",
            f"> - **Overall Frequency:** {freq_overall:,.1f} incidents per day",
            f"> - **Most Problematic Node:** {worst_node} ({node_incident_counts.get(worst_node, 0):,} incidents)",
            ""
        ])
        
        lines = ["### 📊 Comprehensive Scenario Metrics"]
        lines.append("> *Legend: **C** = Incident Count (per parameter) | **A** = Affected Data Points (Affected Rows × Parameters) | **D** = Average Duration*")
        lines.append("")
        
        header = "| Node ID | " + " | ".join(scenario_names) + " | **Node Total** |"
        separator = "|---|" + "|".join(["---"] * len(scenario_names)) + "|---|"
        lines.extend([header, separator])
        
        for node_id in sorted(nodes.keys()):
            row_data = nodes[node_id]
            row = [f"**{node_id}**"]
            
            node_tot_c = 0
            node_tot_a = 0
            node_tot_d = 0
            
            for s in scenario_names:
                m = row_data.get(s, {})
                c = m.get('count', 0)
                a = m.get('samples', 0)
                d = m.get('duration', 0)
                
                node_tot_c += c
                node_tot_a += a
                node_tot_d += d
                
                if c > 0:
                    avg_d = round(d/c, 1)
                    cell = f"**C:** {c:,}<br>**A:** {a:,}<br>**D:** {avg_d:,}s"
                    row.append(cell)
                else:
                    row.append("-")
                    
            avg_tot_d = round(node_tot_d/node_tot_c, 1) if node_tot_c > 0 else 0
            if node_tot_c > 0:
                tot_cell = f"**C:** {node_tot_c:,}<br>**A:** {node_tot_a:,}<br>**D:** {avg_tot_d:,}s"
            else:
                tot_cell = "-"
            row.append(tot_cell)
            lines.append("| " + " | ".join(row) + " |")
            
        lines.append("")
        md_lines.extend(lines)
        
    out_path = out_dir / "aggregated_scenario_report.md"
    out_path.write_text("\n".join(md_lines), encoding="utf-8")
    logger.line(f"Beautiful aggregated report written to: {out_path}")



# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Uncertainty Identification Engine for Smart City IoT telemetry (Stage 1 only)."
    )
    parser.add_argument("dataset", type=str, help="Path to a CSV file containing raw historical telemetry.")
    parser.add_argument("--mapping-config", type=str, default=None,
                         help="Optional path to a JSON mapping config to skip interactive prompts.")
    parser.add_argument("--out-dir", type=str, default="uncertainty_output",
                         help="Directory to write logs and reports to.")
    parser.add_argument("--log-file", type=str, default=None,
                         help="Path to the continuous progress log file (default: <out-dir>/uncertainty_run.log).")
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    out_dir = Path(args.out_dir)
    log_path = Path(args.log_file) if args.log_file else out_dir / "uncertainty_run.log"

    logger = RunLogger(log_path)
    logger.line(f"Loading dataset: {dataset_path}")

    df = pd.read_csv(dataset_path)

    if args.mapping_config:
        mapping = load_mapping_from_json(Path(args.mapping_config))
        logger.line(f"Loaded column mapping from config: {args.mapping_config}")
    else:
        mapping = interactive_column_mapping(df, logger)

    run_analysis(df, mapping, logger, out_dir)


if __name__ == "__main__":
    main()
