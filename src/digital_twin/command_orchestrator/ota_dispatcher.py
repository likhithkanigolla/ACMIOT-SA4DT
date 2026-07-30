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

from typing import Optional

import numpy as np


class OTADispatcher:
    """
    Paper §4.2 — Command Orchestrator: "translates abstract candidate identifiers
    into concrete hardware actuator set-points, formats protocol-compliant OTA
    payloads, dispatches commands asynchronously to physical controllers, and
    captures precise hardware acknowledgment timestamps."

    Current implementation: OTA round-trip latency is simulated as a Gaussian.
    See docs/missing_components.md §2.2 for a full accounting of what is absent.
    """

    # Simulated OTA latency distribution (paper §5: ~50ms observed round-trip)
    _BASE_LATENCY_MS: float = 50.0
    _LATENCY_STD_MS: float = 5.0

    def dispatch(self, candidate: Optional[str]) -> float:
        """
        Simulate dispatching `candidate` to the physical actuator.

        Parameters
        ----------
        candidate : str or None — if None, no command is sent (T_E = 0).

        Returns
        -------
        float : T_E — simulated OTA latency in milliseconds.

        Extracted from: experiment_runner.py lines 85-88.
        """
        if candidate is None:
            return 0.0

        # T_E ~ N(50ms, 5ms)
        t_e = float(self._BASE_LATENCY_MS + np.random.normal(0, self._LATENCY_STD_MS))
        return t_e
