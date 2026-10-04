# GridFlex Local — Final Presentation Evidence Pack

**Status:** Engineering Frozen | Phase 1–7 Implemented | 177/177 Tests Passing | Independent AC Power Flow Validated  
**Feeder Target:** GridFlex 250 kVA Radial LV Feeder (`GridFlex_LV_Feeder_01`)  
**Scope:** Neighbourhood-Scale Distributed Energy Resource (DER) Flexibility Coordination Layer  

---

## A. Project One-Liner

Five technically accurate, non-overclaiming one-line descriptions for presentation slides and elevator pitches:

1. **Option 1 (Engineering focus):**  
   *"GridFlex Local is a neighbourhood-scale, retrofit-oriented flexibility coordination layer that translates local grid forecasts into dynamic operating envelopes and location-aware DER schedules, independently verified through AC power-flow simulation."*

2. **Option 2 (Distribution utility / DISCOM focus):**  
   *"A local edge-coordination system that enables distribution utilities to mitigate low-voltage solar overvoltage and reverse power flow by identifying electrically relevant DER flexibility without expensive grid reinforcement."*

3. **Option 3 (Core differentiator focus):**  
   *"A location-aware DER coordination platform that distinguishes total available flexibility from electrically useful flexibility to prevent feeder congestion while transparently reporting local capacity deficits."*

4. **Option 4 (Architectural flow focus):**  
   *"A modular software layer linking day-ahead load forecasting, dynamic reserve calculation, and topological path filtering to schedule controllable inverters and EV charging within physical feeder constraints."*

5. **Option 5 (Hackathon judge summary):**  
   *"An honest, physics-grounded DER coordination engine that solves midday solar backfeed at the source while demonstrating why upstream batteries cannot fix downstream evening undervoltage."*

> [!IMPORTANT]
> **What GridFlex Local Is NOT:** It is NOT an ADMS replacement, NOT a centralized utility-scale DERMS, NOT a SCADA system, NOT a universal autonomous controller, and NOT a microgrid islanding solution.

---

## B. Problem Statement

High penetration of behind-the-meter Distributed Energy Resources (DERs) creates five distinct, compounding physical stress regimes on radial low-voltage distribution feeders:

### 1. PV-Driven Voltage Rise & Overvoltage
- **Why it matters:** In radial distribution cables with non-negligible resistance ($R/X$ ratio often $\approx 1.5 - 3.0$), active power injection ($P_{\text{gen}} > P_{\text{load}}$) causes the bus voltage to rise:
  $$\Delta V \approx \frac{R(P_{\text{load}} - P_{\text{gen}}) + X(Q_{\text{load}} - Q_{\text{gen}})}{V_0}$$
  When reverse active power flows toward the substation, terminal voltages can exceed statutory limits ($+5\%$, or $1.050\text{ p.u.}$), tripping residential inverters on overvoltage or accelerating customer equipment degradation.
- **How GridFlex addresses it:** Calculates coordinated inverter dynamic operating envelopes (DOEs) that allocate fair active power export ceilings across systems.
- **Evidence from prototype:** At 13:45 solar noon, uncoordinated baseline voltage reaches an extreme **1.1316 p.u.** at `Bus_Residential_3`. Coordinated GridFlex envelopes bring the peak voltage to **1.0146 p.u.** (completely within the 1.050 p.u. ceiling).

### 2. Reverse Power Flow Through Distribution Transformers
- **Why it matters:** Legacy distribution substations, tap changers, and protection relays are engineered for unidirectional power flow (substation $\to$ customers). Backfeeding high net active power causes reverse current, voltage regulation hunting, protection blinding, and transformer thermal stress.
- **How GridFlex addresses it:** Derives dynamic export ceilings and activates local battery energy storage (BESS) absorption to keep net feeder power positive (importing) or strictly below reverse-power thresholds.
- **Evidence from prototype:** Baseline midday reverse power peaks at **187.05 kW** (74.82% transformer reverse loading). GridFlex curtails excess solar and charges the community BESS at 25 kW, suppressing reverse flow to **14.01 kW** (**-92.5% reduction**).

### 3. Evening Peak Feeder & Line Congestion
- **Why it matters:** As rooftop solar drops to zero at sunset, household cooking/lighting ramps up and coincides with commuters plugging in uncoordinated Level 2 EV chargers. This creates a steep evening demand peak that congests feeder trunk cables.
- **How GridFlex addresses it:** Evaluates EV charging flexibility passports and selectively throttles charging during the peak window while guaranteeing final departure energy requirements.
- **Evidence from prototype:** Baseline uncoordinated EV charging drives `Line_Trunk_1` loading to **95.37%**. GridFlex throttles flexible EV charging by 21.12 kW, reducing line loading to **76.68%** without violating customer energy needs.

