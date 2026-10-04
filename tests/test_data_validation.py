"""Unit tests for dataset physical validation, anomaly detection, and quality gating."""

import os
import json
import pytest
import pandas as pd
import numpy as np
from src.data.validator import DataValidator
from src.data.cleaner import DataCleaner


def test_physical_validation_bounds():
    """Verify validator flags negative load or out-of-bounds solar values."""
    validator = DataValidator(output_dir="outputs/data_quality")

    # Synthetic invalid load dataframe
    dates = pd.date_range("2022-01-01", periods=10, freq="15min")
    df_invalid_load = pd.DataFrame({
        "timestamp": dates,
        "load_kw": [1.0, 2.0, -0.5, 1.2, 0.8, 1.5, 2.2, 1.9, 0.4, 0.5],
    })

    res = validator.validate_processed_timeseries(
        df_invalid_load, "Test Invalid Load", "load_kw", expected_resolution_min=15, min_allowed=0.0
    )
    assert res["status"] == "FAIL"
    assert res["negative_values"] == 1


def test_missing_and_duplicate_detection():
    """Verify validator detects missing values and duplicate timestamps."""
    validator = DataValidator(output_dir="outputs/data_quality")
    dates = pd.to_datetime(["2022-01-01 00:00", "2022-01-01 00:00", "2022-01-01 00:30"])
    df_test = pd.DataFrame({
        "timestamp": dates,
        "load_kw": [1.0, np.nan, 2.0],
    })

    res = validator.validate_processed_timeseries(df_test, "Test Dups & NaN", "load_kw")
    assert res["duplicate_count"] == 1
    assert res["missing_count"] == 1
    assert res["status"] in ["FAIL", "WARNING"]


def test_cleaner_deduplication_and_clamping():
    """Verify cleaner deduplicates and clamps physically invalid negative values to 0.0."""
    cleaner = DataCleaner(max_interpolation_gap=2)
    dates = pd.to_datetime(["2022-01-01 00:00", "2022-01-01 00:00", "2022-01-01 00:15"])
    df = pd.DataFrame({
        "timestamp": dates,
        "load_kw": [1.0, 1.5, -0.2],
    })

    cleaned, stats = cleaner.clean_timeseries(df, value_cols=["load_kw"], clamp_min_zero=True)
    assert len(cleaned) == 2  # Duplicate removed
    assert stats["duplicates_dropped"] == 1
    assert (cleaned["load_kw"] >= 0.0).all()  # Negative clamped


def test_quality_reports_exist_and_pass():
    """Verify output data quality report exists and all processed datasets pass."""
    csv_path = "outputs/data_quality/dataset_quality_report.csv"
    json_path = "outputs/data_quality/dataset_quality_report.json"

    assert os.path.exists(csv_path), "dataset_quality_report.csv must exist"
    assert os.path.exists(json_path), "dataset_quality_report.json must exist"

    df_report = pd.read_csv(csv_path)
    assert len(df_report) > 0

    # Ensure all processed datasets have status PASS
    processed_reports = df_report[df_report["dataset"].str.contains("15-min")]
    assert len(processed_reports) >= 4
    for _, row in processed_reports.iterrows():
        assert row["status"] == "PASS", f"Dataset {row['dataset']} did not PASS quality gate"
        assert row["negative_values"] == 0
        assert row["missing_percentage"] == 0.0
