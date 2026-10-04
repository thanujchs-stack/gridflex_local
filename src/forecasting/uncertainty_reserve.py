"""Forecast Uncertainty and Forecast-Aware Flexibility Reserve Engine for Problem 4.

Translates 90% prediction intervals into explicit reserve requirements:
Higher uncertainty -> Higher required flexibility reserve -> Less capacity committed away.
Never double-counts committed congestion relief as reserve capacity.
"""

from typing import Dict, Any, List
import numpy as np
import pandas as pd


def compute_forecast_uncertainty_and_reserves(
    pv_forecast_df: pd.DataFrame,
    load_forecast_df: pd.DataFrame,
    net_load_forecast_df: pd.DataFrame,
    passports_df: pd.DataFrame,
    reserve_margin_factor: float = 0.50,
) -> Dict[str, pd.DataFrame]:
    """Compute forecast uncertainty metrics and dynamic reserve allocations.

    Returns:
        Dict with "forecast_uncertainty" and "reserve_requirement" DataFrames.
    """
    timesteps = pv_forecast_df["timestamp"].tolist()
    n_steps = len(timesteps)

    unc_rows = []
    res_rows = []

    for i in range(n_steps):
        ts = str(timesteps[i])

        pv_row = pv_forecast_df.iloc[i]
        load_row = load_forecast_df.iloc[i]
        nl_row = net_load_forecast_df.iloc[i]

        pv_mean = float(pv_row.get("forecast", 0.0))
        pv_lower = float(pv_row.get("lower_bound", pv_mean * 0.8))
        pv_upper = float(pv_row.get("upper_bound", pv_mean * 1.2))
        pv_unc = max(0.0, pv_upper - pv_lower)

        load_mean = float(load_row.get("forecast", 0.0))
        load_lower = float(load_row.get("lower_bound", load_mean * 0.9))
        load_upper = float(load_row.get("upper_bound", load_mean * 1.1))
        load_unc = max(0.0, load_upper - load_lower)

        # Net load uncertainty is the root-sum-square of solar and demand uncertainty
        nl_unc = float(np.sqrt(pv_unc**2 + load_unc**2))
        nl_mean = float(nl_row.get("forecast", load_mean - pv_mean))
        nl_lower = nl_mean - (nl_unc / 2.0)
        nl_upper = nl_mean + (nl_unc / 2.0)

        # Risk state based on net load forecast and uncertainty magnitude
        if nl_upper > 180.0 or nl_lower < -80.0:
            forecast_risk = "ACTION"
        elif nl_upper > 140.0 or nl_lower < -40.0:
            forecast_risk = "WATCH"
        else:
            forecast_risk = "NORMAL"

        unc_rows.append({
            "timestamp": ts,
            "target": "net_load",
            "forecast_mean": round(nl_mean, 2),
            "forecast_lower": round(nl_lower, 2),
            "forecast_upper": round(nl_upper, 2),
            "forecast_uncertainty": round(nl_unc, 2),
            "forecast_risk": forecast_risk,
            "pv_uncertainty_kw": round(pv_unc, 2),
            "load_uncertainty_kw": round(load_unc, 2),
        })

        # Reserve Requirement Calculation:
        # Dynamic reserve requirement scales with 15-minute prediction interval width
        required_reserve_kw = round(nl_unc * reserve_margin_factor, 2)

        # Check actually available reserve in DER fleet without double counting
        step_passports = passports_df[passports_df["timestamp"] == ts]
        # BESS standby capability reserved specifically for frequency/intermittency buffer
        bess_row = step_passports[step_passports["der_type"] == "BESS"]
        bess_avail_up = float(bess_row["available_flexibility_up_kw"].iloc[0]) if not bess_row.empty else 0.0
        bess_dispatched = float(bess_row["dispatched_flexibility_kw"].iloc[0]) if not bess_row.empty else 0.0

        # Uncommitted BESS capacity provides primary reserve
        bess_uncommitted_reserve = max(0.0, bess_avail_up - bess_dispatched)

        # EV standby throttling capability
        ev_rows = step_passports[step_passports["der_type"] == "EV"]
        ev_avail_up = float(ev_rows["available_flexibility_up_kw"].sum())
        ev_dispatched = float(ev_rows["dispatched_flexibility_kw"].sum())
        ev_uncommitted_reserve = max(0.0, ev_avail_up - ev_dispatched)

        total_available_reserve = bess_uncommitted_reserve + ev_uncommitted_reserve
        reserve_shortfall = max(0.0, required_reserve_kw - total_available_reserve)

        res_rows.append({
            "timestamp": ts,
            "required_reserve_kw": required_reserve_kw,
            "available_reserve_kw": round(total_available_reserve, 2),
            "reserve_shortfall_kw": round(reserve_shortfall, 2),
            "bess_reserve_kw": round(bess_uncommitted_reserve, 2),
            "ev_reserve_kw": round(ev_uncommitted_reserve, 2),
            "forecast_uncertainty_kw": round(nl_unc, 2),
            "reserve_status": "SUFFICIENT" if reserve_shortfall == 0.0 else "DEFICIT",
        })

    return {
        "forecast_uncertainty": pd.DataFrame(unc_rows),
        "reserve_requirement": pd.DataFrame(res_rows),
    }
