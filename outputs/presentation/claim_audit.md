# GridFlex Local — Presentation Claim Audit

This audit evaluates phrases, technical terms, and claims across project documentation, reports, code, and presentation materials. It identifies potentially misleading statements, flags why they could be challenged by power systems judges, and provides exact, defensible replacement wording.

---

### Audit Table of Evaluated Claims

| # | Topic / Evaluated Claim | Source Location | Risk / Challenge by Technical Judges | Recommended Defensible Wording |
|:---:|:---|:---|:---|:---|
| **1** | *"GridFlex solves grid congestion / solves grid problems"* | General narrative / informal speech | **Overclaim:** GridFlex does not solve all constraints. Specifically, evening lateral undervoltage at `Bus_Residential_3` remains unresolved due to radial cable resistance and lack of local downstream flexibility. | *"GridFlex coordinates available DER flexibility to mitigate local distribution constraints within physical network limits."* |
| **2** | *"100% reliable / guaranteed reliability"* | Pitch draft | **Overclaim:** GridFlex is a steady-state flexibility coordination software layer; it does not model protection relays, fault ride-through, recloser tripping, or outage restoration. | *"Maintains 100% mathematical AC power-flow convergence and rigorous power balance across all evaluated simulation timesteps."* |
| **3** | *"Autonomous field deployment / live control"* | Architecture description | **Overclaim:** The prototype generates validated setpoints and dynamic operating envelopes; it does not connect to live energized utility hardware or communicate with live proprietary inverters in the field. | *"A validated digital twin and software prototype designed for eventual integration with utility edge gateways and smart inverters."* |
| **4** | *"SAIDI / SAIFI / ENS reliability improvements"* | Utility pitch template | **Overclaim:** In grid-connected distribution simulation with an active substation slack bus, Energy Not Served (ENS) is 0.0 kWh. Reliability indices (SAIDI/SAIFI) measure physical interruptions, which are outside the model scope. | *"Demonstrates voltage compliance and thermal congestion relief during grid-connected operation; makes no claims regarding customer interruption indices."* |
| **5** | *"Vehicle-to-Grid (V2G) capability"* | EV feature inquiries | **Factually inaccurate for current prototype:** V2G is strictly disabled in the model to avoid customer battery warranty issues and reflect unidirectional Level 2 AC charger realities. | *"EV fleet participation is strictly unidirectional smart throttling (0 kW to 7.4 kW charging rate), with 100% departure energy compliance guaranteed."* |
| **6** | *"Universally optimal dispatch"* | Optimization section | **Overclaim:** Multi-objective heuristics and linear/quadratic approximations in distribution optimization are locally optimal for the formulated objective, not globally optimal across all future stochastic states. | *"Produces constraint-compliant schedules that prioritize statutory voltage bounds and transformer reverse-power limits."* |
| **7** | *"100 Indian households measured"* | Feeder description | **Potential Misrepresentation:** While calibrated to Indian LV feeder density and voltages, the load curves are synthesized from public benchmark smart meter datasets (Pecan Street, CREST), not measured from 100 physical homes in an Indian utility. | *"A digital twin feeder model parameterized to reflect representative urban/peri-urban LV distribution characteristics, utilizing open benchmark load profiles."* |
| **8** | *"Exact electrical sensitivity coefficients"* | Locational flexibility description | **Technical Precision:** The locational relevance factors (1.0, 0.65, 0.35, 0.05, 0.0) are derived from radial topological path impedance and line length ratios, not computed from an inverted Jacobian matrix ($\partial V / \partial P$). | *"A transparent, topology-based locational relevance model derived from physical branch impedances and downstream/upstream radial relationships."* |
| **9** | *"Eliminates all reverse flow"* | Solar mitigation slide | **Numerical Inaccuracy:** Reverse flow is not reduced to 0.0 kW; it is reduced from 187.05 kW to 14.01 kW (a 92.5% reduction, keeping it safely below the 25 kW reverse threshold). | *"Suppresses reverse power flow by 92.5% (from 187.05 kW down to 14.01 kW), keeping backfeed strictly within utility transformer limits."* |
| **10** | *"Hardware-ready inverter controller"* | System summary | **Premature:** Requires standard communication protocol stacks (IEEE 2030.5 / SunSpec Modbus / CSIP) to interface with physical hardware in the field. | *"Software architecture produces standardized dynamic operating envelopes ready to be ingested by IEEE 2030.5 prosumer gateways."* |

---

### Mandatory Speaking Rules for Presenters

1. **Rule 1 (The Evening Problem):** Never claim GridFlex solves the evening undervoltage. Say: *"The evening undervoltage demonstrates our locational differentiator: available upstream flexibility cannot solve downstream cable drop."*
2. **Rule 2 (The Reserve Shortfall):** Never hide the 0.65 kW cloud reserve deficit. Say: *"GridFlex explicitly identifies when forecast uncertainty exceeds available dynamic reserves."*
3. **Rule 3 (The High-PV Success):** Always cite the exact verified AC power-flow numbers: *"Maximum voltage reduced from 1.1316 to 1.0146 p.u., and reverse power reduced from 187.05 to 14.01 kW."*
4. **Rule 4 (The Technology Boundary):** Always clarify that GridFlex is an edge coordination overlay, not a replacement for utility ADMS or SCADA systems.
