# Real-World Hardware Deployment Guide (Raspberry Pi & ESP32)

This guide explains how to transition from offline simulation/replication mode (using synthetic telemetry traces and simulated Gaussian latency) to **real-world closed-loop physical actuation** using an IoT Edge Gateway (such as a Raspberry Pi running an HTTP/REST server communicating with ESP32 sensor/actuator nodes via WiFi, BLE, or Zigbee/oneM2M).

---

## 1. Architecture: Connecting Edge Hardware to MAPE-K + DT

When deployed on real smart building hardware, the replication package connects cleanly to your hardware layers without modifying the core MAPE-K control loop or Digital Twin math:

```
  +-------------------------------------------------------------+
  |              MAPE-K & DIGITAL TWIN CONTROLLER               |
  |                (Server or Raspberry Pi 4)                   |
  |                                                             |
  |   [Monitor] -------> [Analyse/Plan/DT] -------> [Execute]   |
  +-------^--------------------------------------------|--------+
          |                                            |
     HTTP GET (Telemetry)                     HTTP POST (Set-points)
   (live-telemetry-url)                      (live-actuator-url)
          |                                            |
  +-------|--------------------------------------------v--------+
  |               EDGE GATEWAY / DEVICE BROKER                  |
  |             (Raspberry Pi Lightweight Server)               |
  |                                                             |
  |      [Sensor Buffer]                   [PWM / GPIO Driver]  |
  +-------^--------------------------------------------|--------+
          | I2C / UART / WiFi MQTT                     | GPIO / I2C / PWM
  +-------|--------------------------------------------v--------+
  |      ESP32 / SI7021 (Temp) / SGP30 (CO2) / PIR / FAN Motor  |
  +-------------------------------------------------------------+
```

---

## 2. Connecting via Command-Line Flags

To test or deploy against live hardware, simply pass the URLs of your edge controller endpoints to `run.py`:

```bash
# Run SA-DT adaptation mode against a real Raspberry Pi on the local network
python run.py --mode sa_dt \
              --live-telemetry-url "http://192.168.1.100:5000/telemetry" \
              --live-actuator-url "http://192.168.1.100:5000/actuate" \
              --trace
```

### Behavior Under Live Connection:
1. **Live Sensor Ingestion (`TelemetryMonitor`)**:
   - The Monitor makes an HTTP GET request to `--live-telemetry-url`.
   - It captures the **true network and sensor round-trip monitoring latency ($T_M$)** using precise monotonic hardware clock timers (`time.time_ns()`).
   - If the endpoint temporarily connection drops or timeouts, it logs a warning and gracefully falls back to safety baseline interpolation.
2. **Hardware Actuator Dispatch (`OTADispatcher`)**:
   - When an adaptation candidate ($C_1 - C_6$) is selected by the Decision Engine, `OTADispatcher` automatically translates the abstract identifier into concrete hardware actuator control set-points.
   - It dispatches an HTTP POST JSON payload to `--live-actuator-url` and captures the **exact physical hardware acknowledgment (ACK) timestamp ($T_E$)**.

---

## 3. Hardware Set-Point Translation Protocol

When `--live-actuator-url` is active, abstract adaptation commands are translated by `OTADispatcher.translate_to_payload()` into standard JSON control structures sent to your controller:

| Candidate | Description | Transmitted JSON Payload |
|-----------|-------------|--------------------------|
| **$C_1$** | Increase main cooling/HVAC airflow | `{"actuator": "FAN_PWM", "command": "SET_DUTY_CYCLE", "value": 1.0, "target": "temperature"}` |
| **$C_2$** | Activate CO₂ ventilation exhaust | `{"actuator": "EXHAUST_FAN", "command": "SET_STATE", "value": "ON", "target": "co2"}` |
| **$C_3$** | Recalibrate thermal sensor (SI7021) | `{"actuator": "SENSOR_CALIBRATE", "target": "SI7021_TEMP", "command": "OFFSET_CORRECT", "nominal_val": 25.0}` |
| **$C_4$** | Recalibrate air quality sensor (SGP30) | `{"actuator": "SENSOR_CALIBRATE", "target": "SGP30_CO2", "command": "OFFSET_CORRECT", "nominal_val": 400.0}` |
| **$C_5$** | No-op / Defer actuation (Aleatoric bypass) | `{"actuator": "NONE", "command": "DEFER_ACTION", "reason": "aleatoric_noise_bridging"}` |
| **$C_6$** | Reroute to backup secondary ventilation | `{"actuator": "AUX_FAN_PWM", "command": "REROUTE_ON", "value": 1.0, "target": "temperature"}` |

---

## 4. Reference Raspberry Pi Edge Server Snippet

To replicate this physical evaluation on a Raspberry Pi or equivalent controller, deploy a simple Python adapter (using lightweight Flask or FastAPI) on your gateway device to serve sensor readings and interface with GPIO / MQTT:

```python
# Save as edge_gateway.py on your Raspberry Pi
from flask import Flask, jsonify, request
import time

app = Flask(__name__)

# Simulated hardware state / buffer (in production, read via smbus2, gpiozero, or paho-mqtt)
current_sensors = {
    "temperature": 27.2,
    "co2_ppm": 750.0,
    "pir": 1,
    "anomaly_label": "NORMAL"
}

@app.route("/telemetry", methods=["GET"])
def get_telemetry():
    # Return latest sensor reads from I2C / UART buffer
    return jsonify(current_sensors), 200

@app.route("/actuate", methods=["POST"])
def actuate_hardware():
    data = request.json
    candidate = data.get("candidate")
    payload = data.get("payload", {})
    
    actuator = payload.get("actuator")
    command = payload.get("command")
    val = payload.get("value")
    
    print(f"[HW COMMAND RECEIVED] Candidate={candidate} -> Actuator={actuator} Command={command} Value={val}")
    
    # Example physical actuation (e.g., controlling PWM via gpiozero / pigpio)
    if actuator == "FAN_PWM" and command == "SET_DUTY_CYCLE":
        # fan_pwm.value = val
        pass
    elif actuator == "SENSOR_CALIBRATE":
        # Apply software calibration offset in local edge memory
        pass
        
    # Return hardware ACK after physical driver confirms operation
    return jsonify({"status": "ACK", "timestamp": time.time()}), 200

if __name__ == "__main__":
    # Listen on all interfaces on port 5000
    app.run(host="0.0.0.0", port=5000)
```

By substituting your live IP address into `--live-telemetry-url` and `--live-actuator-url`, the Digital Twin simulation validation gate automatically evaluates physical state projections in real-time before actuating hardware set-points in your laboratory environment.