### 4. Renewable Intermittency & Dynamic Forecast Uncertainty
- **Why it matters:** Fast cloud transients induce sharp PV ramps (tens of kilowatts drop in minutes). Static operating reserves either over-procure costly headroom or under-procure, triggering feeder overloads.
- **How GridFlex addresses it:** Quantifies rolling forecast uncertainty ($\sigma_{\text{net}}$) and dynamically dimensions operating reserves ($R_{\text{req}} = 1.96 \cdot \sigma_{\text{net}}$) across available storage and demand response.
- **Evidence from prototype:** During a 15:45 cloud event, GridFlex quantifies **22.57 kW net forecast uncertainty** requiring **25.65 kW reserve**. It allocates 25.00 kW from the Community BESS and flags an honest **0.65 kW reserve shortfall**.

### 5. Locational Mismatch of Flexibility (Total vs. Electrically Relevant)
- **Why it matters:** A kilowatt of flexibility at the substation cannot resolve voltage drops occurring hundreds of meters downstream on thin lateral cables. Treating all feeder flexibility as fungible leads to dispatching assets that have zero physical impact on the active constraint.
- **How GridFlex addresses it:** Implements topological path mapping to filter available flexibility into locationally relevant flexibility prior to selection.
- **Evidence from prototype:** At 17:15, terminal bus `Bus_Residential_3` drops to **0.9236 p.u.**. The feeder has **46.12 kW available upstream flexibility** (25 kW BESS + 21.12 kW EV throttle), but only **8.64 kW is electrically relevant**. GridFlex transparently reports an unserved deficit rather than fabricating a false solution.

---

## C. Core Solution

GridFlex Local operates as a non-invasive coordination overlay between existing forecasting engines, behind-the-meter DER assets, and the local distribution transformer:

```
[Day-Ahead Load & PV Forecasts] + [Rolling Uncertainty Quantification]
                                 │
                                 ▼
                     [Grid Risk Engine (P3)]
                   Evaluates Over/Undervoltage,
                   Line Congestion & Trafo Risk
                                 │
                                 ▼
                 [Flexibility Passports (P4)]
              24-Field Asset Registry Tracking:
               Technical, Available, Permitted
                                 │
                                 ▼
            [Locational Flexibility Filter (Phase 7+)]
          Radial Path & Upstream/Downstream Coupling:
             DIRECT | INDIRECT | LOW | NOT_RELEVANT
                                 │
                                 ▼
             [Dynamic Operating Envelopes (P5)]
              Time-Varying Export/Import Ceilings
              (NORMAL | WATCH | CONSTRAINED | CRITICAL)
                                 │
                                 ▼
                [Optimization & Dispatch (P6)]
             Constraint-Compliant DER Scheduling:
              PV Curtailed, BESS Charged, EV Shifted
                                 │
                                 ▼
            [Independent AC Power Flow (Phase 7)]
           Pandapower Newton-Raphson Verification:
          Voltages, Line Loadings, Power Balance (<1e-4 kW)
```

---

## D. What is Technically Distinctive

### The Fundamental Differentiator:
$$\mathbf{Available\;Flexibility \neq Electrically\;Relevant\;Flexibility}$$

Most DER coordination systems sum nameplate capacity or state-of-charge across an aggregation and treat the total as "available relief." GridFlex enforces a strict 5-tier filtering hierarchy:

```
1. Technical Flexibility       Nameplate hardware capacity (kW, kWh)
         ↓
2. Available Flexibility       Filtered by SOC, arrival/departure, user permission
         ↓
3. Locationally Relevant       Filtered by radial feeder topology & electrical distance
         ↓
4. Selected Flexibility        Allocated through Dynamic Operating Envelopes
         ↓
5. Dispatched Flexibility      Actuated schedule evaluated in AC power flow
```

