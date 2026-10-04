"""Power-flow validation for Phase 5 Dynamic Operating Envelopes.

Simulates Case A (Static baseline envelope) vs Case B (GridFlex dynamic operating envelope)
using the Phase 1 pandapower feeder model across the entire forecast horizon.
"""

from typing import Dict, Any, Optional
import numpy as np
import pandas as pd
import pandapower as pp

from src.utils.config import load_config
from src.network.feeder import build_feeder_topology
from src.profiles.load_profiles import generate_time_index, generate_residential_profiles
from src.profiles.solar_profiles import generate_solar_profiles


def evaluate_envelope_powerflow(
    envelopes_df: pd.DataFrame,
    net_load_forecast_df: pd.DataFrame,
    pv_forecast_df: pd.DataFrame,
    config: Optional[Dict[str, Any]] = None,
) -> pd.DataFrame:
    """Run pandapower AC power flow comparing Case A (Static baseline) vs Case B (Dynamic DOE).

    Returns:
        DataFrame saved to outputs/csv/envelope_validation.csv
    """
    if config is None:
        config = load_config()

    # Build reference network
    t_idx = generate_time_index(start_date="2026-01-15", duration_days=1)
    res_df, _ = generate_residential_profiles(config, t_idx)
    hh_ids = [c for c in res_df.columns if c != "timestamp"]
    _, pv_meta = generate_solar_profiles(config, t_idx, hh_ids)

    comm_ids = [f"COM_{i:02d}" for i in range(1, config.get("neighbourhood", {}).get("commercial_consumers", 5) + 1)]
    crit_id = config.get("critical_facility", {}).get("facility_id", "CRIT_001")
    ev_ids = [f"EV_{i:03d}" for i in range(1, config.get("neighbourhood", {}).get("ev_count", 20) + 1)]
    flex_ids = [fl["load_id"] for fl in config.get("flexible_loads", [])]

    net, mappings = build_feeder_topology(
        config=config,
        household_ids=hh_ids,
        pv_metadata=pv_meta,
        comm_ids=comm_ids,
        crit_id=crit_id,
        ev_ids=ev_ids,
        flex_ids=flex_ids,
    )

    load_map = mappings["load_index_map"]
    sgen_map = mappings["sgen_index_map"]
    bess_id = mappings["bess_der_id"]

    tan_res = np.tan(np.arccos(config.get("residential_loads", {}).get("power_factor", 0.95)))
    n_hh = len(hh_ids)
    n_pv = len(pv_meta)

    envelopes_df = envelopes_df.copy()
    envelopes_df["timestamp"] = pd.to_datetime(envelopes_df["timestamp"])
    timesteps = envelopes_df["timestamp"].drop_duplicates().tolist()
    results = []

    for i, t in enumerate(timesteps):
        nl_row = net_load_forecast_df.iloc[min(i, len(net_load_forecast_df) - 1)]
        pv_row = pv_forecast_df.iloc[min(i, len(pv_forecast_df) - 1)]
        step_envs = envelopes_df[envelopes_df["timestamp"] == t]

        base_load_kw = float(nl_row["forecast"]) + float(pv_row["forecast"])
        base_pv_kw = float(pv_row["forecast"])

        # Determine dynamic modifications from envelopes
        # In Case B:
        # 1. BESS dynamic discharge (UP relief)
        bat_env = step_envs[step_envs["der_type"] == "BESS"]
        bat_discharge_kw = float(bat_env["allocated_flex_kw"].iloc[0]) if not bat_env.empty else 0.0

        # 2. PV dynamic curtailment (DOWN relief)
        pv_envs = step_envs[step_envs["der_type"] == "PV"]
        total_pv_curt = float(np.maximum(0.0, pv_envs["available_pv_kw"] - pv_envs["dynamic_export_limit_kw"]).sum())

        # 3. EV dynamic throttling (UP relief)
        ev_envs = step_envs[step_envs["der_type"] == "EV"]
        total_ev_throttle = float(ev_envs["allocated_flex_kw"].sum())

        # 4. Flexible load shift (UP relief)
        fl_envs = step_envs[step_envs["der_type"] == "FLEXIBLE_LOAD"]
        total_fl_shift = float(fl_envs["allocated_flex_kw"].sum())

        total_up_relief = bat_discharge_kw + total_ev_throttle + total_fl_shift

        # ----------------------------------------------------
        # CASE A: STATIC BASELINE (Unconstrained normal operation)
        # ----------------------------------------------------
        hh_p_base = (base_load_kw / max(1, n_hh)) / 1000.0
        for hid in hh_ids:
            l_idx = load_map[hid]
            net.load.at[l_idx, "p_mw"] = hh_p_base
            net.load.at[l_idx, "q_mvar"] = hh_p_base * tan_res

        pv_p_base = (base_pv_kw / max(1, n_pv)) / 1000.0
        for pid in sgen_map:
            if pid != bess_id:
                s_idx = sgen_map[pid]
                net.sgen.at[s_idx, "p_mw"] = pv_p_base
                net.sgen.at[s_idx, "q_mvar"] = 0.0

        # BESS idle in baseline
        net.sgen.at[sgen_map[bess_id], "p_mw"] = 0.0
        net.sgen.at[sgen_map[bess_id], "q_mvar"] = 0.0

        converged_base = True
        try:
            pp.runpp(net, enforce_q_lims=False, calculate_voltage_angles=True)
            t_load_base = float(net.res_trafo["loading_percent"].max())
            l_load_base = float(net.res_line["loading_percent"].max())
            min_vm_base = float(net.res_bus["vm_pu"].min())
            max_vm_base = float(net.res_bus["vm_pu"].max())
            ext_grid_p_base = float(net.res_ext_grid["p_mw"].sum()) * 1000.0
        except Exception:
            converged_base = False
            t_load_base = np.nan
            l_load_base = np.nan
            min_vm_base = np.nan
            max_vm_base = np.nan
            ext_grid_p_base = np.nan

        # ----------------------------------------------------
        # CASE B: DYNAMIC OPERATING ENVELOPE (Bounded operation)
        # ----------------------------------------------------
        # Apply load reduction from EV throttle + FL shift
        dyn_load_kw = max(0.0, base_load_kw - (total_ev_throttle + total_fl_shift))
        hh_p_dyn = (dyn_load_kw / max(1, n_hh)) / 1000.0
        for hid in hh_ids:
            l_idx = load_map[hid]
            net.load.at[l_idx, "p_mw"] = hh_p_dyn
            net.load.at[l_idx, "q_mvar"] = hh_p_dyn * tan_res

        # Apply PV export limits
        dyn_pv_kw = max(0.0, base_pv_kw - total_pv_curt)
        pv_p_dyn = (dyn_pv_kw / max(1, n_pv)) / 1000.0
        for pid in sgen_map:
            if pid != bess_id:
                s_idx = sgen_map[pid]
                net.sgen.at[s_idx, "p_mw"] = pv_p_dyn
                net.sgen.at[s_idx, "q_mvar"] = 0.0

        # Apply BESS dynamic injection
        bess_p_dyn = (bat_discharge_kw) / 1000.0
        net.sgen.at[sgen_map[bess_id], "p_mw"] = bess_p_dyn
        net.sgen.at[sgen_map[bess_id], "q_mvar"] = 0.0

        converged_dyn = True
        try:
            pp.runpp(net, enforce_q_lims=False, calculate_voltage_angles=True)
            t_load_dyn = float(net.res_trafo["loading_percent"].max())
            l_load_dyn = float(net.res_line["loading_percent"].max())
            min_vm_dyn = float(net.res_bus["vm_pu"].min())
            max_vm_dyn = float(net.res_bus["vm_pu"].max())
            ext_grid_p_dyn = float(net.res_ext_grid["p_mw"].sum()) * 1000.0
        except Exception:
            converged_dyn = False
            t_load_dyn = np.nan
            l_load_dyn = np.nan
            min_vm_dyn = np.nan
            max_vm_dyn = np.nan
            ext_grid_p_dyn = np.nan

        results.append({
            "timestamp": t,
            "horizon_minutes": (i + 1) * 15,
            "baseline_trafo_loading_pct": round(t_load_base, 2),
            "dynamic_trafo_loading_pct": round(t_load_dyn, 2),
            "loading_reduction_pct": round(max(0.0, t_load_base - t_load_dyn), 2),
            "baseline_max_line_loading_pct": round(l_load_base, 2),
            "dynamic_max_line_loading_pct": round(l_load_dyn, 2),
            "baseline_min_vm_pu": round(min_vm_base, 4),
            "dynamic_min_vm_pu": round(min_vm_dyn, 4),
            "voltage_improvement_pu": round(max(0.0, min_vm_dyn - min_vm_base), 4),
            "baseline_max_vm_pu": round(max_vm_base, 4),
            "dynamic_max_vm_pu": round(max_vm_dyn, 4),
            "baseline_grid_import_kw": round(ext_grid_p_base, 2),
            "dynamic_grid_import_kw": round(ext_grid_p_dyn, 2),
            "reverse_power_flow_active": bool(ext_grid_p_base < -0.1 or ext_grid_p_dyn < -0.1),
            "powerflow_converged_baseline": converged_base,
            "powerflow_converged_dynamic": converged_dyn,
        })

    return pd.DataFrame(results)
