"""Integration tests for Phase 2 pipeline execution and physical consistency."""

from pathlib import Path
import subprocess
import pytest
import pandas as pd
import numpy as np
import yaml

from src.der.constraints import DERConstraintManager
from src.der.flexibility import compute_flexibility_timeseries

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_phase1_baseline_unchanged_after_phase2():
    """Verify that Phase 2 does NOT alter the Phase 1 power flow results."""
    feeder_csv = PROJECT_ROOT / "outputs" / "csv" / "phase1_timeseries.csv"
    assert feeder_csv.exists()
    df_before = pd.read_csv(feeder_csv)

    # Run Phase 2 script
    py_exec = PROJECT_ROOT.parent / ".venv" / "Scripts" / "python.exe"
    script = PROJECT_ROOT / "scripts" / "run_phase2.py"
    subprocess.run([str(py_exec), str(script)], check=True, capture_output=True)

    df_after = pd.read_csv(feeder_csv)

    # Must be bit-for-bit identical
    diff = (df_before.select_dtypes(include=[np.number]) - df_after.select_dtypes(include=[np.number])).abs().max().max()
    assert diff < 1e-6, f"Phase 2 modified Phase 1 baseline electrical results! Max diff: {diff}"


def test_phase2_output_files_exist():
    csv_dir = PROJECT_ROOT / "outputs" / "csv"
    expected_files = [
        "der_flexibility_passport.csv",
        "der_availability.csv",
        "flexibility_timeseries.csv",
        "neighbourhood_flexibility_summary.csv"
    ]
    for fn in expected_files:
        fpath = csv_dir / fn
        assert fpath.exists(), f"Missing output CSV: {fn}"
        assert fpath.stat().st_size > 0, f"Output file is empty: {fn}"


def test_participation_sensitivity_monotonicity():
    """Verify that higher participation yields strictly greater or equal available flexibility."""
    config_file = PROJECT_ROOT / "config" / "neighbourhood_config.yaml"
    with open(config_file, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    df_reg = pd.read_csv(PROJECT_ROOT / "outputs" / "csv" / "der_registry.csv")
    df_ts = pd.read_csv(PROJECT_ROOT / "outputs" / "csv" / "der_timeseries.csv")

    constraint_mgr = DERConstraintManager(config, seed=42)
    der_ids = df_reg["der_id"].tolist()
    der_types = dict(zip(df_reg["der_id"], df_reg["der_type"]))

    part_100 = constraint_mgr.assign_participation(der_ids, der_types, 1.00)
    part_70 = constraint_mgr.assign_participation(der_ids, der_types, 0.70)
    part_40 = constraint_mgr.assign_participation(der_ids, der_types, 0.40)

    _, _, summary_100 = compute_flexibility_timeseries(config, df_reg, df_ts, part_100)
    _, _, summary_70 = compute_flexibility_timeseries(config, df_reg, df_ts, part_70)
    _, _, summary_40 = compute_flexibility_timeseries(config, df_reg, df_ts, part_40)

    # Total downward flexibility sum across 24h
    sum_100 = summary_100["total_down_kw"].sum()
    sum_70 = summary_70["total_down_kw"].sum()
    sum_40 = summary_40["total_down_kw"].sum()

    assert sum_100 >= sum_70 >= sum_40
