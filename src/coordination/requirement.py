"""Calculation of flexibility requirements from forecast grid conditions.

Translates Phase 3 forecast risk signals, loading margins, and voltage deviations
into directional (UP/DOWN/SHIFT) power flexibility requirements.
"""

from typing import Dict, Any, List, Optional
import numpy as np
import pandas as pd


def calculate_flexibility_requirements(
    risk_forecast_df: pd.DataFrame,
    config: Dict[str, Any],
) -> pd.DataFrame:
    """Calculate required flexibility for each timestep based on physical constraints.

    Args:
        risk_forecast_df: DataFrame with 'timestamp', 'horizon_minutes', 'operational_state',
                          'trafo_loading_pct', 'max_line_loading_pct', 'min_vm_pu', 'max_vm_pu',
                          'net_load_kw', 'primary_constraint'.
        config: System configuration dictionary.

    Returns:
        DataFrame containing flexibility requirements per timestep:
        [timestamp, horizon_minutes, risk_state, primary_constraint,
         required_up_kw, required_down_kw, required_shift_kw,
         constraint_type, constraint_location, explanation]
    """
    val_cfg = config.get("validation", {})
    trafo_warn_pct = float(val_cfg.get("transformer_warning_pct", 80.0))
    trafo_sn_kva = float(config.get("network", {}).get("transformer", {}).get("sn_mva", 0.250)) * 1000.0
    trafo_rated_kw = trafo_sn_kva * 0.95  # 237.5 kW active power at 0.95 pf

    v_min_thresh = float(val_cfg.get("min_voltage_pu", 0.94))
    v_max_thresh = float(val_cfg.get("max_voltage_pu", 1.06))

    records = []

    for _, row in risk_forecast_df.iterrows():
        t = pd.to_datetime(row["timestamp"])
        h_mins = int(row["horizon_minutes"])
        state = str(row["operational_state"])
        prim_constraint = str(row["primary_constraint"])

        trafo_load = float(row["trafo_loading_pct"])
        line_load = float(row.get("max_line_loading_pct", 0.0))
        min_v = float(row["min_vm_pu"])
        max_v = float(row["max_vm_pu"])
        net_p = float(row["net_load_kw"])

        req_up = 0.0
        req_down = 0.0
        req_shift = 0.0
        constraint_type = "NONE"
        constraint_loc = "NONE"
        notes = []

        # 1. UP Requirement: Forward grid stress / high demand / undervoltage
        # Relieve transformer if exceeding warning threshold
        trafo_excess_kw = 0.0
        if trafo_load > trafo_warn_pct:
            trafo_excess_kw = ((trafo_load - trafo_warn_pct) / 100.0) * trafo_rated_kw
            constraint_type = "TRANSFORMER_OVERLOAD"
            constraint_loc = "Bus_Main_LV / DT_11_0.415_250kVA"
            notes.append(f"Transformer loading {trafo_load:.1f}% > {trafo_warn_pct:.0f}%")

        # Relieve undervoltage if below nominal operating margin (0.955 p.u.)
        voltage_up_relief_kw = 0.0
        if min_v < 0.955:
            # Empirical sensitivity ~ 80 kW per 0.05 p.u. voltage drop
            v_drop_mag = max(0.0, 0.955 - min_v)
            voltage_up_relief_kw = (v_drop_mag / 0.05) * 80.0
            if trafo_excess_kw == 0.0:
                constraint_type = "VOLTAGE_DROP"
                constraint_loc = "Bus_Residential_3"
            notes.append(f"Bus voltage {min_v:.4f} p.u. < 0.955 p.u.")

        req_up = max(trafo_excess_kw, voltage_up_relief_kw)

        # 2. DOWN Requirement: Surplus solar export / overvoltage
        if max_v > 1.035:
            v_rise_mag = max_v - 1.035
            req_down = (v_rise_mag / 0.025) * 40.0
            constraint_type = "VOLTAGE_RISE"
            constraint_loc = "Bus_Residential_1 / Rooftop PV Hub"
            notes.append(f"Overvoltage {max_v:.4f} p.u. > 1.035 p.u.")

        # 3. SHIFT Requirement: Portion of evening UP requirement allocatable to demand shifting
        hour_float = t.hour + t.minute / 60.0
        is_evening_shift_window = (hour_float >= 17.0) and (hour_float <= 22.0)
        if req_up > 0.0 and is_evening_shift_window:
            # Flexible loads and EV throttles can provide up to 50% of the UP relief via shifting
            req_shift = req_up * 0.50

        # Normal condition: zero requirements
        if state == "NORMAL" and req_up == 0.0 and req_down == 0.0:
            notes.append("Feeder operates within normal boundaries; no flexibility required")

        records.append({
            "timestamp": t,
            "horizon_minutes": h_mins,
            "risk_state": state,
            "constraint_type": constraint_type,
            "constraint_location": constraint_loc,
            "required_up_kw": round(req_up, 2),
            "required_down_kw": round(req_down, 2),
            "required_shift_kw": round(req_shift, 2),
            "explanation": "; ".join(notes) if notes else "No constraint",
        })

    return pd.DataFrame(records)
