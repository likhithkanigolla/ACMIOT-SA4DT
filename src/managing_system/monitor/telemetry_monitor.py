"""
Telemetry Monitor
=================

Paper reference: Section 4.4 — Monitor

Responsibility (SRP): ingest one row of streaming telemetry, construct a
SensorReading with staleness/lag tags, and record the monitoring latency T_M.

This module does NOT classify faults, compute risk scores, generate candidates,
or dispatch commands. Those belong to Analyse, Plan, and Execute respectively.

Extracted from: experiment_runner.py (original), lines 37-57 (row parsing and
SensorReading construction) and lines 71-73 (monitoring latency measurement).
"""

from __future__ import annotations

import numpy as np
from typing import Optional

from src.managing_system.shared_knowledge.knowledge_store import SensorReading


# ---------------------------------------------------------------------------
# Physical delta state (mutable per-trace, managed by the caller / runner)
# ---------------------------------------------------------------------------

class PhysicalState:
    """
    Accumulates the physical effect deltas that persist across episodes within
    a single trace run (e.g., AC cools the room, effect persists for tau steps).

    This is NOT part of the Shared Knowledge store — it represents the evolving
    true physical environment state during a simulation trace.
    """
    def __init__(self):
        self.temp_delta: float = 0.0
        self.co2_delta: float = 0.0
        self.c3_temp_offset: float = 0.0
        self.c3_co2_offset: float = 0.0

    def apply_natural_decay(self, tau: float) -> None:
        """Natural decay of physical deltas between fault episodes (Eq. 4 analog)."""
        self.temp_delta *= (1.0 - 1.0 / tau)
        self.co2_delta *= (1.0 - 1.0 / tau)

    def clear_recalibration(self) -> None:
        """Reset permanent calibration offsets when a fault episode ends."""
        self.c3_temp_offset = 0.0
        self.c3_co2_offset = 0.0


# ---------------------------------------------------------------------------
# Monitor: telemetry ingestion
# ---------------------------------------------------------------------------

class TelemetryMonitor:
    """
    Paper §4.4 — Monitor: "ingests streaming telemetry, appends quality /
    staleness tags, and records T_M."

    One call to `ingest_row()` per MAPE-K loop iteration produces a
    `SensorReading` ready for the Analyse phase.
    """

    # Simulated sensor-to-gateway monitoring latency (ms) — Gaussian noise
    _LATENCY_BASE_MS: float = 5.0
    _LATENCY_STD_MS: float = 1.0

    def ingest_row(
        self,
        row: dict,
        episode_index: int,
        physical_state: PhysicalState,
    ) -> tuple[SensorReading, float]:
        """
        Ingest one telemetry row and return:
          (SensorReading perceived_reading, float t_m_ms)

        Parameters
        ----------
        row : dict-like
            One CSV row with keys: temperature, co2_ppm, pir, anomaly_label.
        episode_index : int
            Current episode (row index in the trace).
        physical_state : PhysicalState
            Current accumulated physical deltas (from prior Execute outputs).

        Returns
        -------
        SensorReading
            Perceived reading: raw + physical deltas + calibration offsets.
        float
            T_M — monitoring latency in milliseconds.
        """
        label = row["anomaly_label"]

        # Extract raw sensor values (None if missing — simulates packet loss)
        raw_temp: Optional[float] = (
            float(row["temperature"]) if not _is_nan(row["temperature"]) else None
        )
        raw_co2: Optional[float] = (
            float(row["co2_ppm"]) if not _is_nan(row["co2_ppm"]) else None
        )
        raw_pir: int = int(row["pir"]) if not _is_nan(row["pir"]) else 0

        # Apply accumulated physical deltas + recalibration offsets to produce
        # the perceived (DT-visible) reading — see experiment_runner.py L44-46
        p_temp = (
            raw_temp + physical_state.temp_delta + physical_state.c3_temp_offset
            if raw_temp is not None
            else None
        )
        p_co2 = (
            raw_co2 + physical_state.co2_delta + physical_state.c3_co2_offset
            if raw_co2 is not None
            else None
        )

        # S9 (Network Instability) injects a 180-second synchronisation lag
        # Paper §4.2: "sync lag d; applies sync-penalty discount" (Eq. 1)
        lag_seconds: float = 180.0 if "S9" in label else 0.0

        perceived_reading = SensorReading(
            temperature=p_temp,
            co2=p_co2,
            occupancy=raw_pir,
            timestamp=float(episode_index) * 60.0,
            lag_seconds=lag_seconds,
        )

        # Simulated monitoring latency (sensor to gateway) — T_M
        t_m = float(self._LATENCY_BASE_MS + np.random.normal(0, self._LATENCY_STD_MS))

        return perceived_reading, t_m


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _is_nan(value) -> bool:
    """Safe NaN check that works for both float and non-float types."""
    try:
        import math
        return math.isnan(float(value))
    except (TypeError, ValueError):
        return True
