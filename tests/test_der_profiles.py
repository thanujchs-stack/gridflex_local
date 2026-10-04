"""Unit tests for DER Digital Profiles and Flexibility Passport."""

from pathlib import Path
import pytest
import yaml
import pandas as pd

from src.der.profiles import create_der_passports
from src.der.constraints import DERConstraintManager

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def phase2_setup():
    config_file = PROJECT_ROOT / "config" / "neighbourhood_config.yaml"
    with open(config_file, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    reg_file = PROJECT_ROOT / "outputs" / "csv" / "der_registry.csv"
    ts_file = PROJECT_ROOT / "outputs" / "csv" / "der_timeseries.csv"

    df_reg = pd.read_csv(reg_file)
    df_ts = pd.read_csv(ts_file)

    constraint_mgr = DERConstraintManager(config, seed=42)
    der_ids = df_reg["der_id"].tolist()
    der_types = dict(zip(df_reg["der_id"], df_reg["der_type"]))
    part_map = constraint_mgr.assign_participation(der_ids, der_types, participation_rate=0.70)

    return config, df_reg, df_ts, part_map


def test_passport_row_count(phase2_setup):
    config, df_reg, df_ts, part_map = phase2_setup
    df_passport = create_der_passports(config, df_reg, df_ts, part_map)

    # Must match exactly 84 DER assets from Phase 1
    assert len(df_passport) == 84
    assert len(df_passport) == len(df_reg)


def test_passport_required_fields(phase2_setup):
    config, df_reg, df_ts, part_map = phase2_setup
    df_passport = create_der_passports(config, df_reg, df_ts, part_map)

    required_cols = [
        "der_id",
        "der_type",
        "owner_id",
        "rated_power_kw",
        "energy_capacity_kwh",
        "current_power_kw",
        "current_soc_pct",
        "min_soc_pct",
        "max_soc_pct",
        "availability_start",
        "availability_end",
        "response_time_minutes",
        "baseline_power_kw",
        "min_power_kw",
        "max_power_kw",
        "flexibility_enabled",
        "owner_constraint",
        "reserve_requirement",
        "control_mode"
    ]
    for col in required_cols:
        assert col in df_passport.columns, f"Missing passport column: {col}"


def test_passport_der_types(phase2_setup):
    config, df_reg, df_ts, part_map = phase2_setup
    df_passport = create_der_passports(config, df_reg, df_ts, part_map)

    type_counts = df_passport["der_type"].value_counts().to_dict()
    assert type_counts["PV"] == 60
    assert type_counts["BESS"] == 1
    assert type_counts["EV"] == 20
    assert type_counts["FLEXIBLE_LOAD"] == 3


def test_battery_passport_values(phase2_setup):
    config, df_reg, df_ts, part_map = phase2_setup
    df_passport = create_der_passports(config, df_reg, df_ts, part_map)

    bess_row = df_passport[df_passport["der_type"] == "BESS"].iloc[0]
    assert bess_row["energy_capacity_kwh"] == 100.0
    assert bess_row["rated_power_kw"] == 25.0
    assert bess_row["min_soc_pct"] == 20.0
    assert bess_row["max_soc_pct"] == 90.0
    assert "reserve" in bess_row["reserve_requirement"].lower()