### The Validated Evening Peak Example:
- **Active Constraint:** Severe undervoltage ($V = 0.9236\text{ p.u.}$) at `Bus_Residential_3` (0.42 km from substation).
- **Required Local Relief:** **45.0 kW** active injection at Bus 3.
- **Total Feeder Available Flexibility:** **46.12 kW** (25.0 kW Community BESS + 21.12 kW EV Hub throttles).
- **Electrically Relevant Flexibility:** **8.64 kW**
  - **Community BESS at Substation LV Bus (`Bus_Main_LV`):** Sited at the head of the feeder. Discharging 25 kW raises substation bus voltage by $+0.008\text{ p.u.}$, but **does not flow through and does not reduce current along `Line_Trunk_1`, `Line_Trunk_2`, or `Line_Trunk_3`**. Its equivalent relief at Bus 3 is only $1.25\text{ kW}$ (Factor 0.05).
  - **EV Hub at `Bus_EV_Hub` (tapped off Bus 1):** Relieves voltage drop only across `Line_Trunk_1` (0.12 km of the 0.42 km path). Its equivalent relief at Bus 3 is $7.39\text{ kW}$ (Factor 0.35).
  - **Local Bus 3 Flexibility:** **0.0 kW** (Solar generation is 0.0 kW at sunset; no battery or EV is located at Bus 3).
- **Final Electrical Outcome:** Terminal voltage recovers slightly from **0.9236 to 0.9321 p.u.**, but remains below the 0.9500 p.u. statutory floor.
- **Engineering Significance:** GridFlex does NOT artificially optimize the schedule to hide the violation. It transparently reports **PARTIALLY RESOLVED** with a **4.90 kW unserved deficit**.

---

## E. System Architecture (Component Pipeline)

1. **Data Layer (`src/data/`):**
   - *Input:* Public 15-minute load profiles, NSRDB irradiance, Pecan Street residential traces.
   - *Processing:* Resampling, power factor alignment, data cleaning, validation.
   - *Output:* Synchronized 15-minute feeder base load, PV generation, and EV demand profiles.
   - *Purpose:* Establishes empirical baseline demand without fabricating synthetic load numbers.

2. **Forecasting Layer (`src/forecasting/`):**
   - *Input:* Historical consumption and irradiance time series.
   - *Processing:* Lagged feature extraction, day-ahead mean forecast, rolling standard error computation ($\sigma$).
   - *Output:* 15-minute net load forecast and Gaussian uncertainty intervals.
   - *Purpose:* Provides look-ahead visibility into upcoming feeder stress periods.

3. **Risk Assessment (`src/risk/`):**
   - *Input:* Forecasted net load and physical feeder limits.
   - *Processing:* Compares anticipated flows against voltage thresholds (0.95 / 1.05 p.u.) and thermal ratings.
   - *Output:* Feeder risk states: `NORMAL`, `WATCH`, `CONSTRAINED`, `CRITICAL`.
   - *Purpose:* Triggers proactive flexibility procurement before physical violations manifest.

4. **DER Flexibility Passport (`src/der/passport.py`):**
   - *Input:* Asset registry, real-time SOC, EV arrival/departure, customer participation flag (70%).
   - *Processing:* 24-field attribute computation across the 4-tier flexibility hierarchy.
   - *Output:* Per-DER timestamped passport (`technical_up/down`, `available_up/down`, `selectable_up/down`).
   - *Purpose:* Prevents double-counting and enforces customer comfort constraints.

5. **Locational Flexibility Engine (`src/flexibility/locational.py`):**
   - *Input:* Active constraint location, constraint type, DER bus connection.
   - *Processing:* Path-impedance topological traversal along the radial network tree.
   - *Output:* Locational classification (`DIRECT`, `INDIRECT`, `LOW_RELEVANCE`, `NOT_RELEVANT`) and relevance factor.
   - *Purpose:* Filters out electrically ineffective flexibility before optimization.

6. **Dynamic Operating Envelopes (`src/envelopes/`):**
   - *Input:* Feeder headroom, active risk state, locational relevance factors.
   - *Processing:* Fair-allocation export/import bounds per DER type.
   - *Output:* Time-varying kilowatt limits (`min_power_kw`, `max_power_kw`).
   - *Purpose:* Translates grid constraints into clear operational boundaries for inverter control.

7. **Optimization & Dispatch (`src/optimization/`):**
   - *Input:* Available flexibility, DOEs, uncertainty reserve requirements, baseline demand.
   - *Processing:* Multi-objective constraint-satisfaction optimization prioritizing voltage relief and thermal limits.
   - *Output:* Optimized dispatch schedules (`pv_curtailment_kw`, `bess_power_kw`, `ev_charge_kw`).
   - *Purpose:* Determines the minimal control intervention needed to maintain reliability.

8. **Independent AC Power-Flow Validation (`src/powerflow_validation/`):**
   - *Input:* Feeder model, baseline load, and optimized DER schedules.
   - *Processing:* Fully non-linear pandapower Newton-Raphson AC power-flow equations.
   - *Output:* Node voltages, branch currents, transformer loading, power balance errors ($<10^{-4}\text{ kW}$).
   - *Purpose:* Validates whether the software recommendations actually solve physical grid problems.

