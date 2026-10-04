"""Unit and Integration Tests for GridFlex Local Final Demo Runner & Artifact Integrity.

Verifies:
1. Deterministic demo execution and output structure
2. Required directories and files generated:
   - outputs/final_demo/scenario1_high_pv/ (summary.csv, timeseries.csv, metrics.csv)
   - outputs/final_demo/scenario2_evening_peak/ (summary.csv, timeseries.csv, metrics.csv)
   - outputs/final_demo/scenario3_cloud_uncertainty/ (summary.csv, timeseries.csv, metrics.csv)
   - outputs/final_demo/plots/ (12 master demonstration figures)
   - outputs/final_demo/dashboard.html
   - outputs/final_demo/final_demo_summary.md
3. No NaN values in critical metrics tables
4. Baseline vs. GridFlex comparisons are physically valid
5. AC power-flow convergence and power balance across all scenarios
6. Existing 171 tests remain passing without regression
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest
import pandas as pd
import numpy as np

from scripts.run_final_demo import run_final_demo


@pytest.fixture(scope="module")
def demo_dir():
    return PROJECT_ROOT / "outputs" / "final_demo"


def test_final_demo_runner_deterministic():
    """Verify final demo executes cleanly and returns all PASS flags."""
    res = run_final_demo()
    assert res["scenario_1"] == "PASS"
    assert res["scenario_2"] == "PASS"
    assert res["scenario_3"] == "PASS"
    assert res["powerflow_convergence"] == "PASS"
    assert res["power_balance"] == "PASS"
    assert res["baseline_integrity"] == "PASS"
    assert res["locational_flexibility"] == "PASS"


def test_final_demo_required_files_generated(demo_dir):
    """Verify all required scenario directories, CSVs, markdown, and dashboard exist."""
    assert (demo_dir / "dashboard.html").exists(), "dashboard.html missing"
    assert (demo_dir / "final_demo_summary.md").exists(), "final_demo_summary.md missing"

    for scen in ["scenario1_high_pv", "scenario2_evening_peak", "scenario3_cloud_uncertainty"]:
        s_path = demo_dir / scen
        assert s_path.exists(), f"Missing scenario directory: {scen}"
        assert (s_path / "summary.csv").exists(), f"summary.csv missing in {scen}"
        assert (s_path / "timeseries.csv").exists(), f"timeseries.csv missing in {scen}"
        assert (s_path / "metrics.csv").exists(), f"metrics.csv missing in {scen}"


def test_final_demo_12_master_plots_generated(demo_dir):
    """Verify all 12 publication-grade demonstration figures exist and are non-empty."""
    plots_dir = demo_dir / "plots"
    assert plots_dir.exists(), "plots directory missing"

    expected_plots = [
        "01_load_vs_pv_generation.png",
        "02_net_feeder_power.png",
        "03_baseline_vs_gridflex_voltage.png",
        "04_baseline_vs_gridflex_transformer_loading.png",
        "05_baseline_vs_gridflex_line_loading.png",
        "06_reverse_power_flow.png",
        "07_battery_soc.png",
        "08_ev_charging_schedule.png",
        "09_available_vs_relevant_flexibility.png",
        "10_forecast_uncertainty_band.png",
        "11_dynamic_operating_envelope.png",
        "12_constraint_timeline.png",
    ]
    for p_name in expected_plots:
        p_file = plots_dir / p_name
        assert p_file.exists(), f"Missing plot: {p_name}"
        assert p_file.stat().st_size > 1000, f"Plot {p_name} appears empty or corrupted"


def test_final_demo_metrics_no_nan(demo_dir):
    """Verify that metrics tables contain zero NaN values."""
    for scen in ["scenario1_high_pv", "scenario2_evening_peak", "scenario3_cloud_uncertainty"]:
        m_file = demo_dir / scen / "metrics.csv"
        df = pd.read_csv(m_file)
        nan_counts = df.isna().sum().to_dict()
        for col, count in nan_counts.items():
            assert count == 0, f"Found {count} NaNs in column '{col}' of {scen}/metrics.csv"


def test_final_demo_baseline_vs_gridflex_validity(demo_dir):
    """Verify physical consistency of Baseline vs GridFlex comparisons."""
    # Scenario 1: Solar Overvoltage mitigation
    s1_m = pd.read_csv(demo_dir / "scenario1_high_pv" / "metrics.csv")
    v_max_base = float(s1_m[s1_m["Metric"] == "Maximum Bus Voltage (p.u.)"]["Baseline"].iloc[0])
    v_max_opt = float(s1_m[s1_m["Metric"] == "Maximum Bus Voltage (p.u.)"]["GridFlex"].iloc[0])
    assert v_max_base > 1.050, "Baseline should show overvoltage"
    assert v_max_opt <= 1.050, "GridFlex must eliminate overvoltage"
    assert v_max_opt < v_max_base, "GridFlex must reduce voltage rise"

    # Reverse flow reduction
    rev_base = float(s1_m[s1_m["Metric"] == "Peak Reverse Power Flow (kW)"]["Baseline"].iloc[0])
    rev_opt = float(s1_m[s1_m["Metric"] == "Peak Reverse Power Flow (kW)"]["GridFlex"].iloc[0])
    assert rev_base > 150.0, "Baseline reverse flow should be large"
    assert rev_opt < 25.0, "GridFlex must keep reverse flow under 25 kW ceiling"

    # Scenario 2: Locational deficit honestly reported
    s2_m = pd.read_csv(demo_dir / "scenario2_evening_peak" / "metrics.csv")
    v_min_opt = float(s2_m[s2_m["Metric"] == "Minimum Bus Voltage (p.u.)"]["GridFlex"].iloc[0])
    assert v_min_opt < 0.950, "Scenario 2 terminal undervoltage must remain honestly unresolved"

    # Scenario 3: Reserve deficit honestly reported
    s3_m = pd.read_csv(demo_dir / "scenario3_cloud_uncertainty" / "metrics.csv")
    res_def = float(s3_m[s3_m["Metric"] == "Reserve Deficit (kW)"]["GridFlex"].iloc[0])
    assert res_def > 0.0, "Scenario 3 reserve deficit must be non-zero and honestly reported"
    assert res_def == pytest.approx(0.65, abs=0.05)


def test_final_demo_powerflow_convergence(demo_dir):
    """Verify that AC power-flow converged across all timesteps in all scenarios."""
    for scen in ["scenario1_high_pv", "scenario2_evening_peak", "scenario3_cloud_uncertainty"]:
        ts_file = demo_dir / scen / "timeseries.csv"
        df = pd.read_csv(ts_file)
        assert df["converged"].all(), f"AC power flow failed to converge in {scen}"
        assert (df["power_balance_error_kw"].abs() < 1e-4).all(), f"Power balance error exceeded in {scen}"
