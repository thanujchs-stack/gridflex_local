"""Unit tests for unit conversion and 15-minute energy-conserving resampling."""

import pytest
import pandas as pd
import numpy as np
from src.data.resampler import DataResampler


def test_unit_conversion_energy_to_average_power():
    """Verify conversion: energy_kwh / interval_hours = average_kw.

    For 30-minute interval, interval_hours = 0.5, so average_kw = energy_kwh * 2.0.
    """
    energy_kwh = 1.25
    interval_hours = 0.5
    average_kw = energy_kwh / interval_hours
    assert np.isclose(average_kw, 2.50)


def test_15min_resampling_energy_conservation():
    """Verify that resampling 30-minute power to 15-minute preserves exact energy."""
    resampler = DataResampler()
    dates = pd.date_range("2022-01-01", periods=4, freq="30min")
    # 4 half-hour power readings in kW
    df_30min = pd.DataFrame({
        "timestamp": dates,
        "load_kw": [2.0, 4.0, 1.0, 3.0],
        "household_id": ["H001"] * 4,
    })

    # Energy in 30-min data = sum(P_i * 0.5 h)
    energy_30min_kwh = (df_30min["load_kw"] * 0.5).sum()

    df_15min = resampler.resample_ausgrid_halfhourly_to_15min(
        df_30min, timestamp_col="timestamp", value_cols=["load_kw"], group_col="household_id"
    )

    assert len(df_15min) == 8  # 4 * 2 = 8 steps
    # Energy in 15-min data = sum(P_j * 0.25 h)
    energy_15min_kwh = (df_15min["load_kw"] * 0.25).sum()

    assert np.isclose(energy_30min_kwh, energy_15min_kwh), "15-minute resampling must conserve total energy"


def test_solar_15min_resampling_and_night_clamping():
    """Verify solar 15-minute interpolation and strict night clamping."""
    resampler = DataResampler()
    hourly_dates = pd.date_range("2022-01-01 04:00", periods=6, freq="1h")
    # Hourly GHI: 0 at 4:00, 0 at 5:00, 50 at 6:00, 200 at 7:00, 400 at 8:00, 600 at 9:00
    df_solar = pd.DataFrame({
        "timestamp": hourly_dates,
        "GHI": [0.0, 0.0, 50.0, 200.0, 400.0, 600.0],
        "DNI": [0.0, 0.0, 20.0, 150.0, 350.0, 500.0],
        "DHI": [0.0, 0.0, 30.0, 50.0, 50.0, 100.0],
        "Temperature": [15.0, 15.2, 16.0, 18.0, 20.0, 22.0],
    })

    df_15min = resampler.resample_solar_hourly_to_15min(
        df_solar, timestamp_col="timestamp", irradiance_cols=["GHI", "DNI", "DHI"], temp_col="Temperature"
    )

    assert len(df_15min) == 21  # 5 hours * 4 intervals + 1 endpoint = 21 points
    # Verify non-negative
    assert (df_15min["GHI"] >= 0.0).all()
    assert (df_15min["DNI"] >= 0.0).all()
    assert (df_15min["DHI"] >= 0.0).all()
    # At 04:30 (night), GHI must be 0.0
    val_night = df_15min.loc[df_15min["timestamp"] == "2022-01-01 04:30:00", "GHI"].values[0]
    assert np.isclose(val_night, 0.0)