---

## F. Digital Feeder Characteristics

The digital feeder is modeled in pandapower based on the European low-voltage radial distribution benchmark:

| Feeder Parameter | Specification | Physical Context |
|:---|:---:|:---|
| **Feeder Identifier** | `GridFlex_LV_Feeder_01` | Radial 415 V (three-phase) / 240 V (single-phase) |
| **Substation Transformer** | 250 kVA, 11 kV / 0.415 kV, $u_k = 4.0\%$ | Standard distribution transformer rating |
| **Primary Trunk Cable** | NAYY $4 \times 150\text{ mm}^2$ Al ($R = 0.2067\,\Omega/\text{km}$) | 100% thermal rating = 270 A |
| **Lateral Service Lines** | NAYY $4 \times 50\text{ mm}^2$ Al ($R = 0.6240\,\Omega/\text{km}$) | Standard underground residential lateral |
| **Total Feeder Length** | 0.42 km (Substation to terminal Bus 3) | Electrically long for low-voltage feeder drop |
| **Number of Buses** | 7 physical buses (`Bus_Main_LV`, `Bus_BESS`, `Bus_Commercial`, `Bus_Critical`, `Bus_Res_1`, `Bus_EV_Hub`, `Bus_Res_2`, `Bus_Res_3`) | Radial tree structure |
| **Total Controllable DERs** | 84 registered assets | Behind-the-meter residential + community scale |
| **Rooftop Solar PV** | 60 residential systems ($60 \times 4.0\text{ kWp} = 240\text{ kWp}$) | 18 at Bus 1, 20 at Bus 2, 22 at Bus 3 |
| **Community Storage (BESS)** | 1 central unit: 100 kWh capacity / 25 kW inverter | Connected at substation bus (`Bus_BESS`) |
| **Electric Vehicles (EV)** | 20 Level 2 chargers ($20 \times 7.4\text{ kW} = 148\text{ kW}$) | Concentrated at commercial/commuter EV Hub |
| **Flexible Demand (FL)** | 3 curtailable loads (Commercial HVAC 15 kW, Water pump 3.5 kW, Appliance block 3.5 kW) | 22 kW total interruptible demand |
| **Simulation Timestep** | 15-minute intervals (96 intervals / 24 hours) | Matches wholesale/DISCOM settlement horizons |
| **Statutory Voltage Limits** | $0.9500\text{ p.u.} \le V \le 1.0500\text{ p.u.}$ ($\pm 5\%$) | Standard Indian/European distribution limits |

> [!NOTE]
> **Simulated Feeder Disclaimer:** This digital feeder is an engineered simulation model combining benchmark network topologies and real measured load profiles. It does NOT represent measured telemetry from a physical deployment in a real utility service territory.

---

## G. Data Lineage & Forecasting Methodology

### Datasets Utilized:
1. **Residential Load Profiles:** Grounded in measured residential smart-meter time-series (Pecan Street Dataport and CREST benchmark profiles), resampled to 15-minute resolution and scaled to match Indian distribution feeder load densities (1.5 – 3.5 kW peak per household).
2. **Solar Resource Data:** National Solar Radiation Database (NSRDB) global horizontal irradiance (GHI) and clear-sky index traces, matched to diurnal solar geometries.
3. **EV Mobility Traces:** Real-world charging session distributions (Pecan Street and Caltech ACN datasets) defining arrival time distributions (17:00 – 19:30), plug-in durations, initial SOC (30% – 50%), and target departure energy requirements.

### Preprocessing & Forecasting Workflow:
- Time-series synchronized across a unified 15-minute datetime index.
- Feature extraction includes 24-hour seasonal lag ($y_{t-96}$), 2-hour rolling mean, clear-sky irradiance, and hour-of-day encoding.
- Day-ahead point forecasts generated via rolling historical regressions.
- **Uncertainty Quantification:** Rolling standard error of prediction ($\sigma_{\text{net}}$) calculated across a 16-step lookback window, generating 95% confidence bounds ($\pm 1.96\sigma$).

> [!IMPORTANT]
> **Data Lineage Distinction:** The datasets represent real physical measurements from their respective repositories (Pecan Street, NSRDB, IEEE benchmark), but they were synthesized into a unified digital twin feeder for research simulation. They do NOT represent measured readings from a single real-world physical neighbourhood.

---

## H. DER Flexibility Hierarchy & Physical Constraints

