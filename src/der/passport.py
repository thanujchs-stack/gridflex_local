"""Comprehensive DER Flexibility Passport Engine for GridFlex Local.

Implements the formal 4-tier flexibility hierarchy:
1. Technical Flexibility: Theoretical physical capability of the device.
2. Available Flexibility: Derated by operating state, SOC, arrival/departure, and owner opt-in.
3. Selectable Flexibility: Filtered by operating envelopes, network capacity, and reserve locks.
4. Dispatched Flexibility: Final optimized allocation from Phase 6.

Maintains all 24 required passport fields for every DER and timestep.
"""

from typing import Dict, Any, List, Optional
import numpy as np
import pandas as pd


def generate_der_flexibility_passports(
    config: Dict[str, Any],
    der_registry_df: pd.DataFrame,
    timesteps: List[pd.Timestamp],
    pv_forecast_df: pd.DataFrame,
    load_forecast_df: pd.DataFrame,
    participation_rate: float = 0.70,
    envelopes_df: Optional[pd.DataFrame] = None,
    dispatched_df: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Construct complete 24-field DER Flexibility Passport across all assets and timesteps.

    Returns:
        DataFrame matching outputs/csv/der_flexibility_passport.csv.
    """
    passport_rows = []
    n_steps = len(timesteps)
    dt_hours = 0.25

    # Asset category configurations
    bess_cfg = config.get("battery", {})
    bess_id = bess_cfg.get("der_id", "BESS_COMMUNITY_01")
    bess_cap = float(bess_cfg.get("energy_capacity_kwh", 100.0))
    bess_max_p = float(bess_cfg.get("max_discharge_kw", 25.0))
    bess_min_soc = float(bess_cfg.get("min_soc", 0.20))
    bess_max_soc = float(bess_cfg.get("max_soc", 0.90))
    bess_reserve_soc = 0.30

    # EV parameters
    ev_cfg = config.get("ev_charging", {})
    ev_rated_p = float(ev_cfg.get("charger_rating_kw", 7.4))
    ev_cap = float(ev_cfg.get("battery_capacity_kwh", 40.0))

    # Flexible loads
    flex_loads_cfg = {fl["load_id"]: fl for fl in config.get("flexible_loads", [])}

    for t_idx, ts in enumerate(timesteps):
        hour_float = ts.hour + ts.minute / 60.0

        # Solar irradiance factor for timestamp
        pv_fc_row = pv_forecast_df.iloc[min(t_idx, len(pv_forecast_df) - 1)]
        solar_ratio = float(pv_fc_row["forecast"]) / max(1.0, float(pv_forecast_df["forecast"].max()))

        for _, der in der_registry_df.iterrows():
            did = str(der["der_id"])
            dtype = str(der["der_type"])
            bus_id = str(der.get("bus_id", "Bus_Main_LV"))
            rated_kw = float(der.get("rated_capacity_kw", 5.0))
            rated_kwh = float(der.get("rated_energy_kwh", 0.0)) if pd.notna(der.get("rated_energy_kwh")) else 0.0

            # Deterministic owner participation
            is_participating = (hash(did) % 100 < participation_rate * 100)
            if dtype == "BESS":
                is_participating = True  # Community asset always participates

            # -----------------------------------------------------------------
            # 1. PV INVERTER PASSPORT
            # -----------------------------------------------------------------
            if dtype == "PV":
                control_perm = bool(config.get("flexibility", {}).get("pv", {}).get("curtailment_allowed_default", True))
                avail_start = "06:00"
                avail_end = "18:15"
                is_daylight = 6.0 <= hour_float <= 18.25

                current_power = rated_kw * solar_ratio if is_daylight else 0.0
                baseline_power = current_power
                avail_power = current_power

                # Technical: Inverter can curtail down to 0
                tech_up = 0.0  # PV cannot produce more than solar irradiance
                tech_down = current_power

                # Available: derated by participation and control permission
                avail_up = 0.0
                avail_down = tech_down if (is_participating and control_perm) else 0.0

                # Selectable: bounded by Phase 5 envelope export limit if present
                dyn_max = rated_kw
                if envelopes_df is not None:
                    match_env = envelopes_df[(envelopes_df["timestamp"] == str(ts)) & (envelopes_df["der_id"] == did)]
                    if not match_env.empty:
                        dyn_max = float(match_env["dynamic_max_kw"].iloc[0])

                selectable_down = min(avail_down, max(0.0, current_power - dyn_max)) if dyn_max < current_power else avail_down
                selectable_up = 0.0

                # Dispatched
                dispatched_down = 0.0
                if dispatched_df is not None:
                    match_disp = dispatched_df[(dispatched_df["timestamp"] == str(ts)) & (dispatched_df["der_id"] == did)]
                    if not match_disp.empty:
                        dispatched_down = float(match_disp["allocated_flex_kw"].iloc[0])

                passport_rows.append({
                    "timestamp": str(ts),
                    "der_id": did,
                    "der_type": dtype,
                    "bus_id": bus_id,
                    "rated_power_kw": round(rated_kw, 2),
                    "current_power_kw": round(current_power, 2),
                    "available_power_kw": round(avail_power, 2),
                    "energy_capacity_kwh": 0.0,
                    "soc_percent": np.nan,
                    "min_soc_percent": np.nan,
                    "max_soc_percent": np.nan,
                    "response_time_min": 1.0,
                    "availability_start": avail_start,
                    "availability_end": avail_end,
                    "owner_participation": is_participating,
                    "flexibility_enabled": is_participating,
                    "control_permission": control_perm,
                    "baseline_power_kw": round(baseline_power, 2),
                    "technical_flexibility_up_kw": round(tech_up, 2),
                    "technical_flexibility_down_kw": round(tech_down, 2),
                    "available_flexibility_up_kw": round(avail_up, 2),
                    "available_flexibility_down_kw": round(avail_down, 2),
                    "selectable_flexibility_up_kw": round(selectable_up, 2),
                    "selectable_flexibility_down_kw": round(selectable_down, 2),
                    "dispatched_flexibility_kw": round(dispatched_down, 2),
                    "shiftable_energy_kwh": 0.0,
                    "v2g_enabled": False,
                })

            # -----------------------------------------------------------------
            # 2. COMMUNITY BESS PASSPORT
            # -----------------------------------------------------------------
            elif dtype == "BESS":
                control_perm = True
                avail_start = "00:00"
                avail_end = "23:45"
                current_power = 0.0  # Idle baseline
                baseline_power = 0.0
                soc = 0.50

                # Technical flexibility: max charge / discharge ratings
                tech_up = bess_max_p    # Discharge relieves grid
                tech_down = bess_max_p  # Charge absorbs power

                # Available flexibility: derated by SOC margins above reserve
                headroom_disch_kwh = max(0.0, (soc - bess_reserve_soc) * bess_cap)
                headroom_chg_kwh = max(0.0, (bess_max_soc - soc) * bess_cap)
                avail_up = min(tech_up, headroom_disch_kwh / dt_hours)
                avail_down = min(tech_down, headroom_chg_kwh / dt_hours)

                # Selectable: bounded by Phase 5 envelope
                dyn_max_chg = bess_max_p
                dyn_max_disch = bess_max_p
                if envelopes_df is not None:
                    match_env = envelopes_df[(envelopes_df["timestamp"] == str(ts)) & (envelopes_df["der_id"] == did)]
                    if not match_env.empty:
                        dyn_max_disch = float(match_env["dynamic_max_kw"].iloc[0])

                selectable_up = min(avail_up, dyn_max_disch)
                selectable_down = min(avail_down, dyn_max_chg)

                dispatched_p = 0.0
                if dispatched_df is not None:
                    match_disp = dispatched_df[(dispatched_df["timestamp"] == str(ts)) & (dispatched_df["der_id"] == did)]
                    if not match_disp.empty:
                        dispatched_p = float(match_disp["allocated_flex_kw"].iloc[0])

                passport_rows.append({
                    "timestamp": str(ts),
                    "der_id": did,
                    "der_type": dtype,
                    "bus_id": bus_id,
                    "rated_power_kw": round(bess_max_p, 2),
                    "current_power_kw": round(current_power, 2),
                    "available_power_kw": round(bess_max_p, 2),
                    "energy_capacity_kwh": round(bess_cap, 2),
                    "soc_percent": round(soc * 100.0, 1),
                    "min_soc_percent": round(bess_min_soc * 100.0, 1),
                    "max_soc_percent": round(bess_max_soc * 100.0, 1),
                    "response_time_min": 1.0,
                    "availability_start": avail_start,
                    "availability_end": avail_end,
                    "owner_participation": True,
                    "flexibility_enabled": True,
                    "control_permission": True,
                    "baseline_power_kw": 0.0,
                    "technical_flexibility_up_kw": round(tech_up, 2),
                    "technical_flexibility_down_kw": round(tech_down, 2),
                    "available_flexibility_up_kw": round(avail_up, 2),
                    "available_flexibility_down_kw": round(avail_down, 2),
                    "selectable_flexibility_up_kw": round(selectable_up, 2),
                    "selectable_flexibility_down_kw": round(selectable_down, 2),
                    "dispatched_flexibility_kw": round(dispatched_p, 2),
                    "shiftable_energy_kwh": round(headroom_disch_kwh, 2),
                    "v2g_enabled": False,
                })

            # -----------------------------------------------------------------
            # 3. EV CHARGING PASSPORT
            # -----------------------------------------------------------------
            elif dtype == "EV":
                control_perm = bool(config.get("flexibility", {}).get("ev", {}).get("smart_charging_allowed_default", True))
                avail_start = "18:00"
                avail_end = "07:30"
                # Connected status during horizon (13:30 to 17:15)
                # Evening commuters begin plugging in around 16:30 - 17:15
                ev_num = int(did.split("_")[-1]) if "_" in did else 1
                arrival_hour = 16.5 + (ev_num % 4) * 0.25  # Staggered 16:30, 16:45, 17:00, 17:15
                is_connected = (hour_float >= arrival_hour) or (hour_float <= 7.5)

                baseline_power = ev_rated_p if is_connected else 0.0
                current_power = baseline_power
                avail_power = ev_rated_p if is_connected else 0.0

                # Technical: Can throttle down from rated power
                tech_up = ev_rated_p if is_connected else 0.0  # Throttling demand relieves grid (UP relief)
                tech_down = 0.0

                # Available: derated by participation
                avail_up = tech_up if (is_participating and control_perm) else 0.0
                avail_down = 0.0

                # Selectable: bounded by Phase 5 envelope
                dyn_max = ev_rated_p
                if envelopes_df is not None:
                    match_env = envelopes_df[(envelopes_df["timestamp"] == str(ts)) & (envelopes_df["der_id"] == did)]
                    if not match_env.empty:
                        dyn_max = float(match_env["dynamic_max_kw"].iloc[0])

                selectable_up = min(avail_up, max(0.0, baseline_power - dyn_max)) if dyn_max < baseline_power else avail_up
                selectable_down = 0.0

                dispatched_throttle = 0.0
                if dispatched_df is not None:
                    match_disp = dispatched_df[(dispatched_df["timestamp"] == str(ts)) & (dispatched_df["der_id"] == did)]
                    if not match_disp.empty:
                        dispatched_throttle = float(match_disp["allocated_flex_kw"].iloc[0])

                passport_rows.append({
                    "timestamp": str(ts),
                    "der_id": did,
                    "der_type": dtype,
                    "bus_id": bus_id,
                    "rated_power_kw": round(ev_rated_p, 2),
                    "current_power_kw": round(current_power, 2),
                    "available_power_kw": round(avail_power, 2),
                    "energy_capacity_kwh": round(ev_cap, 2),
                    "soc_percent": 40.0 if is_connected else np.nan,
                    "min_soc_percent": 20.0,
                    "max_soc_percent": 90.0,
                    "response_time_min": 5.0,
                    "availability_start": avail_start,
                    "availability_end": avail_end,
                    "owner_participation": is_participating,
                    "flexibility_enabled": is_participating,
                    "control_permission": control_perm,
                    "baseline_power_kw": round(baseline_power, 2),
                    "technical_flexibility_up_kw": round(tech_up, 2),
                    "technical_flexibility_down_kw": round(tech_down, 2),
                    "available_flexibility_up_kw": round(avail_up, 2),
                    "available_flexibility_down_kw": round(avail_down, 2),
                    "selectable_flexibility_up_kw": round(selectable_up, 2),
                    "selectable_flexibility_down_kw": round(selectable_down, 2),
                    "dispatched_flexibility_kw": round(dispatched_throttle, 2),
                    "shiftable_energy_kwh": round(ev_rated_p * dt_hours if is_connected else 0.0, 2),
                    "v2g_enabled": False,
                })

            # -----------------------------------------------------------------
            # 4. FLEXIBLE DEMAND PASSPORT
            # -----------------------------------------------------------------
            elif dtype == "FLEXIBLE_LOAD":
                fl_spec = flex_loads_cfg.get(did, {})
                fl_start = float(fl_spec.get("start_hour", 9.0))
                fl_end = float(fl_spec.get("end_hour", 17.5))
                is_active = (fl_start <= hour_float <= fl_end)

                current_power = rated_kw if is_active else 0.0
                baseline_power = current_power
                avail_power = rated_kw if is_active else 0.0

                tech_up = rated_kw if is_active else 0.0  # Shedding/shifting demand provides UP relief
                tech_down = 0.0

                avail_up = tech_up if is_participating else 0.0
                avail_down = 0.0

                dyn_max = rated_kw
                if envelopes_df is not None:
                    match_env = envelopes_df[(envelopes_df["timestamp"] == str(ts)) & (envelopes_df["der_id"] == did)]
                    if not match_env.empty:
                        dyn_max = float(match_env["dynamic_max_kw"].iloc[0])

                selectable_up = min(avail_up, max(0.0, baseline_power - dyn_max)) if dyn_max < baseline_power else avail_up
                selectable_down = 0.0

                dispatched_shift = 0.0
                if dispatched_df is not None:
                    match_disp = dispatched_df[(dispatched_df["timestamp"] == str(ts)) & (dispatched_df["der_id"] == did)]
                    if not match_disp.empty:
                        dispatched_shift = float(match_disp["allocated_flex_kw"].iloc[0])

                passport_rows.append({
                    "timestamp": str(ts),
                    "der_id": did,
                    "der_type": dtype,
                    "bus_id": bus_id,
                    "rated_power_kw": round(rated_kw, 2),
                    "current_power_kw": round(current_power, 2),
                    "available_power_kw": round(avail_power, 2),
                    "energy_capacity_kwh": 0.0,
                    "soc_percent": np.nan,
                    "min_soc_percent": np.nan,
                    "max_soc_percent": np.nan,
                    "response_time_min": 15.0,
                    "availability_start": f"{int(fl_start):02d}:00",
                    "availability_end": f"{int(fl_end):02d}:00",
                    "owner_participation": is_participating,
                    "flexibility_enabled": is_participating,
                    "control_permission": True,
                    "baseline_power_kw": round(baseline_power, 2),
                    "technical_flexibility_up_kw": round(tech_up, 2),
                    "technical_flexibility_down_kw": round(tech_down, 2),
                    "available_flexibility_up_kw": round(avail_up, 2),
                    "available_flexibility_down_kw": round(avail_down, 2),
                    "selectable_flexibility_up_kw": round(selectable_up, 2),
                    "selectable_flexibility_down_kw": round(selectable_down, 2),
                    "dispatched_flexibility_kw": round(dispatched_shift, 2),
                    "shiftable_energy_kwh": round(rated_kw * dt_hours if is_active else 0.0, 2),
                    "v2g_enabled": False,
                })

    return pd.DataFrame(passport_rows)
