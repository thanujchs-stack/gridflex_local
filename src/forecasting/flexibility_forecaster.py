"""Forward Flexibility Forecasting for GridFlex Local.

Projects forward available and technical flexibility across the 16-step
(4-hour) horizon, enforcing Phase 2 passports, participation rates,
SOC bounds, and schedule constraints without activating dispatch.
"""

from typing import Dict, List, Any, Optional
import numpy as np
import pandas as pd


def forecast_available_flexibility(
    forecast_timestamps: List[pd.Timestamp],
    pv_forecast_kw: np.ndarray,
    config: Dict[str, Any],
    bess_current_soc: float = 0.50,
) -> pd.DataFrame:
    """Project forward flexibility capacity across 16 future 15-minute timesteps.

    Args:
        forecast_timestamps: List of 16 future pandas Timestamps (t+15 to t+240).
        pv_forecast_kw: Array of 16 forecast PV values (kW) for the neighbourhood.
        config: System configuration dictionary.
        bess_current_soc: State of charge of community BESS at forecast origin.

    Returns:
        DataFrame with projected UP, DOWN, and SHIFT flexibility by DER category.
    """
    n_steps = len(forecast_timestamps)
    dt_h = 15.0 / 60.0  # 0.25 hours

    flex_cfg = config.get("flexibility", {})
    participation_rate = float(flex_cfg.get("default_participation_rate", 0.70))

    # 1. Community Battery Parameters
    bat_cfg = config.get("battery", {})
    e_cap = float(bat_cfg.get("energy_capacity_kwh", 100.0))
    p_ch_max = float(bat_cfg.get("max_charge_kw", 25.0))
    p_dis_max = float(bat_cfg.get("max_discharge_kw", 25.0))
    soc_min = float(bat_cfg.get("min_soc", 0.20))
    soc_max = float(bat_cfg.get("max_soc", 0.90))
    soc_reserve = float(flex_cfg.get("battery", {}).get("reserve_soc", 0.10))
    eta_ch = float(bat_cfg.get("charge_efficiency", 0.95))
    eta_dis = float(bat_cfg.get("discharge_efficiency", 0.95))

    # Effective operational SOC floor respecting reserve
    soc_floor = soc_min + soc_reserve  # 0.30

    # 2. EV Charging Parameters
    ev_cfg = config.get("ev_charging", {})
    n_evs = int(config.get("neighbourhood", {}).get("ev_count", 20))
    ev_p_rated = float(ev_cfg.get("charger_rating_kw", 7.4))
    ev_arr_mean = float(ev_cfg.get("arrival_hour_mean", 19.0))
    ev_dep_mean = float(ev_cfg.get("departure_hour_mean", 7.5))

    # 3. Flexible Loads
    flex_loads = config.get("flexible_loads", [])

    rows = []

    for i in range(n_steps):
        t = pd.to_datetime(forecast_timestamps[i])
        hour_float = t.hour + t.minute / 60.0
        horizon_mins = (i + 1) * 15

        # --- A. BESS Flexibility ---
        # Up-flexibility: discharge headroom down to soc_floor
        headroom_discharge_kwh = max(0.0, (bess_current_soc - soc_floor) * e_cap)
        max_disch_power_kwh = headroom_discharge_kwh * eta_dis / dt_h
        bat_up_avail = min(p_dis_max, max_disch_power_kwh)
        bat_up_tech = min(p_dis_max, max(0.0, (bess_current_soc - soc_min) * e_cap) * eta_dis / dt_h)

        # Down-flexibility: charge headroom up to soc_max
        headroom_charge_kwh = max(0.0, (soc_max - bess_current_soc) * e_cap)
        max_charge_power_kwh = (headroom_charge_kwh / eta_ch) / dt_h
        bat_down_avail = min(p_ch_max, max_charge_power_kwh)
        bat_down_tech = min(p_ch_max, max_charge_power_kwh)

        # --- B. PV Downward Flexibility (Curtailment) ---
        fc_pv = float(pv_forecast_kw[i]) if i < len(pv_forecast_kw) else 0.0
        pv_down_tech = max(0.0, fc_pv)
        pv_down_avail = max(0.0, fc_pv * participation_rate)
        pv_up_avail = 0.0  # PV cannot inject beyond available solar resource

        # --- C. EV Charging Flexibility ---
        # EV active charging window typically evening/night (18:30 - 02:00)
        # Fraction of EVs connected and charging based on diurnal probability
        is_charging_window = (hour_float >= 18.0) or (hour_float <= 2.0)
        if is_charging_window:
            charging_prob = 0.65 if (19.0 <= hour_float <= 23.5) else 0.30
        else:
            charging_prob = 0.05

        active_ev_kw = n_evs * charging_prob * ev_p_rated
        ev_down_tech = active_ev_kw
        ev_down_avail = active_ev_kw * participation_rate

        # --- D. Flexible Loads Flexibility ---
        fl_active_tech = 0.0
        fl_active_avail = 0.0
        for fl in flex_loads:
            s_h = float(fl.get("start_hour", 0.0))
            e_h = float(fl.get("end_hour", 24.0))
            r_kw = float(fl.get("rated_kw", 0.0))
            if s_h <= hour_float < e_h:
                fl_active_tech += r_kw
                fl_active_avail += r_kw * participation_rate

        # Aggregated forward available flexibility
        total_up_avail = bat_up_avail
        total_down_avail = bat_down_avail + pv_down_avail + ev_down_avail + fl_active_avail
        total_shiftable = fl_active_avail

        total_up_tech = bat_up_tech
        total_down_tech = bat_down_tech + pv_down_tech + ev_down_tech + fl_active_tech

        rows.append({
            "timestamp": t,
            "horizon_minutes": horizon_mins,
            "bess_soc_origin": round(bess_current_soc, 3),
            "bess_up_kw": round(bat_up_avail, 2),
            "bess_down_kw": round(bat_down_avail, 2),
            "pv_down_kw": round(pv_down_avail, 2),
            "ev_down_kw": round(ev_down_avail, 2),
            "flexible_load_down_kw": round(fl_active_avail, 2),
            "total_up_available_kw": round(total_up_avail, 2),
            "total_down_available_kw": round(total_down_avail, 2),
            "total_shiftable_available_kw": round(total_shiftable, 2),
            "total_up_technical_kw": round(total_up_tech, 2),
            "total_down_technical_kw": round(total_down_tech, 2),
            "participation_rate": participation_rate,
        })

    return pd.DataFrame(rows)