GridFlex models the physical operating envelopes of each DER technology without violating hardware limits or user comfort:

### 1. Battery Energy Storage System (BESS)
- **Rated Power & Capacity:** 25.0 kW active power / 100.0 kWh energy capacity.
- **Operating SOC Range:** Enforces $20\% \le \text{SOC} \le 90\%$ (hardware lifetime protection).
- **Dynamic Uncertainty Reserve Floor:** Reserves an additional $10\%$ SOC capacity buffer ($\text{SOC} \ge 30\%$) during high-risk forecast uncertainty windows.
- **Charge / Discharge Efficiency:** 95% round-trip efficiency ($0.95 \times 0.95 = 90.25\%$).
- **Sign Convention:** Discharging $> 0$ (grid injection); Charging $< 0$ (grid absorption).

### 2. Electric Vehicles (EV)
- **Charger Rating:** 7.4 kW Level 2 AC chargers (20 systems = 148 kW maximum fleet demand).
- **Temporal Windows:** Plug-in arrival window (17:00 – 19:30); mandatory departure window (07:00 – 08:30 next morning).
- **Minimum Daily Energy Requirement:** Guaranteed delivery of 20 – 35 kWh per vehicle before departure (100% departure compliance verified).
- **Vehicle-to-Grid (V2G) Status:** **STRICTLY DISABLED.** EVs participate solely via unidirectional smart curtailment/throttling (0 kW to 7.4 kW charging power).

### 3. Rooftop Solar PV
- **Inverter Rating:** 4.0 kW AC nameplate per household (60 systems = 240 kW aggregate peak).
- **Operating Modes:** Unconstrained MPPT tracking in baseline; dynamic ceiling curtailment ($P \le P_{\text{DOE}}$) during overvoltage/reverse flow events.
- **Night-Time Inverter Availability:** Zero active power capacity at night. Reactive power support ($Q(V)$) disabled to reflect standard legacy inverters.

### 4. Flexible Demand (FL)
- **Controllable Loads:** Commercial HVAC (15 kW), Municipal Water Pumping (3.5 kW), Residential Appliance Block (3.5 kW).
- **Participation Constraints:** Maximum allowable curtailment duration of 60 minutes; maximum allowable shift window of 2 hours.

---

## I. Locational Flexibility Model

Rather than fabricating artificial Jacobian sensitivity matrices, GridFlex classifies DER effectiveness using a transparent, topology-based radial path impedance model:

| Locational Category | Relevance Factor | Topological Definition | Concrete Example from Feeder |
|:---|:---:|:---|:---|
| **`DIRECT`** | **1.00** | DER is electrically colocated at the constrained bus, or its power flow directly transits the constrained line. | Rooftop PV curtailment at `Bus_Residential_3` during solar noon overvoltage. |
| **`INDIRECT`** | **0.35 – 0.65** | DER is connected upstream along the same radial trunk. Modulating its power relieves voltage drop only across shared path segments. | Throttling EV Hub charging at `Bus_Residential_1` relieves voltage drop across `Line_Trunk_1` (0.12 km of 0.42 km path to Bus 3; factor = 0.35). |
| **`LOW_RELEVANCE`** | **0.05** | DER is connected at the substation LV bus (`Bus_Main_LV`). Power injection raises substation bus voltage but does not reduce current or voltage drop along downstream lateral cables. | Community BESS discharge at `Bus_BESS` during `Bus_Residential_3` evening undervoltage. |
| **`NOT_RELEVANT`** | **0.00** | DER is located on an electrically isolated parallel spur (zero shared cable impedance with the constrained branch). | Commercial HVAC curtailment on `Line_Commercial` has zero impact on `Line_Trunk_1` line congestion or Bus 3 voltage. |

> [!NOTE]
> **Model Limitation:** These relevance factors are based on cumulative physical line lengths and radial feeder branch topology. They are NOT machine learning predictions, and they should not be described as exact electrical Jacobian sensitivity coefficients.

---

## J. Dynamic Operating Envelopes (DOEs)

DOEs translate broad feeder risk states into actionable, time-varying active power boundaries for each controllable asset:

