# GridFlex Local — Phase 1: Digital Neighbourhood + LV Feeder Simulation

> **Technical Prototype Disclaimer:**  
> **"This Phase 1 model is a digital simulation foundation and does not claim to represent a specific Indian distribution feeder."**

---

## 1. What GridFlex Local Is

**GridFlex Local** is a neighbourhood-scale, retrofit-oriented flexibility platform designed to mitigate renewable intermittency and voltage/thermal congestion at the low-voltage (LV) grid edge. Rather than requiring capital-intensive grid reinforcement or inventing proprietary Distributed Energy Resource (DER) hardware, GridFlex Local coordinates existing consumer-owned and community-sited assets—such as rooftop solar PV inverters, community battery energy storage (BESS), electric vehicles (EVs), and flexible/deferrable loads—to make local electricity distribution resilient, dependable, and constraint-aware.

---

## 2. What Phase 1 Does

Phase 1 provides the rigorous, physics-grounded **Digital Neighbourhood and Power System Simulation Foundation**:

- **Neighbourhood Representation:** Simulates 100 residential households with diverse diurnal consumption patterns, 5 commercial consumers, 1 critical health facility, 20 EV charging loads, and 3 scheduled flexible loads.
- **Rooftop Solar PV Modeling:** Simulates ~60 residential rooftop solar installations (60% penetration) with capacity diversity (2.0 to 6.0 kW) adhering to clear-sky insolation geometry.
- **Community Energy Storage:** Models a 100 kWh / 25 kW 4-quadrant community BESS with explicit State of Charge (SOC) tracking and round-trip efficiency constraints.
- **Radial LV Distribution Feeder:** Implements a realistic 415 V radial feeder topology connected to an 11 kV medium-voltage external grid via a 250 kVA distribution transformer in **pandapower**.
- **Time-Series AC Power Flow:** Executes full 15-minute resolution AC Newton-Raphson power flows across 96 timesteps (24-hour horizon).
- **Physical Validation:** Automatically validates power conservation ($P_{\text{grid}} + P_{\text{pv}} + P_{\text{bess\_dis}} \approx P_{\text{load}} + P_{\text{bess\_ch}} + P_{\text{losses}}$), voltage bounds, and non-negativity of loads.
- **Scenario Testing:** Simulates both a **BASELINE** clear-sky scenario and a controlled **PV_CLOUD_EVENT_V1** solar intermittency scenario (70% solar drop between 15:00 and 16:00) using the exact same underlying neighbourhood.

---

## 3. What Phase 1 Does NOT Do

To maintain scientific rigor and clear architectural separation, **Phase 1 intentionally excludes**:

- ❌ **No Machine Learning / Forecasting:** No XGBoost, LightGBM, neural networks, or weather prediction models yet.
- ❌ **No Autonomous DER Optimization:** No MILP dispatch, dynamic operating envelopes (DOEs), or automated load shifting.
- ❌ **No Artificial Reliability Claims:** Energy Not Served (ENS) is realistically 0.0 kWh in Phase 1 because the external substation grid supplies any feeder deficit. No ungrounded "30% reliability improvement" claims are fabricated.
- ❌ **No V2G or Smart EV Scheduling:** EV charging follows uncontrolled baseline arrival behavior.
- ❌ **No Hardware / Cloud Deployment:** No physical hardware or complex web dashboards; focuses purely on reproducible simulation.

---

## 4. Architecture

```
                                  [External MV Grid (11 kV)]
                                               |
                                     [Substation Slack Bus]
                                               |
                                    [Transformer 250 kVA]
                                        (11 / 0.415 kV)
                                               |
                                        [Bus_Main_LV]
               +-------------------------------+-------------------------------+
               |                               |                               |
       [Line_Commercial]               [Line_Critical]                   [Line_BESS]
               |                               |                               |
        [Bus_Commercial]                [Bus_Critical]                    [Bus_BESS]
        (COM01-05, HVAC)              (Health Centre CRIT001)         (Community BESS 100kWh)
               |
        [Line_Trunk_1]
               |
       [Bus_Residential_1] ---- [Line_EV_Hub] ---- [Bus_EV_Hub] (20 EV Chargers)
       (H001-H035, PVs, Pump)
               |
        [Line_Trunk_2]
               |
       [Bus_Residential_2] (H036-H070, PVs, Appliance Block)
               |
        [Line_Trunk_3]
               |
       [Bus_Residential_3] (H071-H100, PVs)
```

The future multi-phase architecture builds on this foundation:
$$\text{Data} \rightarrow \text{Forecasting} \rightarrow \text{Risk Assessment} \rightarrow \text{Flexibility Calculation} \rightarrow \text{DOEs} \rightarrow \text{Optimization} \rightarrow \text{Power-Flow Validation} \rightarrow \text{Dashboard}$$

---

## 5. Engineering Assumptions

Every simulation parameter in `config/neighbourhood_config.yaml` is strictly categorized:

