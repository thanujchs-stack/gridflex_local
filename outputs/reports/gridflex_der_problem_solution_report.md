# GridFlex Local — DER Problem-Solving & Grid Validation Report

**Challenge Area:** Schneider Electric Challenge 03 — Multi-DER Local Flexibility Coordination
**System Scale:** 250 kVA 11/0.415 kV Radial Distribution Substation (100 Households, 60 Rooftop PVs, 20 EVs, 3 Flexible Loads, 1 Community BESS)
**Verification Method:** Independent AC Power-Flow Validation in pandapower

---

## 1. DER Problem Definition

GridFlex Local addresses five real distribution-grid problems caused or amplified by high DER penetration:

1. **Voltage violations / voltage rise** — Excess PV export pushes bus voltages above 1.05 p.u.
2. **Reverse power flow** — Aggregated solar export back-feeds through the distribution transformer.
3. **Transformer and feeder/line congestion** — Coincident evening demand exceeds thermal ratings.
4. **Renewable intermittency and forecast uncertainty** — Rapid cloud cover causes unpredictable PV drops.
5. **Poor visibility and uncertain availability of DER flexibility** — Nameplate capacity ≠ available flexibility.

---

## 2. Baseline Scenario

The baseline represents uncoordinated DER operation:
- All PV systems export at maximum available irradiance.
- All EVs charge at rated power immediately upon connection.
- The community BESS remains idle.
- Flexible loads run on fixed schedules.
- No dynamic operating envelopes are applied.

The feeder topology, transformer rating (250 kVA), line impedance (0.384 Ω/km), customer demand, and PV availability are **identical** between baseline and GridFlex cases.

---

## 3. GridFlex Intervention

GridFlex applies coordinated DER scheduling:
- PV export ceilings derived from net load constraint analysis (not hard-coded).
- BESS schedules derived from surplus/deficit balancing respecting SOC limits.
- EV charging throttled and deferred to off-peak hours while guaranteeing departure energy.
- Flexible loads shifted based on constraint priority hierarchy.
- Dynamic operating envelopes with hysteresis respond to actual constraints.
- Forecast-aware flexibility reserves buffer prediction uncertainty.

---

## 4. Voltage Results

| Metric | Baseline | GridFlex |
|:---|:---:|:---:|
| SCENARIO_1_HIGH_PV_LOW_DEMAND Max Voltage | 1.1316 p.u. | 1.0146 p.u. |
| SCENARIO_1_HIGH_PV_LOW_DEMAND Min Voltage | 0.9588 p.u. | 0.9669 p.u. |
| SCENARIO_1_HIGH_PV_LOW_DEMAND Violation Count | 8 | 0 |
| SCENARIO_2_EV_PEAK_CONGESTION Max Voltage | 1.0987 p.u. | 1.0987 p.u. |
| SCENARIO_2_EV_PEAK_CONGESTION Min Voltage | 0.9236 p.u. | 0.9321 p.u. |
| SCENARIO_2_EV_PEAK_CONGESTION Violation Count | 10 | 10 |
| SCENARIO_3_CLOUD_INTERMITTENCY Max Voltage | 1.0987 p.u. | 1.0978 p.u. |
| SCENARIO_3_CLOUD_INTERMITTENCY Min Voltage | 0.9236 p.u. | 0.9321 p.u. |
| SCENARIO_3_CLOUD_INTERMITTENCY Violation Count | 10 | 10 |
| SCENARIO_4_LOW_PARTICIPATION Max Voltage | 1.0987 p.u. | 1.0987 p.u. |
| SCENARIO_4_LOW_PARTICIPATION Min Voltage | 0.9236 p.u. | 0.9262 p.u. |
| SCENARIO_4_LOW_PARTICIPATION Violation Count | 10 | 10 |
| SCENARIO_5_COMBINED_DIURNAL_STRESS Max Voltage | 1.1109 p.u. | 1.0129 p.u. |
| SCENARIO_5_COMBINED_DIURNAL_STRESS Min Voltage | 0.9162 p.u. | 0.9249 p.u. |
| SCENARIO_5_COMBINED_DIURNAL_STRESS Violation Count | 10 | 4 |

Configurable voltage limits: min = 0.95 p.u., max = 1.05 p.u.

---

## 5. Reverse-Flow Results

