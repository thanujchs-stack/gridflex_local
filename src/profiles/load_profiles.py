"""Residential, commercial, critical, and flexible load profile generators.

Produces synthetic yet representative time-series demand curves for a neighbourhood
connected to a low-voltage distribution feeder, with controlled consumer diversity.
"""

from typing import Any, Dict, List, Tuple
import numpy as np
import pandas as pd


def generate_time_index(
    start_date: str = "2026-01-15",
    duration_days: int = 1,
    timestep_minutes: int = 15
) -> pd.DatetimeIndex:
    """Generate monotonically increasing 15-minute datetime timestamps."""
    freq = f"{timestep_minutes}min"
    periods = int((duration_days * 24 * 60) / timestep_minutes)
    return pd.date_range(start=start_date, periods=periods, freq=freq)


def generate_residential_profiles(
    config: Dict[str, Any],
    time_index: pd.DatetimeIndex
) -> Tuple[pd.DataFrame, Dict[str, Dict[str, Any]]]:
    """Generate 100 diverse residential load profiles.

    Pattern features:
    - Low nocturnal base load (0.1 - 0.4 kW)
    - Morning activity spike (06:30 - 09:00)
    - Midday standby/errand trough (10:00 - 16:00)
    - Evening cooking, lighting & cooling peak (18:00 - 22:30)
    - Nighttime taper
    """
    seed = config["simulation"].get("random_seed", 42)
    rng = np.random.default_rng(seed)

    n_households = config["neighbourhood"].get("households", 100)
    res_cfg = config.get("residential_loads", {})
    daily_kwh_min = res_cfg.get("base_daily_kwh_min", 4.0)
    daily_kwh_max = res_cfg.get("base_daily_kwh_max", 18.0)

    # Fractional hours of the day for each timestep
    hour_float = time_index.hour + time_index.minute / 60.0

    household_metadata = {}
    profiles = {"timestamp": time_index.strftime("%Y-%m-%d %H:%M")}

    for i in range(1, n_households + 1):
        hid = f"H{i:03d}"
        target_daily_kwh = rng.uniform(daily_kwh_min, daily_kwh_max)

        # Baseline diurnal shape parameters with household diversity
        morning_peak_hr = rng.normal(7.5, 0.4)
        evening_peak_hr = rng.normal(20.0, 0.5)
        morning_width = rng.uniform(1.2, 1.8)
        evening_width = rng.uniform(1.8, 2.4)

        base_offset = rng.uniform(0.12, 0.28)
        morning_pulse = 0.8 * np.exp(-0.5 * ((hour_float - morning_peak_hr) / morning_width) ** 2)
        evening_pulse = 1.4 * np.exp(-0.5 * ((hour_float - evening_peak_hr) / evening_width) ** 2)
        midday_activity = 0.3 * np.exp(-0.5 * ((hour_float - 13.0) / 3.0) ** 2)

        # Small stochastic noise to represent discrete appliance switching
        noise = rng.normal(0.0, 0.05, size=len(time_index))
        raw_shape = base_offset + morning_pulse + evening_pulse + midday_activity + noise
        raw_shape = np.clip(raw_shape, 0.05, None)

        # Normalize so integral equals target_daily_kwh
        timestep_hours = (time_index[1] - time_index[0]).total_seconds() / 3600.0 if len(time_index) > 1 else 0.25
        current_daily_kwh = np.sum(raw_shape) * timestep_hours
        scaled_profile = raw_shape * (target_daily_kwh / current_daily_kwh)

        profiles[hid] = np.round(scaled_profile, 4)
        household_metadata[hid] = {
            "household_id": hid,
            "target_daily_kwh": float(np.round(target_daily_kwh, 2)),
            "actual_daily_kwh": float(np.round(np.sum(scaled_profile) * timestep_hours, 2)),
            "peak_kw": float(np.round(np.max(scaled_profile), 3)),
            "min_kw": float(np.round(np.min(scaled_profile), 3)),
            "power_factor": float(res_cfg.get("power_factor", 0.95))
        }

    df_res = pd.DataFrame(profiles)
    return df_res, household_metadata


