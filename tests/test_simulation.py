"""Unit tests for pandapower AC power flow simulation."""

from pathlib import Path
import pytest
import yaml

from src.profiles.load_profiles import (
    generate_time_index,
    generate_residential_profiles,
    generate_commercial_profiles,
    generate_critical_profile,
    generate_flexible_load_profiles
)
from src.profiles.solar_profiles import generate_solar_profiles
from src.profiles.ev_profiles import generate_ev_profiles
from src.der.registry import CommunityBatteryModel
from src.network.feeder import build_feeder_topology
from src.simulation.run_simulation import run_feeder_timeseries_simulation

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def simulation_run():
    config_file = PROJECT_ROOT / "config" / "neighbourhood_config.yaml"
    with open(config_file, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    time_index = generate_time_index(start_date="2026-01-15", duration_days=1, timestep_minutes=15)
    df_res, res_meta = generate_residential_profiles(config, time_index)
    df_comm, comm_meta = generate_commercial_profiles(config, time_index)
    df_crit, crit_meta = generate_critical_profile(config, time_index)
    df_flex, flex_meta = generate_flexible_load_profiles(config, time_index)
    hids = list(res_meta.keys())
    df_solar, pv_meta = generate_solar_profiles(config, time_index, hids)
    df_ev, ev_meta = generate_ev_profiles(config, time_index)
    bess = CommunityBatteryModel(config)
    df_bess = bess.simulate_baseline_timeseries(time_index)

    net, mappings = build_feeder_topology(
        config=config,
        household_ids=hids,
        pv_metadata=pv_meta,
        comm_ids=list(comm_meta.keys()),
        crit_id=crit_meta["facility_id"],
        ev_ids=list(ev_meta.keys()),
        flex_ids=list(flex_meta.keys())
    )

    df_ts, df_bus, df_line, df_trafo, metrics = run_feeder_timeseries_simulation(
        net=net,
        mappings=mappings,
        config=config,
        df_res=df_res,
        df_comm=df_comm,
        df_crit=df_crit,
        df_ev=df_ev,
        df_flex=df_flex,
        df_solar=df_solar,
        df_bess=df_bess,
        scenario_name="TEST_BASELINE"
    )
    return df_ts, df_bus, df_line, df_trafo, metrics


def test_power_flow_converges_all_timesteps(simulation_run):
    df_ts, df_bus, df_line, df_trafo, metrics = simulation_run
    assert metrics["power_flow_converged"] is True
    assert metrics["timesteps"] == 96
    assert len(df_ts) == 96


def test_simulation_results_exist_and_sane(simulation_run):
    df_ts, df_bus, df_line, df_trafo, metrics = simulation_run

    assert "total_load_kw" in df_ts.columns
    assert "pv_generation_kw" in df_ts.columns
    assert "grid_import_kw" in df_ts.columns
    assert "transformer_loading_pct" in df_ts.columns
    assert "min_bus_voltage_pu" in df_ts.columns

    # Voltages must be in physically reasonable distribution range
    assert (df_ts["min_bus_voltage_pu"] > 0.80).all()
    assert (df_ts["max_bus_voltage_pu"] < 1.15).all()

    # Transformer loading must be non-negative
    assert (df_ts["transformer_loading_pct"] >= 0.0).all()


def test_detailed_results_counts(simulation_run):
    df_ts, df_bus, df_line, df_trafo, metrics = simulation_run
    # 9 buses * 96 timesteps = 864 rows
    assert len(df_bus) == 9 * 96
    # 7 lines * 96 timesteps = 672 rows
    assert len(df_line) == 7 * 96
    # 1 transformer * 96 timesteps = 96 rows
    assert len(df_trafo) == 96
