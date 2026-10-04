"""AC Power Flow Simulation Engine using pandapower.

Executes 15-minute time-series power flow simulations across the LV distribution feeder,
enforcing physical conservation, capturing bus voltages, line currents, and transformer loading.
"""

from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
import pandapower as pp

from src.utils.validation import validate_power_balance


def pf_to_tan(pf: float) -> float:
    """Compute tan(arccos(pf)) for reactive power calculation (lagging)."""
    pf_clamped = max(0.1, min(1.0, pf))
    return float(np.tan(np.arccos(pf_clamped)))


def run_feeder_timeseries_simulation(
    net: pp.pandapowerNet,
    mappings: Dict[str, Any],
    config: Dict[str, Any],
    df_res: pd.DataFrame,
    df_comm: pd.DataFrame,
    df_crit: pd.DataFrame,
    df_ev: pd.DataFrame,
    df_flex: pd.DataFrame,
    df_solar: pd.DataFrame,
    df_bess: pd.DataFrame,
    scenario_name: str = "BASELINE"
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    """Execute complete multi-timestep AC power flow simulation.

    Returns:
        (df_timeseries, df_bus_results, df_line_results, df_trafo_results, summary_metrics)
    """
    timestamps = df_res["timestamp"].tolist()
    n_timesteps = len(timestamps)

    load_idx_map = mappings["load_index_map"]
    sgen_idx_map = mappings["sgen_index_map"]
    bess_der_id = mappings["bess_der_id"]

    res_cols = [c for c in df_res.columns if c != "timestamp"]
    comm_cols = [c for c in df_comm.columns if c != "timestamp"]
    crit_col = [c for c in df_crit.columns if c != "timestamp"][0]
    ev_cols = [c for c in df_ev.columns if c != "timestamp"]
    flex_cols = [c for c in df_flex.columns if c != "timestamp"]
    pv_cols = [c for c in df_solar.columns if c != "timestamp"]

    res_tan = pf_to_tan(config.get("residential_loads", {}).get("power_factor", 0.95))
    comm_tan = pf_to_tan(config.get("commercial_loads", {}).get("power_factor", 0.92))
    crit_tan = pf_to_tan(config.get("critical_facility", {}).get("power_factor", 0.96))
    ev_tan = pf_to_tan(config.get("ev_charging", {}).get("power_factor", 0.98))

    # Output storage arrays
    res_load_tot = np.zeros(n_timesteps)
    comm_load_tot = np.zeros(n_timesteps)
    crit_load_tot = np.zeros(n_timesteps)
    ev_load_tot = np.zeros(n_timesteps)
    flex_load_tot = np.zeros(n_timesteps)
    total_load_tot = np.zeros(n_timesteps)
    pv_gen_tot = np.zeros(n_timesteps)
    bess_power_tot = np.zeros(n_timesteps)
    bess_ch_tot = np.zeros(n_timesteps)
    bess_dis_tot = np.zeros(n_timesteps)

    grid_import_kw = np.zeros(n_timesteps)
    grid_export_kw = np.zeros(n_timesteps)
    net_load_kw = np.zeros(n_timesteps)
    trafo_loading_pct = np.zeros(n_timesteps)
    max_line_loading_pct = np.zeros(n_timesteps)
    min_bus_v_pu = np.zeros(n_timesteps)
    max_bus_v_pu = np.zeros(n_timesteps)
    losses_kw = np.zeros(n_timesteps)
    reverse_flow = np.zeros(n_timesteps, dtype=bool)

    # Detailed tables records
    bus_records = []
    line_records = []
    trafo_records = []

    bus_names = list(net.bus.name.values)
    line_names = list(net.line.name.values)

    for t in range(n_timesteps):
        ts = timestamps[t]

        # 1. Update Residential Loads
        p_res_t = 0.0
        for hid in res_cols:
            kw = float(df_res.loc[t, hid])
            p_res_t += kw
            idx = load_idx_map[hid]
            net.load.loc[idx, "p_mw"] = kw / 1000.0
            net.load.loc[idx, "q_mvar"] = (kw / 1000.0) * res_tan
        res_load_tot[t] = p_res_t

        # 2. Update Commercial Loads
        p_comm_t = 0.0
        for cid in comm_cols:
            kw = float(df_comm.loc[t, cid])
            p_comm_t += kw
            idx = load_idx_map[cid]
            net.load.loc[idx, "p_mw"] = kw / 1000.0
            net.load.loc[idx, "q_mvar"] = (kw / 1000.0) * comm_tan
        comm_load_tot[t] = p_comm_t

        # 3. Update Critical Facility Load
        p_crit_t = float(df_crit.loc[t, crit_col])
        crit_load_tot[t] = p_crit_t
        idx_c = load_idx_map[crit_col]
        net.load.loc[idx_c, "p_mw"] = p_crit_t / 1000.0
        net.load.loc[idx_c, "q_mvar"] = (p_crit_t / 1000.0) * crit_tan

        # 4. Update EV Loads
        p_ev_t = 0.0
        for evid in ev_cols:
            kw = float(df_ev.loc[t, evid])
            p_ev_t += kw
            idx = load_idx_map[evid]
            net.load.loc[idx, "p_mw"] = kw / 1000.0
            net.load.loc[idx, "q_mvar"] = (kw / 1000.0) * ev_tan
        ev_load_tot[t] = p_ev_t

        # 5. Update Flexible Loads
        p_flex_t = 0.0
        for flid in flex_cols:
            kw = float(df_flex.loc[t, flid])
            p_flex_t += kw
            idx = load_idx_map[flid]
            net.load.loc[idx, "p_mw"] = kw / 1000.0
            net.load.loc[idx, "q_mvar"] = 0.0
        flex_load_tot[t] = p_flex_t

        total_demand_kw = p_res_t + p_comm_t + p_crit_t + p_ev_t + p_flex_t
        total_load_tot[t] = total_demand_kw

        # 6. Update Solar PV sgen elements
        p_pv_t = 0.0
        for pvid in pv_cols:
            kw = float(df_solar.loc[t, pvid])
            p_pv_t += kw
            s_idx = sgen_idx_map[pvid]
            net.sgen.loc[s_idx, "p_mw"] = kw / 1000.0
            net.sgen.loc[s_idx, "q_mvar"] = 0.0
        pv_gen_tot[t] = p_pv_t

        # 7. Update BESS sgen element (positive = injection/discharge)
        p_bess_act = float(df_bess.loc[t, "bess_power_kw"])
        p_bess_ch = float(df_bess.loc[t, "bess_charge_kw"])
        p_bess_dis = float(df_bess.loc[t, "bess_discharge_kw"])
        bess_power_tot[t] = p_bess_act
        bess_ch_tot[t] = p_bess_ch
        bess_dis_tot[t] = p_bess_dis

        s_bess_idx = sgen_idx_map[bess_der_id]
        # In pandapower sgen: positive p_mw injects power into the bus
        net.sgen.loc[s_bess_idx, "p_mw"] = p_bess_act / 1000.0
        net.sgen.loc[s_bess_idx, "q_mvar"] = 0.0

        # 8. Execute AC Power Flow
        try:
            pp.runpp(net, algorithm="nr", calculate_voltage_angles=True, enforce_q_lims=False, numba=False)
        except Exception as e:
            raise RuntimeError(
                f"Power flow failed to converge at timestep {t} ({ts}) in scenario {scenario_name}. "
                f"Conditions: Total Load={total_demand_kw:.2f} kW, PV={p_pv_t:.2f} kW. Error: {str(e)}"
            )

        # 9. Extract Results
        # Slack bus active power (MW -> kW)
        p_ext_grid_mw = float(net.res_ext_grid.p_mw.iloc[0])
        p_grid_net_kw = p_ext_grid_mw * 1000.0

        if p_grid_net_kw >= 0:
            grid_import_kw[t] = p_grid_net_kw
            grid_export_kw[t] = 0.0
            reverse_flow[t] = False
        else:
            grid_import_kw[t] = 0.0
            grid_export_kw[t] = abs(p_grid_net_kw)
            reverse_flow[t] = True

        net_load_kw[t] = total_demand_kw - p_pv_t

        # Transformer loading
        trafo_load = float(net.res_trafo.loading_percent.iloc[0])
        trafo_loading_pct[t] = trafo_load

        # Line loading
        max_line_load = float(net.res_line.loading_percent.max())
        max_line_loading_pct[t] = max_line_load

        # Bus voltages (only LV buses for distribution analysis)
        lv_bus_indices = net.bus[net.bus.zone != "MV"].index
        vm_lv = net.res_bus.loc[lv_bus_indices, "vm_pu"]
        min_bus_v_pu[t] = float(vm_lv.min())
        max_bus_v_pu[t] = float(vm_lv.max())

        # Network losses (trafo pl_mw + line pl_mw in kW)
        line_pl_kw = float(net.res_line.pl_mw.sum() * 1000.0)
        trafo_pl_kw = float(net.res_trafo.pl_mw.sum() * 1000.0)
        losses_kw[t] = line_pl_kw + trafo_pl_kw

        # Detailed record collections
        for b_i, b_nm in zip(net.bus.index, bus_names):
            bus_records.append({
                "timestamp": ts,
                "bus_id": b_i,
                "bus_name": b_nm,
                "vm_pu": float(net.res_bus.loc[b_i, "vm_pu"]),
                "va_degree": float(net.res_bus.loc[b_i, "va_degree"]),
                "p_mw": float(net.res_bus.loc[b_i, "p_mw"]),
                "q_mvar": float(net.res_bus.loc[b_i, "q_mvar"])
            })

        for l_i, l_nm in zip(net.line.index, line_names):
            line_records.append({
                "timestamp": ts,
                "line_id": l_i,
                "line_name": l_nm,
                "loading_percent": float(net.res_line.loc[l_i, "loading_percent"]),
                "i_ka": float(net.res_line.loc[l_i, "i_ka"]),
                "pl_mw": float(net.res_line.loc[l_i, "pl_mw"]),
                "ql_mvar": float(net.res_line.loc[l_i, "ql_mvar"])
            })

        trafo_records.append({
            "timestamp": ts,
            "trafo_name": str(net.trafo.name.iloc[0]),
            "loading_percent": trafo_load,
            "p_hv_mw": float(net.res_trafo.p_hv_mw.iloc[0]),
            "q_hv_mvar": float(net.res_trafo.q_hv_mvar.iloc[0]),
            "p_lv_mw": float(net.res_trafo.p_lv_mw.iloc[0]),
            "q_lv_mvar": float(net.res_trafo.q_lv_mvar.iloc[0]),
            "pl_mw": float(net.res_trafo.pl_mw.iloc[0])
        })

    # Assemble main timeseries dataframe
    df_ts = pd.DataFrame({
        "timestamp": timestamps,
        "total_load_kw": np.round(total_load_tot, 3),
        "residential_load_kw": np.round(res_load_tot, 3),
        "commercial_load_kw": np.round(comm_load_tot, 3),
        "critical_load_kw": np.round(crit_load_tot, 3),
        "ev_load_kw": np.round(ev_load_tot, 3),
        "flexible_load_kw": np.round(flex_load_tot, 3),
        "pv_generation_kw": np.round(pv_gen_tot, 3),
        "battery_power_kw": np.round(bess_power_tot, 3),
        "battery_soc": df_bess["soc"].to_numpy(),
        "grid_import_kw": np.round(grid_import_kw, 3),
        "grid_export_kw": np.round(grid_export_kw, 3),
        "net_load_kw": np.round(net_load_kw, 3),
        "transformer_loading_pct": np.round(trafo_loading_pct, 2),
        "max_line_loading_pct": np.round(max_line_loading_pct, 2),
        "min_bus_voltage_pu": np.round(min_bus_v_pu, 4),
        "max_bus_voltage_pu": np.round(max_bus_v_pu, 4),
        "network_losses_kw": np.round(losses_kw, 3),
        "reverse_power_flow": reverse_flow
    })

    df_bus_res = pd.DataFrame(bus_records)
    df_line_res = pd.DataFrame(line_records)
    df_trafo_res = pd.DataFrame(trafo_records)

    # Validate Power Balance
    # Inflow = grid_import + pv + bess_discharge
    # Outflow = total_load + bess_charge + losses + grid_export
    p_balance_grid_in = df_ts["grid_import_kw"] - df_ts["grid_export_kw"]
    max_err, mean_err, failed_steps, _ = validate_power_balance(
        p_grid_import=df_ts["grid_import_kw"] - df_ts["grid_export_kw"],
        p_pv_generation=df_ts["pv_generation_kw"],
        p_bess_discharge=pd.Series(bess_dis_tot),
        p_total_load=df_ts["total_load_kw"],
        p_bess_charge=pd.Series(bess_ch_tot),
        p_losses=df_ts["network_losses_kw"],
        tolerance_kw=float(config.get("validation", {}).get("power_balance_tolerance_kw", 1.0))
    )

    metrics = {
        "scenario": scenario_name,
        "timesteps": n_timesteps,
        "power_flow_converged": True,
        "power_balance_max_error_kw": round(max_err, 4),
        "power_balance_mean_error_kw": round(mean_err, 4),
        "power_balance_failed_timesteps": failed_steps,
        "peak_transformer_loading_pct": round(float(trafo_loading_pct.max()), 2),
        "peak_line_loading_pct": round(float(max_line_loading_pct.max()), 2),
        "min_voltage_pu": round(float(min_bus_v_pu.min()), 4),
        "max_voltage_pu": round(float(max_bus_v_pu.max()), 4),
        "reverse_power_flow_timesteps": int(reverse_flow.sum()),
        "total_losses_kwh": round(float(losses_kw.sum() * 0.25), 2)
    }

    return df_ts, df_bus_res, df_line_res, df_trafo_res, metrics
