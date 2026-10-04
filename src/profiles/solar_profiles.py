"""Rooftop Solar PV profile generator and intermittency scenario transformer.

Generates diverse residential solar generation curves grounded in clear-sky
insolation geometry, and provides controlled cloud intermittency scenario injection.
"""

from typing import Any, Dict, List, Tuple
import numpy as np
import pandas as pd


def generate_solar_profiles(
    config: Dict[str, Any],
    time_index: pd.DatetimeIndex,
    household_ids: List[str]
) -> Tuple[pd.DataFrame, Dict[str, Dict[str, Any]]]:
    """Generate ~60 residential rooftop PV systems distributed across households.

    Features:
    - Clear-sky solar radiation envelope between sunrise (~06:00) and sunset (~18:15)
    - Peak irradiance at ~12:30
    - Capacity diversity (2.0 to 6.0 kW, mean ~3.5 kW)
    - Inverter clipping constraint: 0 <= pv_kw <= capacity_kw
    """
    seed = config["simulation"].get("random_seed", 42) + 300
    rng = np.random.default_rng(seed)

    solar_cfg = config.get("solar", {})
    pv_penetration = config["neighbourhood"].get("pv_penetration", 0.60)
    min_cap = solar_cfg.get("min_capacity_kw", 2.0)
    max_cap = solar_cfg.get("max_capacity_kw", 6.0)
    mean_cap = solar_cfg.get("mean_capacity_kw", 3.5)
    std_cap = solar_cfg.get("std_capacity_kw", 1.0)
    peak_hr = solar_cfg.get("peak_sun_hour", 12.5)
    sunrise = solar_cfg.get("sunrise_hour", 6.0)
    sunset = solar_cfg.get("sunset_hour", 18.25)
    pf = float(solar_cfg.get("power_factor", 1.0))

    # Determine which households receive rooftop PV
    n_households = len(household_ids)
    n_pv = int(round(n_households * pv_penetration))
    chosen_hids = sorted(rng.choice(household_ids, size=n_pv, replace=False))

    hour_float = time_index.hour + time_index.minute / 60.0
    daylight_mask = (hour_float > sunrise) & (hour_float < sunset)

    # Base normalized solar shape (half-sine between sunrise and sunset)
    day_length = sunset - sunrise
    norm_time = (hour_float - sunrise) / day_length
    norm_solar = np.where(daylight_mask, np.sin(np.pi * norm_time), 0.0)
    # Sharpen slightly to match typical global horizontal / tilted irradiance profile
    norm_solar = np.where(norm_solar > 0, norm_solar ** 1.15, 0.0)

    pv_profiles = {"timestamp": time_index.strftime("%Y-%m-%d %H:%M")}
    pv_metadata = {}

    for idx, hid in enumerate(chosen_hids, start=1):
        der_id = f"PV_{hid}"
        # Sample capacity from truncated normal distribution
        raw_cap = rng.normal(mean_cap, std_cap)
        capacity_kw = float(np.round(np.clip(raw_cap, min_cap, max_cap), 2))

        # Individual tilt / orientation / shading variation factor
        orientation_factor = rng.uniform(0.92, 1.05)
        # Small micro-fluctuation (aerosols / atmospheric haze)
        micro_variation = 1.0 + rng.normal(0.0, 0.015, size=len(time_index))

        pv_kw = norm_solar * capacity_kw * orientation_factor * micro_variation
        pv_kw = np.clip(pv_kw, 0.0, capacity_kw)
        pv_kw = np.where(daylight_mask, pv_kw, 0.0)

        pv_profiles[der_id] = np.round(pv_kw, 4)
        pv_metadata[der_id] = {
            "der_id": der_id,
            "household_id": hid,
            "der_type": "PV",
            "capacity_kw": capacity_kw,
            "power_factor": pf,
            "daily_yield_kwh": float(np.round(np.sum(pv_kw) * 0.25, 2)),
            "peak_kw": float(np.round(np.max(pv_kw), 3))
        }

    df_solar = pd.DataFrame(pv_profiles)
    return df_solar, pv_metadata


def apply_cloud_event(
    df_solar: pd.DataFrame,
    config: Dict[str, Any]
) -> pd.DataFrame:
    """Create the PV_CLOUD_EVENT_V1 scenario by applying a temporary irradiance dip.

    Does NOT mutate the original dataframe; returns a new transformed scenario.
    During cloud event window [start_time, end_time], PV generation is scaled by pv_factor.
    """
    cloud_cfg = config.get("cloud_event", {})
    start_str = cloud_cfg.get("start_time", "15:00")
    end_str = cloud_cfg.get("end_time", "16:00")
    factor = float(cloud_cfg.get("pv_factor", 0.30))

    df_scenario = df_solar.copy()
    ts_col = pd.to_datetime(df_scenario["timestamp"])
    time_strs = ts_col.dt.strftime("%H:%M")

    # Cloud window mask (inclusive of start, up to end)
    cloud_mask = (time_strs >= start_str) & (time_strs <= end_str)

    pv_cols = [c for c in df_scenario.columns if c != "timestamp"]
    for col in pv_cols:
        df_scenario.loc[cloud_mask, col] = np.round(df_scenario.loc[cloud_mask, col] * factor, 4)

    return df_scenario