def generate_commercial_profiles(
    config: Dict[str, Any],
    time_index: pd.DatetimeIndex
) -> Tuple[pd.DataFrame, Dict[str, Dict[str, Any]]]:
    """Generate 5 commercial load profiles (shops, mini-market, offices).

    Features daytime active hours (08:30 - 19:00), prominent air conditioning
    and lighting, low standby overnight.
    """
    seed = config["simulation"].get("random_seed", 42) + 100
    rng = np.random.default_rng(seed)

    n_comm = config["neighbourhood"].get("commercial_consumers", 5)
    comm_cfg = config.get("commercial_loads", {})
    peak_min = comm_cfg.get("peak_kw_min", 8.0)
    peak_max = comm_cfg.get("peak_kw_max", 25.0)

    hour_float = time_index.hour + time_index.minute / 60.0
    profiles = {"timestamp": time_index.strftime("%Y-%m-%d %H:%M")}
    comm_metadata = {}

    for i in range(1, n_comm + 1):
        cid = f"COM{i:02d}"
        target_peak = rng.uniform(peak_min, peak_max)
        open_hr = rng.uniform(8.0, 9.0)
        close_hr = rng.uniform(18.5, 20.0)

        standby = rng.uniform(0.10, 0.15) * target_peak
        # Sigmoidal operating profile for business hours
        opening_ramp = 1.0 / (1.0 + np.exp(-(hour_float - open_hr) / 0.5))
        closing_ramp = 1.0 / (1.0 + np.exp((hour_float - close_hr) / 0.5))
        business_activity = opening_ramp * closing_ramp

        # Midday AC peak around 13:00 - 15:00
        cooling_peak = 0.3 * target_peak * np.exp(-0.5 * ((hour_float - 14.0) / 2.0) ** 2)
        noise = rng.normal(0.0, 0.03 * target_peak, size=len(time_index))

        kw_profile = standby + business_activity * (target_peak * 0.7) + cooling_peak + noise
        kw_profile = np.clip(kw_profile, standby * 0.8, target_peak)

        profiles[cid] = np.round(kw_profile, 4)
        comm_metadata[cid] = {
            "commercial_id": cid,
            "peak_kw": float(np.round(np.max(kw_profile), 3)),
            "min_kw": float(np.round(np.min(kw_profile), 3)),
            "power_factor": float(comm_cfg.get("power_factor", 0.92))
        }

    df_comm = pd.DataFrame(profiles)
    return df_comm, comm_metadata


def generate_critical_profile(
    config: Dict[str, Any],
    time_index: pd.DatetimeIndex
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Generate 1 critical infrastructure load profile (Primary Health Clinic).

    24/7 continuous baseline with daytime clinical hours elevation.
    Marked with priority=1 for downstream grid protection.
    """
    seed = config["simulation"].get("random_seed", 42) + 200
    rng = np.random.default_rng(seed)

    crit_cfg = config.get("critical_facility", {})
    fid = crit_cfg.get("facility_id", "CRIT_001")
    base_kw = crit_cfg.get("base_kw", 5.0)
    peak_kw = crit_cfg.get("peak_kw", 12.0)

    hour_float = time_index.hour + time_index.minute / 60.0
    daytime_bump = (peak_kw - base_kw) * np.exp(-0.5 * ((hour_float - 12.0) / 3.5) ** 2)
    noise = rng.normal(0.0, 0.15, size=len(time_index))

    load = np.clip(base_kw + daytime_bump + noise, base_kw * 0.85, peak_kw)

    df_crit = pd.DataFrame({
        "timestamp": time_index.strftime("%Y-%m-%d %H:%M"),
        fid: np.round(load, 4)
    })
    meta = {
        "facility_id": fid,
        "name": crit_cfg.get("name", "Primary Health Centre"),
        "priority": int(crit_cfg.get("priority", 1)),
        "base_kw": float(base_kw),
        "peak_kw": float(np.round(np.max(load), 3)),
        "power_factor": float(crit_cfg.get("power_factor", 0.96))
    }
    return df_crit, meta


def generate_flexible_load_profiles(
    config: Dict[str, Any],
    time_index: pd.DatetimeIndex
) -> Tuple[pd.DataFrame, Dict[str, Dict[str, Any]]]:
    """Generate baseline operating profiles for designated flexible loads.

    In Phase 1, flexible loads follow their deterministic baseline schedule
    (not yet shifted or optimized).
    """
    flex_list = config.get("flexible_loads", [])
    profiles = {"timestamp": time_index.strftime("%Y-%m-%d %H:%M")}
    metadata = {}

    hour_float = time_index.hour + time_index.minute / 60.0

    for item in flex_list:
        lid = item["load_id"]
        rated_kw = float(item["rated_kw"])
        start_hr = float(item["start_hour"])
        end_hr = float(item["end_hour"])

        # Operating when within scheduled hours
        active_mask = (hour_float >= start_hr) & (hour_float < end_hr)
        load_kw = np.where(active_mask, rated_kw, 0.0)

        profiles[lid] = np.round(load_kw, 4)
        metadata[lid] = {
            "load_id": lid,
            "name": item.get("name", lid),
            "rated_kw": rated_kw,
            "start_hour": start_hr,
            "end_hour": end_hr,
            "bus_name": item.get("bus_name", "Bus_Residential_1"),
            "flexible": True
        }

    df_flex = pd.DataFrame(profiles)
    return df_flex, metadata