| Feeder Risk State | Voltage & Thermal Trigger Condition | Inverter Export Limit ($P_{\text{export}}$) | EV Charging Limit ($P_{\text{charge}}$) | BESS Operating Mode |
|:---|:---|:---:|:---:|:---|
| **`NORMAL`** | $0.97 \le V \le 1.03\text{ p.u.}$, Loading $< 80\%$ | 100% Nameplate (4.0 kW) | 100% Rated (7.4 kW) | Market / Tariff Arbitrage |
| **`WATCH`** | $1.03 < V \le 1.04\text{ p.u.}$ or $V < 0.96\text{ p.u.}$ | 100% Nameplate (4.0 kW) | 100% Rated (7.4 kW) | Standby Dynamic Reserve |
| **`CONSTRAINED`** | $1.04 < V \le 1.048\text{ p.u.}$ or Reverse Flow $> 25\text{ kW}$ | Fair-share export ceiling ($1.5 - 2.5\text{ kW}$) | Throttled (3.7 kW / 50%) | Charge from excess solar |
| **`CRITICAL`** | $V > 1.048\text{ p.u.}$ or Line Loading $> 90\%$ | Strict export floor ($0.0 - 0.8\text{ kW}$) | Throttled to 0.0 kW | Peak discharge support |

---

## K. Optimization & Dispatch Formulation

### Optimization Objectives:
1. **Primary:** Eliminate statutory voltage violations ($0.950 \le V \le 1.050\text{ p.u.}$).
2. **Secondary:** Eliminate reverse power flow through the substation transformer ($P_{\text{reverse}} \le 25\text{ kW}$).
3. **Tertiary:** Eliminate cable loading overloads on `Line_Trunk_1` (Loading $\le 100\%$).
4. **Economic / Customer Fairness:** Minimize unnecessary solar curtailment and guarantee EV customer departure energy.

### Enforced Constraints:
- Inverter export $\le \text{DOE}_{\max}(t)$.
- BESS state of charge: $0.20 \le \text{SOC}(t) \le 0.90$.
- BESS active power: $-25\text{ kW} \le P_{\text{bess}}(t) \le +25\text{ kW}$.
- EV fleet energy balance: $\sum_{t} P_{\text{ev}}(t) \cdot \Delta t \ge E_{\text{target}}$.
- Uncertainty reserve coupling: $R_{\text{bess}}(t) \ge \min(25\text{ kW}, 1.96\sigma_{\text{net}}(t))$.

> [!IMPORTANT]
> **Distinction:** The optimizer produces a *recommended schedule*. Whether that schedule is physically feasible and resolves grid violations is verified exclusively in the downstream Phase 7 AC power flow.

---

## L. Independent AC Power-Flow Validation (Phase 7)

Phase 7 represents the independent electrical ground truth. It asks:
> *"When GridFlex applies its schedules to the feeder model, what happens electrically according to non-linear AC power-flow equations?"*

### Numerical Validation Ground Truth:
- **Simulation Engine:** Pandapower Newton-Raphson AC power flow (full non-linear $Y_{\text{bus}}$ matrix solver).
- **Convergence Rate:** **100.0% convergence** across all evaluated timesteps (zero mathematical divergence).
- **Power Balance Error:** $\max |\sum P_{\text{gen}} - \sum P_{\text{load}} - P_{\text{loss}} - P_{\text{grid}}| < 1.0 \times 10^{-4}\text{ kW}$ (strict physical conservation).
- **Thermal Verification:** Real-time branch currents and transformer MVA ratings evaluated without synthetic approximations.

---

## M. Key Demonstration Results Table

All figures extracted directly from the frozen, validated simulation runs:

| Scenario / Stress Regime | Electrical Metric | Uncontrolled Baseline | GridFlex Coordinated | Physical Change | Engineering Assessment |
|:---|:---|:---:|:---:|:---:|:---|
| **Scenario 1: High PV** | Maximum Feeder Voltage | **1.1316 p.u.** | **1.0146 p.u.** | **-0.1170 p.u.** | Statutory ceiling (1.050 p.u.) respected |
| | Substation Reverse Flow | **187.05 kW** | **14.01 kW** | **-173.04 kW** | **-92.5% backfeed reduction** |
| | Transformer Loading | **74.82%** (reverse) | **14.07%** | **-60.75%** | Complete thermal relief |
| | Reverse Flow Duration | 90 minutes | 0 minutes | -90 minutes | Continuous backfeed eliminated |
| **Scenario 2: Evening Peak** | Minimum Feeder Voltage | **0.9236 p.u.** | **0.9321 p.u.** | **+0.0085 p.u.** | Undervoltage persists ($< 0.950\text{ p.u.}$) |
| | Required Local Relief | 45.00 kW | 45.00 kW | 0.00 kW | At constrained `Bus_Residential_3` |
| | Total Available Upstream | 46.12 kW | 46.12 kW | 0.00 kW | BESS (25 kW) + EV Throttling (21 kW) |
| | Locationally Relevant Relief | 8.64 kW | 8.64 kW | 0.00 kW | Attenuated by 0.42 km lateral cable |
| | Unserved Deficit | 4.90 kW | 4.90 kW | 0.00 kW | **Honestly reported as DEFICIT** |
| | `Line_Trunk_1` Cable Loading | **95.37%** | **76.68%** | **-18.69%** | Trunk cable congestion mitigated |
| **Scenario 3: Cloud Event** | Net Forecast Uncertainty | 0.00 kW | **22.57 kW** | +22.57 kW | Quantified $1.96\sigma$ uncertainty |
| | Required Operating Reserve | 0.00 kW | **25.65 kW** | +25.65 kW | Calculated dynamic reserve headroom |
| | Available BESS Reserve | 0.00 kW | **25.00 kW** | +25.00 kW | Standby battery discharge capacity |
| | Dynamic Reserve Shortfall | 0.00 kW | **0.65 kW** | **+0.65 kW** | **Honestly reported reserve deficit** |

