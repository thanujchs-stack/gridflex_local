"""Unit tests for deterministic household selection and neighbourhood aggregation."""

import os
import pytest
import pandas as pd
import numpy as np
from src.data.dataset_manager import DatasetManager


def test_deterministic_household_sampling():
    """Verify that household selection is 100% reproducible with random_seed=42."""
    manager1 = DatasetManager(random_seed=42)
    h1 = manager1.select_households(num_households=100, random_seed=42)

    manager2 = DatasetManager(random_seed=42)
    h2 = manager2.select_households(num_households=100, random_seed=42)

    pd.testing.assert_frame_equal(h1, h2)
    assert len(h1) == 100
    assert h1["household_id"].nunique() == 100
    assert h1["customer_id"].nunique() == 100


def test_selected_households_file_exists():
    """Verify data/processed/selected_households.csv has expected columns and 100 rows."""
    path = "data/processed/selected_households.csv"
    assert os.path.exists(path), f"File {path} must exist"
    df = pd.read_csv(path)
    assert len(df) == 100
    expected_cols = ["household_id", "customer_id", "generator_capacity_kw", "postcode"]
    for c in expected_cols:
        assert c in df.columns


def test_neighbourhood_aggregation_sums():
    """Verify aggregated neighbourhood load and PV match the sum of individual households."""
    hh_load_path = "data/processed/ausgrid_load_15min.csv"
    nb_load_path = "data/processed/neighbourhood_load_15min.csv"
    hh_pv_path = "data/processed/ausgrid_pv_15min.csv"
    nb_pv_path = "data/processed/neighbourhood_pv_15min.csv"

    for p in [hh_load_path, nb_load_path, hh_pv_path, nb_pv_path]:
        assert os.path.exists(p), f"Missing file: {p}"

    # Sample test window of 96 timesteps (1 day)
    nb_load = pd.read_csv(nb_load_path).head(96)
    nb_pv = pd.read_csv(nb_pv_path).head(96)

    hh_load = pd.read_csv(hh_load_path)
    hh_pv = pd.read_csv(hh_pv_path)

    sample_ts = nb_load["timestamp"].iloc[10]
    expected_load_sum = hh_load[hh_load["timestamp"] == sample_ts]["load_kw"].sum()
    actual_load_sum = nb_load[nb_load["timestamp"] == sample_ts]["total_load_kw"].values[0]
    assert np.isclose(expected_load_sum, actual_load_sum, atol=1e-3)

    sample_pv_ts = nb_pv["timestamp"].iloc[48]
    expected_pv_sum = hh_pv[hh_pv["timestamp"] == sample_pv_ts]["pv_kw"].sum()
    actual_pv_sum = nb_pv[nb_pv["timestamp"] == sample_pv_ts]["total_pv_kw"].values[0]
    assert np.isclose(expected_pv_sum, actual_pv_sum, atol=1e-3)
