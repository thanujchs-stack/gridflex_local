"""Electric Vehicle (EV) baseline charging profile generator.

Generates uncontrolled home/commuter EV charging profiles based on realistic
arrival schedules, battery replenishment needs, and Level 2 AC charger ratings.
"""

from typing import Any, Dict, List, Tuple
import numpy as np
import pandas as pd


def generate_ev_profiles(
    config: Dict[str, Any],
    time_index: pd.DatetimeIndex
) -> Tuple[pd.DataFrame, Dict[str, Dict[str, Any]]]:
    """Generate ~20 uncontrolled EV charging load profiles.

    Phase 1 Rule: EV charging is strictly UNCONTROLLED baseline behavior.
    Vehicles arrive in the evening, immediately begin charging at rated wallbox power,
    and charge until required energy is replenished or departure occurs.
    """
    seed = config["simulation"].get("random_seed", 42) + 400
    rng = np.random.default_rng(seed)

    n_evs = config["neighbourhood"].get("ev_count", 20)
    ev_cfg = config.get("ev_charging", {})
    charger_kw = float(ev_cfg.get("charger_rating_kw", 7.4))
    min_energy = float(ev_cfg.get("min_daily_energy_kwh", 8.0))
    max_energy = float(ev_cfg.get("max_daily_energy_kwh", 22.0))
    arr_mean = float(ev_cfg.get("arrival_hour_mean", 19.0))
    arr_std = float(ev_cfg.get("arrival_hour_std", 1.5))
    pf = float(ev_cfg.get("power_factor", 0.98))

    hour_float = time_index.hour + time_index.minute / 60.0
    dt_hours = (time_index[1] - time_index[0]).total_seconds() / 3600.0 if len(time_index) > 1 else 0.25

    ev_profiles = {"timestamp": time_index.strftime("%Y-%m-%d %H:%M")}
    ev_metadata = {}

    for i in range(1, n_evs + 1):
        ev_id = f"EV_{i:03d}"
        req_energy = float(np.round(rng.uniform(min_energy, max_energy), 2))
        arrival_hr = float(np.round(np.clip(rng.normal(arr_mean, arr_std), 16.0, 22.5), 2))

        # Duration needed to deliver energy at full charger rate
        hours_needed = req_energy / charger_kw
        timesteps_needed = int(np.ceil(hours_needed / dt_hours))

        charging_kw = np.zeros(len(time_index), dtype=float)

        # Find first timestep at or after arrival_hr
        arr_indices = np.where(hour_float >= arrival_hr)[0]
        if len(arr_indices) > 0:
            start_idx = arr_indices[0]
            remaining_energy = req_energy

            for t_idx in range(start_idx, len(time_index)):
                if remaining_energy <= 1e-4:
                    break
                # Energy that would be delivered at full power in this timestep
                max_step_energy = charger_kw * dt_hours
                if remaining_energy >= max_step_energy:
                    charging_kw[t_idx] = charger_kw
                    remaining_energy -= max_step_energy
                else:
                    # Final fractional timestep
                    power = remaining_energy / dt_hours
                    charging_kw[t_idx] = float(np.round(power, 4))
                    remaining_energy = 0.0

        delivered_energy = float(np.round(np.sum(charging_kw) * dt_hours, 2))

        ev_profiles[ev_id] = np.round(charging_kw, 4)
        ev_metadata[ev_id] = {
            "ev_id": ev_id,
            "der_type": "EV",
            "charger_rating_kw": charger_kw,
            "arrival_hour": arrival_hr,
            "required_energy_kwh": req_energy,
            "delivered_energy_kwh": delivered_energy,
            "peak_kw": float(np.round(np.max(charging_kw), 3)),
            "power_factor": pf,
            "controlled": False
        }

    df_ev = pd.DataFrame(ev_profiles)
    return df_ev, ev_metadata
