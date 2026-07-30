"""
OTA Dispatcher — Command Orchestrator
======================================

Paper reference: Section 4.2 — Command Orchestrator

Responsibility (SRP): simulate the OTA dispatch of a command to the physical
actuator and return the execution latency T_E.

Implementation status (see docs/missing_components.md §2.2):
  The paper describes real OTA dispatch to ESP32 microcontrollers with hardware
  ACK timestamps. What is implemented here is a simulated OTA latency:
      T_E ~ N(50 ms, 5 ms)  if a candidate was selected
      T_E = 0               if no action taken

  No real protocol-compliant payload formatting or ESP32 communication is
  implemented. T_E values in the paper are simulated, not from real hardware.

Extracted from: experiment_runner.py (original), lines 85-88.
"""

from __future__ import annotations

import json
import time
from typing import Optional, Dict, Any
import urllib.request
import urllib.error

import numpy as np


class OTADispatcher:
    """
    Paper §4.2 — Command Orchestrator: "translates abstract candidate identifiers
    into concrete hardware actuator set-points, formats protocol-compliant OTA
    payloads, dispatches commands asynchronously to physical controllers, and
    captures precise hardware acknowledgment timestamps."

    When running in offline simulation (default replication package mode), OTA
    round-trip latency is simulated as a Gaussian T_E ~ N(50ms, 5ms).

    REAL-WORLD HARDWARE DEPLOYMENT (Raspberry Pi / ESP32 Gateway):
      To run against physical actuators, initialize with a live HTTP/REST endpoint
      (e.g., live_endpoint_url="http://192.168.1.100:5000/actuate"). The dispatcher
      will automatically translate abstract candidate IDs into JSON control payloads,
      post them to the edge gateway, and measure true hardware ACK latency in ms.
    """

    # Simulated OTA latency distribution (paper §5: ~50ms observed round-trip)
    _BASE_LATENCY_MS: float = 50.0
    _LATENCY_STD_MS: float = 5.0

    def __init__(self, live_endpoint_url: Optional[str] = None):
        """
        Parameters
        ----------
        live_endpoint_url : Optional[str]
            HTTP/REST endpoint of the live IoT Edge Gateway (e.g., Raspberry Pi).
            If None, defaults to Gaussian simulation latency.
        """
        self._live_endpoint = live_endpoint_url

    def translate_to_payload(self, candidate: str) -> Dict[str, Any]:
        """
        Translate abstract adaptation candidates (C1-C6) into concrete hardware
        actuator set-point payloads (Paper §4.2).
        """
        payload_map = {
            "C1": {"actuator": "FAN_PWM", "command": "SET_DUTY_CYCLE", "value": 1.0, "target": "temperature"},
            "C2": {"actuator": "EXHAUST_FAN", "command": "SET_STATE", "value": "ON", "target": "co2"},
            "C3": {"actuator": "SENSOR_CALIBRATE", "target": "SI7021_TEMP", "command": "OFFSET_CORRECT", "nominal_val": 25.0},
            "C4": {"actuator": "SENSOR_CALIBRATE", "target": "SGP30_CO2", "command": "OFFSET_CORRECT", "nominal_val": 400.0},
            "C5": {"actuator": "NONE", "command": "DEFER_ACTION", "reason": "aleatoric_noise_bridging"},
            "C6": {"actuator": "AUX_FAN_PWM", "command": "REROUTE_ON", "value": 1.0, "target": "temperature"},
        }
        return payload_map.get(candidate, {"actuator": "UNKNOWN", "raw_candidate": candidate})

    def dispatch(self, candidate: Optional[str]) -> float:
        """
        Dispatch `candidate` to the physical actuator (or simulated equivalent).

        Parameters
        ----------
        candidate : str or None — if None, no command is sent (T_E = 0).

        Returns
        -------
        float : T_E — measured or simulated OTA latency in milliseconds.
        """
        if candidate is None:
            return 0.0

        # --- LIVE HARDWARE DEPLOYMENT MODE ---
        if self._live_endpoint:
            payload = self.translate_to_payload(candidate)
            data = json.dumps({"candidate": candidate, "payload": payload, "timestamp": time.time()}).encode("utf-8")
            req = urllib.request.Request(
                self._live_endpoint,
                data=data,
                headers={"Content-Type": "application/json"}
            )
            start_ns = time.time_ns()
            try:
                with urllib.request.urlopen(req, timeout=5.0) as resp:
                    _ = resp.read()  # Wait for hardware acknowledgement (ACK)
                t_e = (time.time_ns() - start_ns) / 1_000_000.0
                return float(t_e)
            except (urllib.error.URLError, TimeoutError) as e:
                print(f"[OTADispatcher] Warning: Live endpoint {self._live_endpoint} unreachable ({e}). Fallback to simulated latency.")

        # --- OFFLINE REPRODUCTION MODE (Simulated T_E ~ N(50ms, 5ms)) ---
        t_e = float(self._BASE_LATENCY_MS + np.random.normal(0, self._LATENCY_STD_MS))
        return t_e