| Metric | Baseline | GridFlex |
|:---|:---:|:---:|
| SCENARIO_1_HIGH_PV_LOW_DEMAND Peak Reverse Flow | 187.05 kW | 14.01 kW |
| SCENARIO_1_HIGH_PV_LOW_DEMAND Reverse Flow Duration | 150.0 min | 45.0 min |
| SCENARIO_1_HIGH_PV_LOW_DEMAND Reverse Flow Energy | 312.73 kWh | 10.41 kWh |
| SCENARIO_2_EV_PEAK_CONGESTION Peak Reverse Flow | 138.61 kW | 138.61 kW |
| SCENARIO_2_EV_PEAK_CONGESTION Reverse Flow Duration | 150.0 min | 150.0 min |
| SCENARIO_2_EV_PEAK_CONGESTION Reverse Flow Energy | 203.9 kWh | 203.9 kWh |
| SCENARIO_3_CLOUD_INTERMITTENCY Peak Reverse Flow | 138.61 kW | 113.79 kW |
| SCENARIO_3_CLOUD_INTERMITTENCY Reverse Flow Duration | 90.0 min | 90.0 min |
| SCENARIO_3_CLOUD_INTERMITTENCY Reverse Flow Energy | 173.97 kWh | 136.68 kWh |
| SCENARIO_4_LOW_PARTICIPATION Peak Reverse Flow | 138.61 kW | 138.61 kW |
| SCENARIO_4_LOW_PARTICIPATION Reverse Flow Duration | 150.0 min | 150.0 min |
| SCENARIO_4_LOW_PARTICIPATION Reverse Flow Energy | 203.9 kWh | 203.9 kWh |
| SCENARIO_5_COMBINED_DIURNAL_STRESS Peak Reverse Flow | 156.98 kW | 13.21 kW |
| SCENARIO_5_COMBINED_DIURNAL_STRESS Reverse Flow Duration | 150.0 min | 30.0 min |
| SCENARIO_5_COMBINED_DIURNAL_STRESS Reverse Flow Energy | 228.61 kWh | 4.92 kWh |

---

## 6. Transformer Results

| Scenario | Baseline Peak | GridFlex Peak | Baseline Avg | GridFlex Avg | Baseline Overload Duration | GridFlex Overload Duration |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|
| SCENARIO_1_HIGH_PV_LOW_DEMAND | 75.39% | 23.13% | 39.27% | 10.54% | 0.0 min | 0.0 min |
| SCENARIO_2_EV_PEAK_CONGESTION | 56.36% | 56.36% | 35.53% | 34.33% | 0.0 min | 0.0 min |
| SCENARIO_3_CLOUD_INTERMITTENCY | 56.36% | 46.51% | 35.83% | 30.95% | 0.0 min | 0.0 min |
| SCENARIO_4_LOW_PARTICIPATION | 56.36% | 56.36% | 35.53% | 34.86% | 0.0 min | 0.0 min |
| SCENARIO_5_COMBINED_DIURNAL_STRESS | 63.71% | 47.43% | 38.52% | 18.66% | 0.0 min | 0.0 min |

---

## 7. Feeder/Line Results

| Scenario | Baseline Peak | GridFlex Peak | Baseline Avg | GridFlex Avg | Baseline Overload Duration | GridFlex Overload Duration |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|
| SCENARIO_1_HIGH_PV_LOW_DEMAND | 125.48% | 30.07% | 63.65% | 18.22% | 90.0 min | 0.0 min |
| SCENARIO_2_EV_PEAK_CONGESTION | 95.37% | 95.37% | 57.33% | 55.43% | 45.0 min | 45.0 min |
| SCENARIO_3_CLOUD_INTERMITTENCY | 95.37% | 95.45% | 55.12% | 53.25% | 45.0 min | 45.0 min |
| SCENARIO_4_LOW_PARTICIPATION | 95.37% | 95.37% | 57.33% | 56.28% | 45.0 min | 45.0 min |
| SCENARIO_5_COMBINED_DIURNAL_STRESS | 107.0% | 68.46% | 62.05% | 29.42% | 75.0 min | 0.0 min |

---

## 8. Forecast Uncertainty Results

- Mean net load forecast uncertainty: 40.01 kW
- Maximum forecast uncertainty: 51.29 kW
- PV uncertainty contribution: 26.52 kW (mean)
- Load uncertainty contribution: 29.64 kW (mean)

Risk distribution:
- NORMAL: 12 timesteps
- WATCH: 4 timesteps
- ACTION: 0 timesteps

---

## 9. Flexibility Availability Results

Across 84 DERs and 1344 passport records:

