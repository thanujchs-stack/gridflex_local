"""Unit tests for validation functions and physical constraints."""

from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from src.utils.validation import (
    validate_timestamps,
    validate_no_nan_or_inf,
    validate_load_profiles,
    validate_solar_profiles,
    validate_battery_soc,
    validate_power_balance
)
from src.der.registry import CommunityBatteryModel


def test_invalid_timestamps_detection():
    # Duplicate timestamp
    df_dup = pd.DataFrame({
        "timestamp": ["2026-01-15 00:00", "2026-01-15 00:00", "2026-01-15 00:30"],
        "load": [1.0, 1.2, 1.1]
    })
    with pytest.raises(ValueError, match="Duplicate timestamps"):
        validate_timestamps(df_dup)

    # Missing interval (jump from 00:00 to 01:00 with 15-min expected)
    df_gap = pd.DataFrame({
        "timestamp": ["2026-01-15 00:00", "2026-01-15 01:00"],
        "load": [1.0, 1.2]
    })
    with pytest.raises(ValueError, match="Missing or irregular timestep"):
        validate_timestamps(df_gap, expected_step_minutes=15)


def test_nan_and_inf_detection():
    df_nan = pd.DataFrame({"timestamp": ["2026-01-15 00:00"], "val": [np.nan]})
    with pytest.raises(ValueError, match="contains NaN values"):
        validate_no_nan_or_inf(df_nan)

    df_inf = pd.DataFrame({"timestamp": ["2026-01-15 00:00"], "val": [np.inf]})
    with pytest.raises(ValueError, match="contains infinite values"):
        validate_no_nan_or_inf(df_inf)


def test_negative_load_detection():
    df_neg = pd.DataFrame({
        "timestamp": ["2026-01-15 00:00", "2026-01-15 00:15"],
        "H001": [1.2, -0.5]
    })
    with pytest.raises(ValueError, match="negative values"):
        validate_load_profiles(df_neg)


def test_solar_over_capacity_detection():
    df_pv = pd.DataFrame({
        "timestamp": ["2026-01-15 12:00", "2026-01-15 12:15"],
        "PV_001": [3.0, 6.5]
    })
    with pytest.raises(ValueError, match="exceeds rated capacity"):
        validate_solar_profiles(df_pv, capacities={"PV_001": 5.0})


def test_battery_soc_boundaries():
    # Valid SOC within [0.20, 0.90]
    valid_soc = pd.Series([0.5, 0.6, 0.4, 0.25, 0.85])
    validate_battery_soc(valid_soc, min_soc=0.20, max_soc=0.90)

    # Violate min SOC
    low_soc = pd.Series([0.5, 0.15])
    with pytest.raises(ValueError, match="violated minimum boundary"):
        validate_battery_soc(low_soc, min_soc=0.20, max_soc=0.90)

    # Violate max SOC
    high_soc = pd.Series([0.5, 0.95])
    with pytest.raises(ValueError, match="violated maximum boundary"):
        validate_battery_soc(high_soc, min_soc=0.20, max_soc=0.90)


def test_battery_model_clamping():
    config = {
        "battery": {
            "energy_capacity_kwh": 100.0,
            "max_charge_kw": 25.0,
            "max_discharge_kw": 25.0,
            "initial_soc": 0.22,
            "min_soc": 0.20,
            "max_soc": 0.90,
            "charge_efficiency": 1.0,
            "discharge_efficiency": 1.0
        }
    }
    bess = CommunityBatteryModel(config)
    time_index = pd.date_range("2026-01-15", periods=10, freq="15min")
    # Demand huge discharge power (100 kW for each step)
    huge_discharge = np.full(10, 100.0)
    df = bess.simulate_baseline_timeseries(time_index, scheduled_power_kw=huge_discharge)

    # SOC must never fall below min_soc (0.20)
    assert (df["soc"] >= 0.20).all()


def test_power_balance_calculation():
    # Perfect balance case: supply = 100, demand = 95, losses = 5
    p_grid = pd.Series([100.0, 100.0])
    p_pv = pd.Series([0.0, 0.0])
    p_bess_dis = pd.Series([0.0, 0.0])
    p_load = pd.Series([95.0, 95.0])
    p_bess_ch = pd.Series([0.0, 0.0])
    p_loss = pd.Series([5.0, 5.0])

    max_err, mean_err, failed, _ = validate_power_balance(
        p_grid, p_pv, p_bess_dis, p_load, p_bess_ch, p_loss, tolerance_kw=1.0
    )
    assert max_err < 1e-4
    assert failed == 0

    # Imbalanced case: inject 10 kW mismatch
    p_loss_bad = pd.Series([15.0, 15.0])
    max_err_b, mean_err_b, failed_b, _ = validate_power_balance(
        p_grid, p_pv, p_bess_dis, p_load, p_bess_ch, p_loss_bad, tolerance_kw=1.0
    )
    assert abs(max_err_b - 10.0) < 1e-4
    assert failed_b == 2
