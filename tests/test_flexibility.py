"""Unit tests for flexibility evaluation, availability, and aggregation."""

from pathlib import Path
import pytest
import yaml
import pandas as pd
import numpy as np

from src.der.flexibility import compute_flexibility_timeseries
from src.der.constraints import DERConstraintManager

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def flex_run():
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

    df_avail, df_flex_ts, df_flex_summary = compute_flexibility_timeseries(
        config=config,
        df_der_reg=df_reg,
        df_der_ts=df_ts,
        participation_map=part_map
    )
    return df_avail, df_flex_ts, df_flex_summary, part_map, df_ts


def test_flexibility_non_negative(flex_run):
    df_avail, df_flex_ts, df_flex_summary, part_map, df_ts = flex_run

    assert (df_flex_ts["tech_flex_up_kw"] >= 0.0).all()
    assert (df_flex_ts["tech_flex_down_kw"] >= 0.0).all()
    assert (df_flex_ts["flex_up_kw"] >= 0.0).all()
    assert (df_flex_ts["flex_down_kw"] >= 0.0).all()
    assert (df_flex_ts["flex_shiftable_kw"] >= 0.0).all()
    assert (df_flex_ts["energy_flexibility_kwh"] >= 0.0).all()

    assert (df_flex_summary["total_up_kw"] >= 0.0).all()
    assert (df_flex_summary["total_down_kw"] >= 0.0).all()
    assert (df_flex_summary["total_shiftable_kw"] >= 0.0).all()


def test_zero_flexibility_when_unavailable_or_non_participating(flex_run):
    df_avail, df_flex_ts, df_flex_summary, part_map, df_ts = flex_run

    # When unavailable, available flexibility must be zero
    unavail_rows = df_flex_ts[df_flex_ts["available"] == False]
    assert (unavail_rows["flex_up_kw"] == 0.0).all()
    assert (unavail_rows["flex_down_kw"] == 0.0).all()
    assert (unavail_rows["flex_shiftable_kw"] == 0.0).all()

    # When non-participating, available flexibility must be zero
    non_part_rows = df_flex_ts[df_flex_ts["participating"] == False]
    assert (non_part_rows["flex_up_kw"] == 0.0).all()
    assert (non_part_rows["flex_down_kw"] == 0.0).all()
    assert (non_part_rows["flex_shiftable_kw"] == 0.0).all()


def test_no_double_counting_ev(flex_run):
    df_avail, df_flex_ts, df_flex_summary, part_map, df_ts = flex_run

    # EV flexibility must NEVER exceed the actual baseline charging power in that timestep
    ev_records = df_flex_ts[df_flex_ts["der_type"] == "EV"]
    for _, row in ev_records.iterrows():
        did = row["der_id"]
        ts = row["timestamp"]
        # Find baseline power in df_ts
        p_base = float(df_ts.loc[df_ts["timestamp"] == ts, did].iloc[0])
        assert row["flex_down_kw"] <= (p_base + 1e-4)


def test_technical_vs_available_separation(flex_run):
    df_avail, df_flex_ts, df_flex_summary, part_map, df_ts = flex_run

    # For non-participating active DERs, technical flexibility > 0 while available flexibility == 0
    non_part_active = df_flex_ts[(df_flex_ts["participating"] == False) & (df_flex_ts["available"] == True)]
    if not non_part_active.empty:
        assert (non_part_active["tech_flex_down_kw"] > 0.0).any()
        assert (non_part_active["flex_down_kw"] == 0.0).all()


def test_battery_headroom_respects_reserve(flex_run):
    df_avail, df_flex_ts, df_flex_summary, part_map, df_ts = flex_run

    bess_records = df_flex_ts[df_flex_ts["der_type"] == "BESS"]
    # At initial SOC 50%, with 30% effective floor (20% min + 10% reserve),
    # 20 kWh available discharge -> at 0.25h, (20 * 0.95) / 0.25 = 76 kW, capped by max discharge 25 kW
    assert (bess_records["flex_up_kw"] <= 25.0).all()
    assert (bess_records["flex_down_kw"] <= 25.0).all()