| Tier | Aggregate kW |
|:---|:---:|
| 1. Technical Flexibility | 950.0 kW |
| 2. Available Flexibility | 861.2 kW |
| 3. Selectable Flexibility | 861.2 kW |
| 4. Dispatched Flexibility | 43.5 kW |

Mean committed flexibility: 4.95 kW
Mean reserved flexibility: 20.00 kW
Mean remaining flexibility: 28.87 kW

**No flexibility is double-counted.** Committed and reserved flexibility are tracked separately
and remaining flexibility is computed as: available - committed - reserved.

---

## 10. Participation Sensitivity

| Participation Rate | Effect |
|:---|:---|
| 100% | Full DER fleet available for coordination |
| 70% (Default) | ~30% of DER owners opt out; reduced flexibility pool |
| 40% | Significantly constrained coordination; GridFlex impact reduced |

Scenario 4 explicitly tests 40% participation and demonstrates that theoretical flexibility is
not equal to available flexibility.

---

## 11. Trade-offs

GridFlex coordination involves inherent trade-offs:

1. **PV curtailment vs voltage compliance**: Restricting PV export reduces clean energy yield but prevents voltage violations.
2. **EV charging convenience vs grid relief**: Deferring EV charging reduces peak load but delays vehicle readiness.
3. **Battery cycling vs flexibility**: Using BESS for grid services increases cycling and degradation.
4. **Reserve margin vs utilization**: Holding flexibility in reserve reduces immediate dispatch capability but provides resilience.
5. **Participation rate vs constraint relief**: Lower participation directly reduces available flexibility.

If GridFlex improves one metric while worsening another, this report documents the trade-off
rather than claiming universal improvement.

---

## 12. Remaining Limitations

1. **Simplified feeder model**: Single radial feeder with 8 buses; real LV networks have more complex topologies.
2. **No three-phase modelling**: Balanced single-phase equivalent; phase imbalance effects are not captured.
3. **Limited DER-to-constraint sensitivity**: Electrical influence of each DER on specific constraints is approximated, not computed via full Jacobian sensitivity.
4. **Static power factors**: Load and DER power factors are fixed; reactive power coordination is not yet implemented.
5. **No communication latency**: Assumes instantaneous DER response within the 15-minute timestep.
6. **No protection system modelling**: Relay coordination and fault current effects are not modelled.
7. **Single-day simulation**: 24-hour window; seasonal and multi-day effects are not captured.
8. **No market integration**: No tariff signals, grid service pricing, or market clearing mechanisms.

> **GridFlex does not claim to completely solve DER integration.**
> It demonstrates that, under controlled simulation conditions, coordinating existing DER flexibility
> can reduce specific distribution grid constraints without changing the underlying infrastructure.

---

## 13. Deployment Assumptions

- All DERs have communication capability (MQTT, Modbus, or similar).
- Metering data is available at 15-minute resolution.
- Owner opt-in/opt-out is a binary participation flag.
- The distribution utility provides transformer and line ratings.
- PV inverters support dynamic export limiting.
- EV chargers support OCPP or equivalent smart charging protocol.

---

## 14. Phase 7 Independent Validation

All 5 scenarios were validated using independent AC power flow in pandapower:
- **Same feeder topology** for baseline and GridFlex.
- **Same transformer** (250 kVA, 11/0.415 kV).
- **Same line impedances** (0.384 Ω/km + j0.082 Ω/km).
- **Same loads and PV availability**.
- **Only the DER operating schedule differs**.

Power balance verified at every timestep (tolerance: 1.0 kW).

---

## 15. Exact Data/Configuration Used

- Configuration file: `config/neighbourhood_config.yaml`
- Optimization config: `config/optimization.yaml`
- Transformer: 250 kVA, vk = 4.0%, vkr = 1.1%
- Lines: XLPE Al cable, 0.384 Ω/km, 0.082 Ω/km, 220 A thermal rating
- Voltage limits: 0.95 – 1.05 p.u.
- Battery: 100 kWh / 25 kW, SOC 20%–90%, initial 50%
- EV chargers: 7.4 kW Level 2, 20 units
- PV systems: 60 units, 2–6 kW, average 3.5 kW
- Solver: scipy.optimize.linprog with HiGHS
- Random seed: 42

---

## 16. Reproducibility Information

- All simulations use fixed random seed (42) for deterministic results.
- HiGHS linear programming solver produces numerically identical solutions.
- Running `scripts/run_der_problem_solutions.py` twice produces identical output.
- All input datasets are pinned and version-controlled.
- AC power flow uses pandapower with `numba=False` for deterministic convergence.