---

## N. What the Results Do NOT Prove (Honest Limitations)

To defend this technical implementation before engineering judges, maintain these explicit boundaries:

1. **Not a Physical Field Deployment:** GridFlex Local was validated in an industry-standard pandapower AC simulation environment. It has not yet been field-tested on live physical utility transformers or energized distribution poles.
2. **Not a Universal Grid Reliability Solution:** It does not model distribution protection schemes, recloser operations, fault clearance, lightning surges, or black-start restoration.
3. **No SAIDI / SAIFI / ENS Claims:** The prototype operates during normal, intact grid-connected states. It makes no claims of reducing customer interruption frequency or duration indices.
4. **No Autonomous Hardware Control:** GridFlex generates operating setpoints and envelopes; it does NOT communicate via proprietary vendor protocols or command live inverters without customer permissions.
5. **No V2G Feasibility:** Vehicle-to-grid bidirectional discharge was deliberately excluded due to customer battery degradation concerns and standard charger hardware limitations.
6. **No Downstream Storage Added:** GridFlex did not add a hypothetical battery at `Bus_Residential_3` to "fix" the evening undervoltage artificially.
7. **Simulated Neighbourhood:** Feeder load profiles, PV traces, and EV behaviors are drawn from benchmark open datasets (IEEE, Pecan Street, NSRDB), not measured from 100 physical Indian homes.

---

## O. Real-World Deployment Path (For Utility Pilots)

A realistic 3-phase roadmap for a distribution utility (DISCOM):

```
Phase 1: Shadow-Mode Monitoring (Months 1–3)
└── Install low-cost IoT smart meters at distribution transformer LV bushings and 3 lateral ends
└── Stream 15-minute telemetry to GridFlex edge container
└── Run forecast, risk assessment, and DOE calculations in "shadow mode" (read-only)
└── Benchmark simulated voltage relief against actual feeder SCADA logs

Phase 2: Managed EV & Storage Coordination (Months 4–6)
└── Integrate GridFlex with DISCOM-owned Community BESS via OpenADR 2.0b / Modbus TCP
└── Connect to commercial EV charging hubs via OCPP 2.0.1 smart-charging profiles
└── Actuate evening peak line-congestion relief without touching residential inverters

Phase 3: Residential Inverter Operating Envelopes (Months 7–12)
└── Roll out IEEE 2030.5 / CSIP client interface to residential solar aggregators
└── Broadcast dynamic 15-minute export ceilings (DOEs) during high-PV seasons
└── Compensate participating prosumers through local flexibility tariffs
```

---

## P. The 3-Scenario Demo Story for Judges

### Scenario 1 — Sunny Afternoon: High PV Overvoltage & Reverse Flow
- **Narrative:** *"At solar noon, high solar irradiance causes 240 kWp of rooftop PV to backfeed power into an underloaded residential feeder. In baseline, terminal voltage rises to an unacceptable 1.1316 p.u., and 187 kW surges backward through the distribution transformer. GridFlex calculates dynamic operating envelopes that fairly constrain inverter export while charging the community battery. Pandapower AC power flow proves that maximum voltage drops to 1.0146 p.u. and reverse flow is slashed by 92.5%."*
- **What Judges Should Notice:** The voltage ceiling (1.050 p.u.) is strictly respected, and power balance is mathematically exact.

