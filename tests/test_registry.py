"""Unit tests for DER Registry and asset modeling."""

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
from src.der.registry import build_der_registry, DERType

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def registry():
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

    household_bus_map = {hid: "Bus_Residential_1" for hid in hids}
    reg = build_der_registry(
        config=config,
        pv_metadata=pv_meta,
        ev_metadata=ev_meta,
        flex_metadata=flex_meta,
        household_bus_mapping=household_bus_map
    )
    return reg


def test_der_ids_are_unique(registry):
    assert registry.validate_unique_ids()


def test_der_types_valid(registry):
    valid_types = {DERType.PV, DERType.BESS, DERType.EV, DERType.FLEXIBLE_LOAD}
    for asset in registry.list_all():
        assert asset.der_type in valid_types


def test_expected_der_counts(registry):
    pv_assets = registry.filter_by_type(DERType.PV)
    bess_assets = registry.filter_by_type(DERType.BESS)
    ev_assets = registry.filter_by_type(DERType.EV)
    flex_assets = registry.filter_by_type(DERType.FLEXIBLE_LOAD)

    assert len(pv_assets) == 60
    assert len(bess_assets) == 1
    assert len(ev_assets) == 20
    assert len(flex_assets) == 3
    assert len(registry.list_all()) == (60 + 1 + 20 + 3)


def test_registry_dataframe_export(registry):
    df = registry.to_dataframe()
    assert len(df) == 84
    assert "der_id" in df.columns
    assert "der_type" in df.columns
    assert "bus_name" in df.columns
    assert "rated_capacity_kw" in df.columns
