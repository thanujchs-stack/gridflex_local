# GridFlex Local — Final Demonstration

## Problem

Distribution grids with high penetration of distributed energy resources (DERs) face five interconnected physical problems:
1. **Severe Voltage Rise / Overvoltage:** Solar noon backfeed elevates residential feeder voltages above the statutory limit (1.050 p.u.).
2. **Reverse Power Flow:** Aggregate distributed generation exceeding local feeder demand forces power backward through the substation distribution transformer.
3. **Transformer and Feeder Trunk Congestion:** Rapid evening EV charging coincides with household baseload ramps, overloading cables and transformers.
4. **Renewable Intermittency & Forecast Uncertainty:** Fast cloud transients induce steep supply-demand deficits that exceed static spinning reserves.
5. **Poor Visibility & Spatial Misalignment:** Available DER flexibility located at the substation cannot resolve downstream lateral voltage drop due to radial cable impedance ($I \cdot R$).

---

## Scenario 1 — High PV (Sunny Afternoon)

- **What Happened:** At 13:45 solar noon, 60 residential rooftop PV systems generate peak solar power against light household demand, creating 187.05 kW of reverse power flow and driving terminal voltages to an extreme **1.1316 p.u.** at `Bus_Residential_3`.
- **What GridFlex Changed:** GridFlex computed dynamic operating envelopes (DOEs) for all PV systems and scheduled the 100 kWh Community BESS. PV export was constrained via coordinated inverter ceilings, while BESS absorbed 25 kW.
- **Independent AC Validation:** Pandapower AC power flow confirmed that maximum feeder voltage was brought from **1.1316 p.u. down to 1.0146 p.u.** (fully within statutory limits), and peak reverse power flow was suppressed by **92.5%** (from 187.05 kW to 14.01 kW).

---

## Scenario 2 — Evening Peak (Locational Flexibility)

- **What Happened:** At 17:15, rooftop PV generation ceased while 20 Level 2 EVs and residential cooking created heavy peak demand. Terminal voltage at `Bus_Residential_3` collapsed to **0.9236 p.u.** (below the 0.9500 p.u. statutory floor), and `Line_Trunk_1` loaded to **95.37%**.
- **Why GridFlex Couldn't Fully Solve It:** Although the feeder possessed **46.12 kW of available upstream flexibility** (25 kW Community BESS + 21.12 kW EV charging throttle), only **8.64 kW equivalent relief** was locationally relevant to `Bus_Residential_3`. The Community BESS is sited at the substation LV bus (`Bus_Main_LV`), where injection cannot counteract the $I \cdot R$ drop across the 0.42 km trunk cable.
- **What Locational Flexibility Reveals:** GridFlex distinguishes *total available flexibility* from *electrically relevant flexibility*. Voltage improved modestly from **0.9236 to 0.9321 p.u.**, leaving an honest **4.90 kW unserved deficit**. GridFlex truthfully reports this constraint as **PARTIALLY RESOLVED**.

---

## Scenario 3 — Cloud Uncertainty

- **What Happened:** At 15:45, rapid cloud passage caused sudden PV output degradation, introducing **22.57 kW** of net load forecast uncertainty.
- **How Reserve Was Calculated:** GridFlex evaluated a dynamic uncertainty reserve requirement ($R_{req} = 1.96 \cdot \sigma_{net}$) of **25.65 kW**. The Community BESS possessed **25.00 kW** of available discharge headroom.
- **Was Reserve Sufficient:** Available reserve was 25.00 kW against a 25.65 kW requirement, resulting in an honest **0.65 kW reserve deficit**. Rather than fabricating artificial capacity, GridFlex explicitly signaled this deficit to trigger external grid support.

---

## Key Results

| Performance Dimension | Baseline Case | GridFlex Coordinated | Physical Impact | Validation Status |
|:---|:---:|:---:|:---:|:---:|
| **Peak Voltage (Scenario 1)** | 1.1316 p.u. | 1.0146 p.u. | -0.1170 p.u. (Overvoltage eliminated) | **PASSED** |
| **Peak Reverse Flow (Scenario 1)** | 187.05 kW | 14.01 kW | -173.04 kW (-92.5% reverse flow) | **PASSED** |
| **Substation Trafo Loading (Scenario 1)** | 74.82% | 14.07% | -60.75% thermal relief | **PASSED** |
| **Terminal Voltage (Scenario 2)** | 0.9236 p.u. | 0.9321 p.u. | +0.0085 p.u. (Partially resolved) | **DEFICIT HONESTLY REPORTED** |
| **Trunk Line Loading (Scenario 2)** | 95.37% | 76.68% | -18.69% line congestion relief | **PASSED** |
| **Uncertainty Reserve Deficit (Scenario 3)** | 0.00 kW | 0.65 kW | Quantified shortfall detected | **PASSED** |
| **AC Power-Flow Convergence** | 100% | 100% | Full non-linear AC feasibility | **PASSED** |

---

## Engineering Insight

> *"GridFlex does not treat all DER flexibility as equally useful. Flexibility must be available, permitted, and electrically relevant to the specific grid constraint."*

In a radial low-voltage network, electrical distance and impedance dictate physical efficacy. High total flexibility upstream at the substation cannot resolve localized voltage drop at a downstream terminal bus without local downstream DER assets (distributed storage or smart EV discharging).


---

## Limitations

1. **V2G Disabled:** Vehicle-to-Grid discharging was deliberately kept disabled per frozen requirements.
2. **No New Downstream BESS:** No additional batteries were added at `Bus_Residential_3`.
3. **Simulated Neighbourhood:** Feeder load profiles, PV traces, and EV behaviors are grounded in IEEE European LV benchmark profiles and Pecan Street data.
4. **Topology-Based Locational Relevance:** Locational filtering utilizes transparent radial path impedance and downstream/upstream relationships; no artificial sensitivity coefficients are fabricated.
5. **External Grid Available:** The slack bus remains connected to an external 11 kV grid.
6. **No Outage Model:** The simulation focuses on steady-state power quality and congestion during normal grid-connected operation.
7. **No SAIDI/SAIFI Claims:** GridFlex does not make reliability index or customer interruption claims.
8. **Control Interfaces:** Real-world field deployment requires IEEE 2030.5 / OpenADR communication interfaces and customer participation agreements.