| Category | Description | Example Parameters |
|---|---|---|
| **[engineering-assumption]** | Sized for a representative urban/peri-urban LV feeder prototype | 100 households, 250 kVA transformer, 415 V nominal, 15-min timestep, fixed random seed (42) |
| **[synthetic]** | Deterministically generated diurnal profiles reflecting consumer diversity | Household daily kWh (4.0–18.0 kWh), commercial business curves, EV commute arrival distributions |
| **[data-derived]** | Standard cable conductor and transformer electrical impedance characteristics | 95 mm² Al XLPE cable ($R=0.384\,\Omega/\text{km}$, $X=0.082\,\Omega/\text{km}$, $I_{\max}=220\,\text{A}$) |

---

## 6. Installation

Ensure Python 3.11+ is installed.

```bash
# Navigate to project directory
cd gridflex-local

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

---

## 7. Configuration

All major parameters are centrally managed in `config/neighbourhood_config.yaml`:

- `simulation`: Start date, duration, 15-minute resolution, seed.
- `neighbourhood`: Asset counts (100 houses, 60 PVs, 5 commercial, 1 critical, 20 EVs).
- `solar`: Capacity bounds (2.0–6.0 kW), peak irradiance hours.
- `battery`: Sizing (100 kWh, 25 kW), SOC bounds (20% to 90%), efficiencies (95%).
- `network`: Transformer MVA, cable impedances and line lengths.
- `cloud_event`: Intermittency window (`15:00`–`16:00`), reduction factor (`0.30`).
- `validation`: Voltage thresholds (0.94–1.06 p.u.), loading warnings (80%, 100%).

---

## 8. How to Run

### Run the Complete Pipeline
```bash
python scripts/run_phase1.py
```

### Run Only Profile Generation
```bash
python scripts/create_profiles.py
```

### Run Automated Unit Tests
```bash
pytest
```

---

## 9. Output Files

### CSV Data Outputs (`outputs/csv/`)
- `phase1_timeseries.csv`: Comprehensive 96-timestep electrical results for BASELINE.
- `phase1_timeseries_cloud.csv`: 96-timestep results under PV_CLOUD_EVENT_V1.
- `der_registry.csv`: Complete metadata and technical ratings for all 84 DER assets.
- `der_timeseries.csv`: Active power and SOC timeseries for each individual DER.
- `bus_results.csv`: Voltage magnitudes ($V_{\text{pu}}$) and angles per bus.
- `line_results.csv`: Conductor loading (%) and branch power flows.
- `transformer_results.csv`: Substation transformer loading (%), HV/LV powers, and losses.

### Engineering Figures (`outputs/figures/`)
1. `01_total_load_vs_pv_generation.png`: Total feeder demand vs. solar generation curves.
2. `02_net_load.png`: Duck curve / net load comparison across scenarios.
3. `03_transformer_loading.png`: Distribution transformer loading vs. 80% warning and 100% rated limits.
4. `04_maximum_line_loading.png`: Peak feeder conductor thermal loading profile.
5. `05_bus_voltage_bounds.png`: Minimum and maximum bus voltage envelope across the LV feeder.
6. `06_grid_import_export.png`: Substation active power exchange and reverse power flow detection.
7. `07_battery_soc.png`: Community BESS State of Charge adhering to 20%–90% operating limits.

---

## 10. Electrical Metrics

- **Net Load:** $P_{\text{net}} = P_{\text{load}} - P_{\text{PV}}$ (kW)
- **Power Balance Error:** $|(P_{\text{grid}} + P_{\text{pv}} + P_{\text{bess\_dis}}) - (P_{\text{load}} + P_{\text{bess\_ch}} + P_{\text{losses}})|$
- **Reverse Power Flow:** Flagged when $P_{\text{grid\_net}} < 0$, indicating local generation exceeds neighbourhood demand and feeds upstream into the MV grid.
- **Voltage Violations:** Evaluated against 0.94 p.u. (undervoltage) and 1.06 p.u. (overvoltage).
- **Transformer Loading:** Apparent power loading relative to 250 kVA nameplate rating.

---

## 11. Baseline vs. Cloud Scenario

| Metric | Baseline Scenario | Cloud Intermittency Scenario (`PV_CLOUD_EVENT_V1`) |
|---|---|---|
| **Solar Generation** | Uninterrupted clear-sky insolation | 70% generation drop between 15:00 and 16:00 |
| **Grid Import** | Baseline diurnal exchange | Instantaneous ramp-up at substation to compensate solar drop |
| **Transformer Loading** | Gradual afternoon transition | Sharp step-increase in transformer loading during cloud window |
| **Neighbourhood Consistency** | Exact same 100 households, EVs, commercial loads, and network topology |

---

## 12. Validation and Integrity Checks

- **Sanity Checks:** Automatic validation verifies strictly monotonic timestamps, absence of NaN/infinite values, non-negative loads, and capacity boundaries.
- **Conservation of Energy:** AC power flow guarantees power conservation across all 96 timesteps within numerical tolerance (< 0.001 kW).
- **Storage Boundaries:** Battery simulation mathematically enforces $SOC_{\min} \le SOC(t) \le SOC_{\max}$.

---

## 13. Limitations

- **Balanced 3-Phase Assumption:** Phase 1 uses balanced single-line equivalent modeling. Real Indian LV distribution feeders often exhibit phase unbalance.
- **Static Inverter Power Factor:** Inverters operate at unity power factor; volt-var / volt-watt autonomous inverter functions are deferred to Phase 2+.
- **Uncontrolled Flexibility:** Flexible loads and battery storage operate in passive baseline modes.

---

## 14. Phase 2: DER Digital Profiles & Flexibility Foundation

> **Architectural Guardrail:**  
> **"Phase 2 quantifies flexibility; it does not decide when or how that flexibility should be dispatched."**

### 1. What a DER Flexibility Passport Is
The **DER Flexibility Passport** (`outputs/csv/der_flexibility_passport.csv`) is a standardized, machine-readable digital representation of each distributed energy resource connected to the neighbourhood feeder. It captures:
- Physical ratings (rated kW, kWh capacity, response time)
- Dynamic state variables (current power, baseline power, SOC)
- Operational boundaries (min/max power, min/max SOC, reserve margins)
- Availability windows and control modes
- Socio-economic owner constraints and opt-in participation status

### 2. Technical Flexibility vs. Available Flexibility
The core principle governing Phase 2 is:
$$\text{Technical Flexibility} \neq \text{Available Flexibility}$$
- **Technical Flexibility:** The theoretical physical capability of an asset given its nameplate rating and physics state, assuming unrestricted control.
- **Available (Dispatchable) Flexibility:** The actual flexibility that can be summoned in practice, accounting for asset availability, consumer opt-in participation, emergency storage reserves, and operational deadlines. If an asset is unavailable or its owner has not opted in, its available dispatchable flexibility is strictly **zero**.

### 3. Flexibility Directions
- **UP Flexibility ($F_{\text{up}}$):** Resource ability to provide net support to the local grid (e.g. BESS discharge into the feeder).
- **DOWN Flexibility ($F_{\text{down}}$):** Resource ability to reduce its grid impact by shedding load or curtailing excess generation (e.g. BESS charging, solar PV inverter curtailment, EV charge throttling, flexible load shed).
- **SHIFT Flexibility ($F_{\text{shift}}$):** Deferrable demand that can be postponed in time without canceling energy delivery (e.g. EV charging sessions with slack before morning departure, scheduled water pumping).

### 4. Asset-Specific Constraints
- **Community Battery (BESS):** Sized at 100 kWh / 25 kW. Constrained by a strict 10% emergency reserve margin above the 20% minimum SOC ($SOC_{\text{eff\_min}} = 30\%$). Headroom curves enforce $0 \le P_{\text{dis}} \le 25\text{ kW}$ and $0 \le P_{\text{ch}} \le 25\text{ kW}$ duration-scaled by 15-minute intervals.
- **Electric Vehicles (EVs):** 20 Level 2 chargers ($7.4\text{ kW}$). V2G is strictly **FALSE** in Phase 2. EV flexibility represents downward throttling of baseline charging sessions while protecting total energy delivery before scheduled morning departure ($1.0\text{ h}$ safety buffer).
- **Rooftop Solar PV:** 60 systems ($211.28\text{ kW}$ total). Downward flexibility represents active power curtailment capability: $F_{\text{down}} = P_{\text{available}} - 0$. Curtailment is dispatched only if the owner has opted into flexibility programs.
- **Flexible Loads:** 3 scheduled loads ($3.5\text{ kW}$ water pump, $10.0\text{ kW}$ commercial HVAC, $4.0\text{ kW}$ appliance block). Downward flexibility corresponds to baseline load shed or deferral within defined operational windows.

### 5. No Double-Counting Guarantee
Phase 2 strictly avoids phantom flexibility:
- EV charging flexibility cannot exceed the vehicle's *actual active charging demand* at that timestep (never nameplate charger capacity).
- BESS discharge power is bounded by the lesser of converter rating and available energy above reserve.

### 6. Why Phase 2 Does Not Dispatch DERs
Phase 2 is an analytical quantification layer that maps the boundary of possible actions. It does not perform economic dispatch, optimal power flow, voltage regulation, or dynamic operating envelope calculations. The baseline power flow established in Phase 1 remains 100% unaltered.

---

## 15. Roadmap & Future Phases

- **Phase 1 (Complete):** Digital Neighbourhood + LV Feeder Simulation (pandapower AC power flow, electrical validation).
- **Phase 2 (Complete):** DER Digital Profiles + Flexibility Foundation (passports, availability, constraints, sensitivity).
- **Phase 3:** Monitoring + Forecasting Layer (Solar irradiance forecasting, load prediction, net demand uncertainty).
- **Phase 4:** DER Flexibility Engine & Dynamic Operating Envelopes (DOEs).
- **Phase 5:** Multi-Objective Co-Optimization (Peak shaving, transformer overload prevention, ENS reduction).
- **Phase 6:** Dashboard, Interface & Edge Demonstration.

