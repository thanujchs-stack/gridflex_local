"""Unit tests for the abstracted dataset loader interface and Phase 1 compatibility."""

import pytest
import pandas as pd
import numpy as np
from src.data.load_dataset import load_forecasting_dataset


def test_load_real_public_dataset():
    """Verify loading real/public dataset via load_forecasting_dataset."""
    data = load_forecasting_dataset(mode="REAL_PUBLIC", include_household_level=False)

    assert data["mode"] == "REAL_PUBLIC"
    assert data["resolution_minutes"] == 15
    assert len(data["timestamps"]) > 0
    assert len(data["neighbourhood_load_kw"]) == len(data["timestamps"])
    assert len(data["neighbourhood_pv_kw"]) == len(data["timestamps"])
    assert len(data["solar_irradiance"]) == len(data["timestamps"])

    # Physical checks
    assert (data["neighbourhood_load_kw"] >= 0.0).all()
    assert (data["neighbourhood_pv_kw"] >= 0.0).all()
    assert "ghi_wm2" in data["solar_irradiance"].columns

    # Metadata checks
    assert "load_source" in data["metadata"]
    assert "solar_source" in data["metadata"]
    assert "limitations" in data["metadata"]


def test_load_synthetic_phase1_dataset():
    """Verify loading Phase 1 synthetic dataset maintains identical contract."""
    data = load_forecasting_dataset(mode="SYNTHETIC_PHASE1")

    assert data["mode"] == "SYNTHETIC_PHASE1"
    assert data["resolution_minutes"] == 15
    assert len(data["timestamps"]) == 96
    assert len(data["neighbourhood_load_kw"]) == 96
    assert len(data["neighbourhood_pv_kw"]) == 96
    assert len(data["solar_irradiance"]) == 96

    assert (data["neighbourhood_load_kw"] >= 0.0).all()
    assert (data["neighbourhood_pv_kw"] >= 0.0).all()


def test_invalid_mode_raises():
    """Verify invalid mode raises ValueError."""
    with pytest.raises(ValueError):
        load_forecasting_dataset(mode="INVALID_MODE")


def test_timestamp_filtering():
    """Verify start_time and end_time filtering works properly."""
    data = load_forecasting_dataset(
        mode="REAL_PUBLIC",
        start_time="2012-01-01 00:00:00",
        end_time="2012-01-01 23:45:00",
    )
    assert len(data["timestamps"]) == 96
    assert str(data["timestamps"].iloc[0]) == "2012-01-01 00:00:00"
    assert str(data["timestamps"].iloc[-1]) == "2012-01-01 23:45:00"
