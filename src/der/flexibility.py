"""DER Flexibility Assessment and Aggregation Engine.

Evaluates technical vs available flexibility across all DER assets at each timestep,
respecting asset availability, owner participation, SOC reserves, and power ratings
without double-counting.
"""

from typing import Any, Dict, List, Tuple
import pandas as pd
import numpy as np

from src.der.constraints import DERConstraintManager


def compute_flexibility_timeseries(
    config: Dict[str, Any],
    df_der_reg: pd.DataFrame,
    df_der_ts: pd.DataFrame,
    participation_map: Dict[str, bool]
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Compute availability, DER-level flexibility, and neighbourhood aggregated summary.

    Returns:
        (df_availability, df_flex_ts, df_flex_summary)
    """
    timestamps = df_der_ts["timestamp"].tolist()
    n_timesteps = len(timestamps)
    dt_hours = 0.25  # 15 minutes = 0.25 hours

    constraint_mgr = DERConstraintManager(config)
    bess_cfg = config.get("battery", {})
    bess_limits = constraint_mgr.get_battery_effective_limits(
        energy_capacity_kwh=float(bess_cfg.get("energy_capacity_kwh", 100.0)),
        min_soc=float(bess_cfg.get("min_soc", 0.20)),
        max_soc=float(bess_cfg.get("max_soc", 0.90))
    )
    bess_max_dis_kw = float(bess_cfg.get("max_discharge_kw", 25.0))
    bess_max_ch_kw = float(bess_cfg.get("max_charge_kw", 25.0))
    bess_cap_kwh = float(bess_cfg.get("energy_capacity_kwh", 100.0))
    bess_eta_dis = float(bess_cfg.get("discharge_efficiency", 0.95))
    bess_eta_ch = float(bess_cfg.get("charge_efficiency", 0.95))

    # Parse hour floats for schedule checks
    time_series_dt = pd.to_datetime(timestamps)
    hour_floats = time_series_dt.hour + time_series_dt.minute / 60.0

    # Availability table: timestamp + col per DER
    availability_dict = {"timestamp": timestamps}
    flex_records = []

    # Pre-extract asset metadata
    asset_dict = {}
    for _, row in df_der_reg.iterrows():
        did = str(row["der_id"])
        asset_dict[did] = {
            "type": str(row["der_type"]),
            "rated_kw": float(row["rated_capacity_kw"]),
            "rated_kwh": float(row["rated_energy_kwh"]) if pd.notna(row.get("rated_energy_kwh")) else 0.0
        }

    # Summary tracking arrays
    sum_pv_down = np.zeros(n_timesteps)
    sum_bess_up = np.zeros(n_timesteps)
    sum_bess_down = np.zeros(n_timesteps)
    sum_ev_down = np.zeros(n_timesteps)
    sum_fl_down = np.zeros(n_timesteps)
    sum_total_up = np.zeros(n_timesteps)
    sum_total_down = np.zeros(n_timesteps)
    sum_total_shift = np.zeros(n_timesteps)
    count_participating = np.zeros(n_timesteps, dtype=int)
    count_available = np.zeros(n_timesteps, dtype=int)

    # Initialize availability columns
    for did in asset_dict:
        availability_dict[did] = np.zeros(n_timesteps, dtype=bool)

    # 1. Compute per-DER flexibility at each timestep
    for t in range(n_timesteps):
        ts = timestamps[t]
        hr = hour_floats[t]

        t_avail_count = 0
        t_part_count = 0

        for did, ainfo in asset_dict.items():
            dtype = ainfo["type"]
            rated_kw = ainfo["rated_kw"]
            participates = participation_map.get(did, False)

            # Baseline power at timestep t
            if did in df_der_ts.columns:
                p_base = float(df_der_ts.loc[t, did])
            else:
                p_base = 0.0

            is_available = False
            tech_up = 0.0
            tech_down = 0.0
            avail_up = 0.0
            avail_down = 0.0
            avail_shift = 0.0
            energy_flex_kwh = 0.0

            if dtype == "PV":
                # PV is available when solar generation is physically positive
                if p_base > 0.01:
                    is_available = True
                    tech_down = p_base  # Technical curtailment limit is actual output
                    if participates:
                        avail_down = p_base
                    energy_flex_kwh = avail_down * dt_hours

            elif dtype == "BESS":
                # Current SOC in Phase 1 baseline is tracked in df_der_ts
                soc_val = float(df_der_ts.loc[t, "BESS_COMMUNITY_01_soc"]) if "BESS_COMMUNITY_01_soc" in df_der_ts.columns else 0.50
                curr_kwh = soc_val * bess_cap_kwh

                # Upward flexibility (Discharge headroom above minimum + reserve):
                # E_dis = max(0, curr_kwh - usable_min_kwh)
                avail_dis_energy_kwh = max(0.0, curr_kwh - bess_limits["usable_min_kwh"])
                # Power that could be sustained over dt_hours without breaching reserve
                p_dis_headroom_kw = min(bess_max_dis_kw, (avail_dis_energy_kwh * bess_eta_dis) / dt_hours)
                tech_up = p_dis_headroom_kw

                # Downward flexibility (Charging headroom below maximum SOC):
                avail_ch_energy_kwh = max(0.0, bess_limits["max_kwh"] - curr_kwh)
                p_ch_headroom_kw = min(bess_max_ch_kw, avail_ch_energy_kwh / (bess_eta_ch * dt_hours))
                tech_down = p_ch_headroom_kw

                # BESS is available if it has either charging or discharging headroom
                is_available = (tech_up > 0.01 or tech_down > 0.01)

                if participates and is_available:
                    avail_up = tech_up
                    avail_down = tech_down
                    energy_flex_kwh = avail_dis_energy_kwh + avail_ch_energy_kwh

            elif dtype == "EV":
                # EV is available only while actively connected / charging
                if p_base > 0.01:
                    is_available = True
                    tech_down = p_base  # Can throttle baseline charging down to 0
                    if participates:
                        avail_down = p_base
                        # Shiftable flexibility equals charging power that can be deferred
                        avail_shift = p_base
                    energy_flex_kwh = avail_down * dt_hours

            elif dtype == "FLEXIBLE_LOAD":
                # Flexible loads have predefined operating windows
                if p_base > 0.01:
                    is_available = True
                    tech_down = p_base  # Can shed or postpone scheduled baseline demand
                    if participates:
                        avail_down = p_base
                        avail_shift = p_base
                    energy_flex_kwh = avail_down * dt_hours

            # Record availability
            availability_dict[did][t] = is_available
            if is_available:
                t_avail_count += 1
                if participates:
                    t_part_count += 1

            # Accumulate summary totals
            if dtype == "PV":
                sum_pv_down[t] += avail_down
            elif dtype == "BESS":
                sum_bess_up[t] += avail_up
                sum_bess_down[t] += avail_down
            elif dtype == "EV":
                sum_ev_down[t] += avail_down
            elif dtype == "FLEXIBLE_LOAD":
                sum_fl_down[t] += avail_down

            sum_total_up[t] += avail_up
            sum_total_down[t] += avail_down
            sum_total_shift[t] += avail_shift

            flex_records.append({
                "timestamp": ts,
                "der_id": did,
                "der_type": dtype,
                "tech_flex_up_kw": round(tech_up, 3),
                "tech_flex_down_kw": round(tech_down, 3),
                "flex_up_kw": round(avail_up, 3),
                "flex_down_kw": round(avail_down, 3),
                "flex_shiftable_kw": round(avail_shift, 3),
                "energy_flexibility_kwh": round(energy_flex_kwh, 3),
                "available": is_available,
                "participating": participates
            })

        count_available[t] = t_avail_count
        count_participating[t] = t_part_count

    df_avail = pd.DataFrame(availability_dict)
    df_flex_ts = pd.DataFrame(flex_records)

    df_flex_summary = pd.DataFrame({
        "timestamp": timestamps,
        "pv_down_kw": np.round(sum_pv_down, 3),
        "battery_up_kw": np.round(sum_bess_up, 3),
        "battery_down_kw": np.round(sum_bess_down, 3),
        "ev_down_kw": np.round(sum_ev_down, 3),
        "flexible_load_down_kw": np.round(sum_fl_down, 3),
        "total_up_kw": np.round(sum_total_up, 3),
        "total_down_kw": np.round(sum_total_down, 3),
        "total_shiftable_kw": np.round(sum_total_shift, 3),
        "participating_der_count": count_participating,
        "available_der_count": count_available
    })

    return df_avail, df_flex_ts, df_flex_summary
