"""Unit tests for profile generation modules."""

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
from src.profiles.solar_profiles import generate_solar_profiles, apply_cloud_event
from src.profiles.ev_profiles import generate_ev_profiles

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def config():
    config_file = PROJECT_ROOT / "config" / "neighbourhood_config.yaml"
    with open(config_file, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture
def time_index(config):
    sim_cfg = config["simulation"]
    return generate_time_index(
        start_date=sim_cfg.get("start_date", "2026-01-15"),
        duration_days=sim_cfg.get("duration_days", 1),
        timestep_minutes=sim_cfg.get("timestep_minutes", 15)
    )


def test_time_index_properties(time_index):
    assert len(time_index) == 96
    assert time_index.is_monotonic_increasing
    assert len(time_index) == len(set(time_index))


def test_residential_profiles(config, time_index):
    df_res, res_meta = generate_residential_profiles(config, time_index)
    # Check count of households
    assert len(res_meta) == 100
    assert len(df_res) == 96
    assert "timestamp" in df_res.columns

    # Verify no negative loads
    cols = [c for c in df_res.columns if c != "timestamp"]
    assert len(cols) == 100
    for col in cols:
        assert (df_res[col] >= 0.0).all(), f"Negative load found in {col}"


def test_commercial_profiles(config, time_index):
    df_comm, comm_meta = generate_commercial_profiles(config, time_index)
    assert len(comm_meta) == 5
    assert len(df_comm) == 96
    cols = [c for c in df_comm.columns if c != "timestamp"]
    assert len(cols) == 5
    for col in cols:
        assert (df_comm[col] >= 0.0).all(), f"Negative commercial load found in {col}"


def test_critical_facility_profile(config, time_index):
    df_crit, crit_meta = generate_critical_profile(config, time_index)
    assert crit_meta["facility_id"] == "CRIT_001"
    assert crit_meta["priority"] == 1
    assert len(df_crit) == 96
    assert (df_crit["CRIT_001"] >= 0.0).all()


def test_flexible_load_profiles(config, time_index):
    df_flex, flex_meta = generate_flexible_load_profiles(config, time_index)
    assert len(flex_meta) == 3
    assert len(df_flex) == 96
    for col in flex_meta:
        assert (df_flex[col] >= 0.0).all()


def test_solar_profiles_and_cloud_event(config, time_index):
    df_res, res_meta = generate_residential_profiles(config, time_index)
    hids = list(res_meta.keys())
    df_solar, pv_meta = generate_solar_profiles(config, time_index, hids)

    # 60% of 100 households = 60 PV systems
    assert len(pv_meta) == 60
    assert len(df_solar) == 96

    for der_id, meta in pv_meta.items():
        cap = meta["capacity_kw"]
        series = df_solar[der_id]
        # Check non-negative
        assert (series >= 0.0).all()
        # Check within capacity limit
        assert (series <= (cap * 1.001)).all()
        # Check night is zero (first timestep 00:00 and last timestep 23:45)
        assert series.iloc[0] == 0.0
        assert series.iloc[-1] == 0.0

    # Test cloud scenario transformation
    df_cloud = apply_cloud_event(df_solar, config)
    assert len(df_cloud) == 96
    # Cloud event between 15:00 and 16:00 should reduce PV generation
    ts = df_solar["timestamp"].str[-5:]
    mask_cloud = (ts >= "15:00") & (ts <= "16:00")
    for der_id in pv_meta:
        orig_pv = df_solar.loc[mask_cloud, der_id].sum()
        cloud_pv = df_cloud.loc[mask_cloud, der_id].sum()
        if orig_pv > 0.1:
            assert cloud_pv < orig_pv


def test_ev_profiles(config, time_index):
    df_ev, ev_meta = generate_ev_profiles(config, time_index)
    assert len(ev_meta) == 20
    assert len(df_ev) == 96
    for evid, meta in ev_meta.items():
        series = df_ev[evid]
        rating = meta["charger_rating_kw"]
        assert (series >= 0.0).all()
        assert (series <= (rating * 1.001)).all()
