"""Script to generate, validate, and persist all neighbourhood profiles.

Generates:
- 100 residential load profiles
- 5 commercial consumer load profiles
- 1 critical facility load profile (Primary Health Centre)
- 20 EV charging load profiles (uncontrolled baseline)
- 3 flexible load profiles (baseline schedule)
- ~60 rooftop solar PV profiles (baseline clear-sky diurnal shape)
- Solar intermittency scenario profiles (PV_CLOUD_EVENT_V1)
- Community BESS baseline operation profile (idle)
"""

import os
from pathlib import Path
import sys
import yaml

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.profiles.load_profiles import (
    generate_time_index,
    generate_residential_profiles,
    generate_commercial_profiles,
    generate_critical_profile,
    generate_flexible_load_profiles
)
from src.profiles.solar_profiles import generate_solar_profiles, apply_cloud_event
from src.profiles.ev_profiles import generate_ev_profiles
from src.der.registry import CommunityBatteryModel
from src.utils.validation import (
    validate_load_profiles,
    validate_solar_profiles,
    validate_ev_profiles,
    validate_battery_soc
)


def load_config(config_path: Path) -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main():
    config_file = PROJECT_ROOT / "config" / "neighbourhood_config.yaml"
    config = load_config(config_file)

    sim_cfg = config["simulation"]
    time_index = generate_time_index(
        start_date=sim_cfg.get("start_date", "2026-01-15"),
        duration_days=sim_cfg.get("duration_days", 1),
        timestep_minutes=sim_cfg.get("timestep_minutes", 15)
    )

    print(f"Generating profiles for horizon: {len(time_index)} timesteps (15-min intervals)...")

    # 1. Residential Loads
    df_res, res_meta = generate_residential_profiles(config, time_index)
    validate_load_profiles(df_res)
    print(f"  [PASS] Residential profiles: {len(res_meta)} households generated and validated.")

    # 2. Commercial Loads
    df_comm, comm_meta = generate_commercial_profiles(config, time_index)
    validate_load_profiles(df_comm)
    print(f"  [PASS] Commercial profiles: {len(comm_meta)} consumers generated and validated.")

    # 3. Critical Facility Load
    df_crit, crit_meta = generate_critical_profile(config, time_index)
    validate_load_profiles(df_crit)
    print(f"  [PASS] Critical facility profile: {crit_meta['facility_id']} ({crit_meta['name']}) validated.")

    # 4. Flexible Loads
    df_flex, flex_meta = generate_flexible_load_profiles(config, time_index)
    validate_load_profiles(df_flex)
    print(f"  [PASS] Flexible loads: {len(flex_meta)} baseline schedules generated and validated.")

    # 5. Solar PV Profiles
    hids = list(res_meta.keys())
    df_solar_base, pv_meta = generate_solar_profiles(config, time_index, hids)
    pv_caps = {der_id: m["capacity_kw"] for der_id, m in pv_meta.items()}
    validate_solar_profiles(df_solar_base, pv_caps)
    print(f"  [PASS] Solar PV profiles (baseline): {len(pv_meta)} systems generated and validated.")

    # 6. Solar Cloud Intermittency Scenario
    df_solar_cloud = apply_cloud_event(df_solar_base, config)
    validate_solar_profiles(df_solar_cloud, pv_caps)
    print(f"  [PASS] Solar PV profiles (cloud scenario PV_CLOUD_EVENT_V1) generated and validated.")

    # 7. EV Profiles
    df_ev, ev_meta = generate_ev_profiles(config, time_index)
    ev_ratings = {evid: m["charger_rating_kw"] for evid, m in ev_meta.items()}
    validate_ev_profiles(df_ev, ev_ratings)
    print(f"  [PASS] EV charging profiles: {len(ev_meta)} uncontrolled sessions generated and validated.")

    # 8. Community Battery Profile
    bess_model = CommunityBatteryModel(config)
    df_bess = bess_model.simulate_baseline_timeseries(time_index)
    validate_battery_soc(df_bess["soc"], bess_model.min_soc, bess_model.max_soc)
    print(f"  [PASS] Community BESS profile ({bess_model.der_id}): baseline idle simulated and validated.")

    # Output directory
    out_dir = PROJECT_ROOT / "data" / "generated"
    out_dir.mkdir(parents=True, exist_ok=True)

    df_res.to_csv(out_dir / "residential_profiles.csv", index=False)
    df_comm.to_csv(out_dir / "commercial_profiles.csv", index=False)
    df_crit.to_csv(out_dir / "critical_profile.csv", index=False)
    df_flex.to_csv(out_dir / "flexible_load_profiles.csv", index=False)
    df_solar_base.to_csv(out_dir / "solar_profiles_baseline.csv", index=False)
    df_solar_cloud.to_csv(out_dir / "solar_profiles_cloud.csv", index=False)
    df_ev.to_csv(out_dir / "ev_profiles.csv", index=False)
    df_bess.to_csv(out_dir / "battery_baseline.csv", index=False)

    print(f"\nAll profile datasets successfully saved to {out_dir}")
    return {
        "time_index": time_index,
        "df_res": df_res,
        "res_meta": res_meta,
        "df_comm": df_comm,
        "comm_meta": comm_meta,
        "df_crit": df_crit,
        "crit_meta": crit_meta,
        "df_flex": df_flex,
        "flex_meta": flex_meta,
        "df_solar_base": df_solar_base,
        "df_solar_cloud": df_solar_cloud,
        "pv_meta": pv_meta,
        "df_ev": df_ev,
        "ev_meta": ev_meta,
        "df_bess": df_bess,
        "bess_model": bess_model
    }


if __name__ == "__main__":
    main()
