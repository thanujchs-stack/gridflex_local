"""Power-flow evaluator for forward forecast scenarios.

Uses pandapower AC power flow to evaluate voltage margins, line loadings,
and transformer loading for future forecast timesteps WITHOUT dispatching DERs.
"""

from typing import Dict, List, Any, Tuple, Optional
import copy
import numpy as np
import pandas as pd
import pandapower as pp

from src.utils.config import load_config
from src.network.feeder import build_feeder_topology
from src.profiles.load_profiles import generate_time_index, generate_residential_profiles
from src.profiles.solar_profiles import generate_solar_profiles


def evaluate_forecast_powerflow(
    forecast_df: pd.DataFrame,
    pv_forecast_df: pd.DataFrame,
    config: Optional[Dict[str, Any]] = None,
) -> pd.DataFrame:
    """Run pandapower AC power flow across 16 forecast horizon timesteps.

    Args:
        forecast_df: 16-row DataFrame with 'timestamp', 'forecast' (gross load in kW), 'upper_bound'.
        pv_forecast_df: 16-row DataFrame with 'timestamp', 'forecast' (solar generation in kW).
        config: Feeder configuration dictionary.

    Returns:
        DataFrame containing power-flow results for each future timestep:
        [timestamp, horizon_minutes, trafo_loading_pct, trafo_loading_upper_pct,
         max_line_loading_pct, min_vm_pu, max_vm_pu, converged]
    """
    if config is None:
        config = load_config()

    # Build reference feeder topology
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

    # Baseline nominal power factors
    tan_res = np.tan(np.arccos(config.get("residential_loads", {}).get("power_factor", 0.95)))
    tan_comm = np.tan(np.arccos(config.get("commercial_loads", {}).get("power_factor", 0.92)))

    # Household load distribution weights
    n_hh = len(hh_ids)
    n_pv = len(pv_meta)

    # Reference baseline capacities
    trafo_sn_mva = float(config.get("network", {}).get("transformer", {}).get("sn_mva", 0.250))
    trafo_rated_kw = trafo_sn_mva * 1000.0 * 0.95  # approx 237.5 kW active at 0.95 pf

    results = []

    for i in range(len(forecast_df)):
        row_fc = forecast_df.iloc[i]
        row_pv = pv_forecast_df.iloc[i]

        t = pd.to_datetime(row_fc["timestamp"])
        horizon_mins = int(row_fc.get("horizon_minutes", (i + 1) * 15))
        p_load_kw = float(row_fc["forecast"])
        p_load_upper_kw = float(row_fc.get("upper_bound", p_load_kw))
        p_pv_kw = float(row_pv["forecast"])

        # Reset all loads and sgens in net
        net.load["p_mw"] = 0.0
        net.load["q_mvar"] = 0.0
        net.sgen["p_mw"] = 0.0
        net.sgen["q_mvar"] = 0.0

        # Distribute point forecast load across residential buses
        p_per_hh_mw = (p_load_kw * 0.85 / n_hh) / 1000.0
        q_per_hh_mvar = p_per_hh_mw * tan_res
        for hid in hh_ids:
            if hid in load_map:
                idx = load_map[hid]
                net.load.at[idx, "p_mw"] = max(0.0, p_per_hh_mw)
                net.load.at[idx, "q_mvar"] = max(0.0, q_per_hh_mvar)

        # Distribute commercial and critical load
        p_comm_mw = (p_load_kw * 0.12 / max(1, len(comm_ids))) / 1000.0
        for cid in comm_ids:
            if cid in load_map:
                idx = load_map[cid]
                net.load.at[idx, "p_mw"] = max(0.0, p_comm_mw)
                net.load.at[idx, "q_mvar"] = max(0.0, p_comm_mw * tan_comm)

        if crit_id in load_map:
            idx = load_map[crit_id]
            p_crit_mw = (p_load_kw * 0.03) / 1000.0
            net.load.at[idx, "p_mw"] = max(0.0, p_crit_mw)
            net.load.at[idx, "q_mvar"] = max(0.0, p_crit_mw * 0.29)

        # Distribute PV generation across solar inverters
        p_per_pv_mw = (p_pv_kw / max(1, n_pv)) / 1000.0
        for pid in pv_meta.keys():
            if pid in sgen_map:
                s_idx = sgen_map[pid]
                net.sgen.at[s_idx, "p_mw"] = max(0.0, p_per_pv_mw)
                net.sgen.at[s_idx, "q_mvar"] = 0.0

        # Community BESS is strictly idle (Phase 3 does not dispatch)
        if bess_id in sgen_map:
            b_idx = sgen_map[bess_id]
            net.sgen.at[b_idx, "p_mw"] = 0.0
            net.sgen.at[b_idx, "q_mvar"] = 0.0

        # Execute power flow
        converged = True
        try:
            pp.runpp(net, algorithm="nr", enforce_q_lims=True, calculate_voltage_angles=True)
            trafo_loading = float(net.res_trafo["loading_percent"].max())
            max_line_loading = float(net.res_line["loading_percent"].max())
            min_vm = float(net.res_bus["vm_pu"].min())
            max_vm = float(net.res_bus["vm_pu"].max())
        except Exception:
            converged = False
            # Physical linear approximation fallback
            net_kw = max(0.0, p_load_kw - p_pv_kw)
            trafo_loading = (net_kw / (trafo_sn_mva * 1000.0)) * 100.0
            max_line_loading = trafo_loading * 0.70
            min_vm = max(0.90, 1.00 - (net_kw / 5000.0))
            max_vm = 1.00

        # Also estimate transformer loading under upper bound uncertainty
        net_upper_kw = max(0.0, p_load_upper_kw - (p_pv_kw * 0.8))
        trafo_loading_upper = (net_upper_kw / (trafo_sn_mva * 1000.0)) * 100.0

        results.append({
            "timestamp": t,
            "horizon_minutes": horizon_mins,
            "trafo_loading_pct": round(trafo_loading, 2),
            "trafo_loading_upper_pct": round(trafo_loading_upper, 2),
            "max_line_loading_pct": round(max_line_loading, 2),
            "min_vm_pu": round(min_vm, 4),
            "max_vm_pu": round(max_vm, 4),
            "converged": converged,
        })

    return pd.DataFrame(results)