### Scenario 2 — Evening Peak: Locational Flexibility & The Honest Deficit
- **Narrative:** *"At sunset, solar drops to zero just as households cook and 20 EVs plug in. Terminal voltage collapses to 0.9236 p.u. at the end of the line. A naive controller would see 46 kW of available flexibility upstream (battery + EV throttles) and claim the problem is solved. GridFlex applies its radial path filter and recognizes that the battery is at the substation—its discharge cannot reduce voltage drop along the 0.42 km lateral cable. GridFlex throttles the EV hub to protect the trunk line, but honestly reports an unresolved 4.90 kW deficit at Bus 3."*
- **What Judges Should Notice:** GridFlex proves that *available flexibility $\neq$ electrically useful flexibility*. It does not cheat the physics.

### Scenario 3 — Cloud Event: Quantified Forecast Uncertainty & Reserve Deficit
- **Narrative:** *"At 15:45, a sudden cloud drop creates a steep net-load ramp. Rather than hoping the battery has enough headroom, GridFlex evaluates a rolling 95% uncertainty interval requiring 25.65 kW of dynamic reserve. The battery has 25.00 kW available. Instead of assuming the grid will absorb the error, GridFlex flags an explicit 0.65 kW reserve shortfall to alert distribution operators."*
- **What Judges Should Notice:** The system handles uncertainty through rigorous statistical intervals and declares deficits transparently.

---

## Q. Recommended Master Figures for Presentation

Ranked by presentation utility (no numerical scores assigned):

1. **`03_baseline_vs_gridflex_voltage.png`**  
   - *Demonstrates:* Side-by-side feeder voltage extremes across the diurnal cycle (midday overvoltage eliminated; evening undervoltage honestly displayed).
   - *Target Slide:* Results / Electrical Validation Slide.
   - *Presenter Talk Track:* *"GridFlex completely mitigates the 1.13 p.u. midday solar overvoltage down to 1.01 p.u., while accurately showing the evening lateral undervoltage regime."*

2. **`06_reverse_power_flow.png`**  
   - *Demonstrates:* Substation transformer reverse power flow crashing from 187 kW down to 14 kW.
   - *Target Slide:* Problem 2 / Substation Impact Slide.
   - *Presenter Talk Track:* *"We eliminate 92.5% of reverse power backfeed, preventing substation reverse-flow tripping without expensive network upgrades."*

3. **`09_available_vs_relevant_flexibility.png`**  
   - *Demonstrates:* Total available flexibility vs. locationally relevant flexibility across all feeder constraints.
   - *Target Slide:* Core Innovation / Technical Differentiator Slide.
   - *Presenter Talk Track:* *"This figure encapsulates our core finding: while total available flexibility is abundant, locationally relevant flexibility is strictly constrained by cable impedance."*

4. **`05_baseline_vs_gridflex_line_loading.png`**  
   - *Demonstrates:* Trunk cable congestion relief achieved by smart EV charging throttling.
   - *Target Slide:* Evening Peak / EV Fleet Coordination Slide.
   - *Presenter Talk Track:* *"By throttling flexible EV chargers by 21 kW, we prevent the primary trunk cable from overloading, keeping it under 77% capacity."*

5. **`10_forecast_uncertainty_band.png`**  
   - *Demonstrates:* Rolling Gaussian forecast uncertainty envelope ($\pm 1.96\sigma$) around net load.
   - *Target Slide:* Data & Forecasting Slide.
   - *Presenter Talk Track:* *"GridFlex does not rely on deterministic point forecasts; it dimensions dynamic operating reserves based on a 95% confidence uncertainty band."*

6. **`11_dynamic_operating_envelope.png`**  
   - *Demonstrates:* Inverter export headroom transitioning dynamically between Normal, Constrained, and Critical states.
   - *Target Slide:* Dynamic Operating Envelopes Slide.
   - *Presenter Talk Track:* *"Rather than disconnecting solar panels, GridFlex allocates time-varying export ceilings that keep prosumers online while protecting the feeder."*

7. **`07_battery_soc.png`**  
   - *Demonstrates:* Community battery state of charge respecting 20% floor, 90% ceiling, and dynamic reserve buffer.
   - *Target Slide:* Battery Storage & Reserve Slide.
   - *Presenter Talk Track:* *"The community battery absorbs surplus midday solar and preserves a 10% dynamic reserve buffer for cloud intermittency."*

8. **`12_constraint_timeline.png`**  
   - *Demonstrates:* Chronological matrix of active feeder constraints across the 24-hour horizon.
   - *Target Slide:* Feeder Overview / Scenario Summary Slide.
   - *Presenter Talk Track:* *"Our 24-hour constraint timeline illustrates how feeder stress shifts from solar noon backfeed to evening trunk congestion and lateral undervoltage."*
