# Thresholds Reference

This file lists all threshold constants (real values with units) used across the verticals.

## Summary Table (all verticals)

| Vertical | Metric | Good (<=) | Neutral (range) | Bad (>) | Unit | Constant(s) |
|---|---|---:|---|---:|---|---|
| Air Quality | AQI | 50 | 50–200 | >200 | — | `aqAqiLow=50`, `aqAqiHigh=200` |
| Air Quality | PM2.5 | 30 | 30–100 | >100 | ppm | `aqPm25Low=30`, `aqPm25High=100` |
| Air Quality | PM10 | 50 | 50–250 | >250 | ppm | `aqPm10Low=50`, `aqPm10High=250` |
| Air Quality | Noise | 45 | 45–70 | >70 | dB | `aqNoiseLow=45`, `aqNoiseHigh=70` |
| Air Quality | Humidity | within ±10% of 50 | ±10–20% | beyond ±20% | % | `aqHumidityIdeal=50`, `aqHumidityFirstSpan=10`, `aqHumiditySecondSpan=20` |
| Air Quality | Temperature | within ±5°C of 25 | ±5–10°C | beyond ±10°C | °C | `aqTempIdeal=25`, `aqTempFirstSpan=5`, `aqTempSecondSpan=10` |
| SmartRoom Air Quality | AQI | 50 | 50–150 | >150 | — | `srAqAqiLow=50`, `srAqAqiHigh=150` |
| SmartRoom Air Quality | CO₂ | 700 | 700–1000 | >1000 | ppm | `srAqCo2Low=700`, `srAqCo2High=1000` |
| SmartRoom Air Quality | PM2.5 | 30 | 30–100 | >100 | ppm | `srAqPm25Low=30`, `srAqPm25High=100` |
| SmartRoom Air Quality | PM10 | 50 | 50–250 | >250 | ppm | `srAqPm10Low=50`, `srAqPm10High=250` |
| SmartRoom Air Quality | Noise | 45 | 45–70 | >70 | dB | `srAqNoiseLow=45`, `srAqNoiseHigh=70` |
| SmartRoom Air Quality | Humidity | within ±10% of 50 | ±10–20% | beyond ±20% | % | `srAqHumidityIdeal=50`, `srAqHumidityFirstSpan=10`, `srAqHumiditySecondSpan=20` |
| SmartRoom Air Quality | Temperature | within ±5°C of 25 | ±5–10°C | beyond ±10°C | °C | `srAqTempIdeal=25`, `srAqTempFirstSpan=5`, `srAqTempSecondSpan=10` |
| Crowd Monitoring | People Count | 15 | 15–40 | >40 | count | `cmPplCountLow=15`, `cmPplCountHigh=40` |
| Crowd Monitoring | Dist. Violations | 2 | 2–5 | >5 | count | `cmDistViolationsLow=2`, `cmDistViolationsHigh=5` |
| Crowd Monitoring | Mask Violations | 2 | 2–5 | >5 | count | `cmMaskViolationsLow=2`, `cmMaskViolationsHigh=5` |
| Energy Monitoring | R Current | 1,000,000 | 1,000,000–1,000,005 | >1,000,005 | A | `emRCurrentLow=1e6`, `emRCurrentHigh=1e6+5` |
| Energy Monitoring | R Voltage | 340 | 340–360 | >360 | V | `emRVoltageLow=340`, `emRVoltageHigh=360` |
| Energy Monitoring | R Power | 8,000 | 8,000–10,000 | >10,000 | W | `emRPowerLow=8000`, `emRPowerHigh=10000` |
| Energy Monitoring | Energy Consumed | 5,000,000 | 5e6–7e6 | >7e6 | kWh | `emEnergyConsumptionLow=5e6`, `emEnergyConsumptionHigh=7e6` |
| Energy Monitoring | Apparent Power | 700,000 | 700,000–1,000,005 | >1,000,005 | VA | `emApparentPowerLow=7e5`, `emApparentPowerHigh=1e6+5` |
| Energy Monitoring | Real Power | 300,000 | 300,000–500,005 | >500,005 | kW | `emRealPowerLow=3e5`, `emRealPowerHigh=5e5+5` |
| SmartRoom AC | Room Temp | within ±5°C of 25 | ±5–10°C | beyond ±10°C | °C | `srAcRoomTempIdeal=25`, `srAcRoomTempFirstSpan=5`, `srAcRoomTempSecondSpan=10` |
| SmartRoom AC | Temp Adjust | within ±5°C of 25 | ±5–10°C | beyond ±10°C | °C | `srAcTempAdjustIdeal=25`, `srAcTempAdjustFirstSpan=5`, `srAcTempAdjustSecondSpan=10` |
| SmartRoom AC | ON/OFF | 0 | 0–1 | 1 | — | `srAcOnOffLow=0`, `srAcOnOffHigh=1` |
| SmartRoom AC | ON % (overall) | <=40% | 40–70% | >70% | % | `srAcOnOffPercentLow=40`, `srAcOnOffPercentHigh=70` |
| SmartRoom Energy | Total Energy | 400,000,000 | 4e8–5e8 | >5e8 | kWh | `srEmTotalEnergyLow=4e8`, `srEmTotalEnergyHigh=5e8` |
| SmartRoom Energy | Current | 10 | 10–100 | >100 | A | `srEmCurrentLow=10`, `srEmCurrentHigh=100` |
| SmartRoom Energy | Power | 2,000 | 2,000–3,000 | >3,000 | W | `srEmPowerLow=2000`, `srEmPowerHigh=3000` |
| SmartRoom Energy | Voltage | 250 | 250–280 | >280 | V | `srEmVoltageLow=250`, `srEmVoltageHigh=280` |
| SmartRoom Occupancy | Occupancy (binary) | 0 | 0–1 | 1 | — | `srOcOc1Low=0`, `srOcOc1High=1` |
| SmartRoom Occupancy | Occupancy % (overall) | <=30% | 30–60% | >60% | % | `srOcOc1TotalPercentLow=30`, `srOcOc1TotalPercentHigh=60` |
| SmartRoom Occupancy | Temperature | within ±5°C of 25 | ±5–10°C | beyond ±10°C | °C | `srOcTempIdeal=25`, `srOcTempFirstSpan=5`, `srOcTempSecondSpan=10` |
| SmartRoom Occupancy | Humidity | within ±10% of 50 | ±10–20% | beyond ±20% | % | `srOcHumidityIdeal=50`, `srOcHumidityFirstSpan=10`, `srOcHumiditySecondSpan=20` |
| Wi-Sun | RSSI | 30 | 30–60 | >60 | dBm | `wnRssiLow=30`, `wnRssiHigh=60` |
| Wi-Sun | Latency | 2000 | 2000–5000 | >5000 | ms | `wnLatencyLow=2000`, `wnLatencyHigh=5000` |
| Wi-Sun | RPL Rank | 20000 | 20000–40000 | >40000 | — | `wnRplRankLow=20000`, `wnRplRankHigh=40000` |
| Wi-Sun | ETX | 195 | 195–250 | >250 | — | `wnEtxLow=195`, `wnEtxHigh=250` |
| Weather | Temperature | within ±5°C of 25 | ±5–10°C | beyond ±10°C | °C | `weTempIdeal=25`, `weTempFirstSpan=5`, `weTempSecondSpan=10` |
| Weather | Humidity | within ±10% of 50 | ±10–20% | beyond ±20% | % | `weHumidityIdeal=50`, `weHumidityFirstSpan=10`, `weHumiditySecondSpan=20` |
| Weather | Windspeed | 5 | 5–10 | >10 | m/s | `weWindspeedLow=5`, `weWindspeedHigh=10` |
| Weather | Rain | 2.5 | 2.5–7.5 | >7.5 | mm/hr | `weRainLow=2.5`, `weRainHigh=7.5` |
| Water Flow | Total Flow | 25,000 | 25,000–600,000 | >600,000 | m³ | `wfTotalFlowLow=25000`, `wfTotalFlowHigh=600000` |
| Water Flow | Flow Volume | 25,000 | 25,000–100,000 | >100,000 | L | `wfTotalFlowVolumeLow=25000`, `wfTotalFlowVolumeHigh=100000` |
| Water Flow | Flow Rate | 40 | 40–60 | >60 | m³/h | `wfTotalFlowRateLow=40`, `wfTotalFlowRateHigh=60` |
| Water Flow | Pressure | 1,000 | 1,000–2,000 | >2,000 | P | `wfPressureLow=1000`, `wfPressureHigh=2000` |
| Water Distribution | TDS | 150 | 150–300 | >300 | ppm | `wdTdsLow=150`, `wdTdsHigh=300` |
| Water Distribution | TDS Voltage | 1 | 1–2 | >2 | V | `wdTdsVoltageLow=1`, `wdTdsVoltageHigh=2` |
| Water Distribution | pH | within ±1 of 7 | ±1–2 | beyond ±2 | — | `wdPhIdeal=7`, `wdPhFirstSpan=1`, `wdPhSecondSpan=2` |
| Water Distribution | Turbidity | 1 | 1–5 | >5 | NTU | `wdTurbidityLow=1`, `wdTurbidityHigh=5` |
| Water Distribution | Temperature | within ±5°C of 25 | ±5–10°C | beyond ±10°C | °C | `wdTempIdeal=25`, `wdTempFirstSpan=5`, `wdTempSecondSpan=10` |
| Water Distribution | Water Level | 40 | 40–60 | >60 | cm | `wdWaterLevelLow=40`, `wdWaterLevelHigh=60` |
| Solar | EAC Today | 100 | 100–200 | >200 | W | `slEacTodayLow=100`, `slEacTodayHigh=200` |
| Solar | EAC Total | 200,000 | 200,000–600,000 | >600,000 | Wh | `slEacTotalLow=200000`, `slEacTotalHigh=600000` |
| Solar | Power1 | 8,000 | 8,000–10,000 | >10,000 | W | `slTotalPower1Low=8000`, `slTotalPower1High=10000` |
| Solar | Current1 | 3 | 3–5 | >5 | A | `slCurrent1Low=3`, `slCurrent1High=5` |

---