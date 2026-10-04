"""Unit and Integration Tests for Phase 7: Independent Power-Flow + Electrical Validation.

Tests cover:
- Section 30: Sanity tests (reproducibility, identical baseline schedules, zero-flex action, controlled battery injection)
- Section 31: Physical conservation, convergence, transformer loading, line loading, voltage limits, reverse flow,
  grid import/export sign convention, causal comparison integrity, and phase immutability.
"""

from pathlib import Path
import pytest
import numpy as np
import pandas as pd
import pandapower as pp

from src.utils.config import load_config
from src.powerflow_validation.engine import PowerFlowValidationEngine
from src.powerflow_validation.scenarios import run_all_validation_scenarios
from src.powerflow_validation.metrics import compute_electrical_scorecard, verify_causal_integrity


@pytest.fixture(scope="module")
def validation_engine():
    config = load_config()
    return PowerFlowValidationEngine(config)


@pytest.fixture(scope="module")
def phase7_data():
    csv_dir = Path("outputs/csv")
    return {
        "dispatch_df": pd.read_csv(csv_dir / "optimized_dispatch.csv"),
        "ev_df": pd.read_csv(csv_dir / "ev_schedule.csv"),
        "fl_df": pd.read_csv(csv_dir / "flexible_load_schedule.csv"),
        "pv_df": pd.read_csv(csv_dir / "pv_schedule.csv"),
        "bess_df": pd.read_csv(csv_dir / "battery_schedule.csv"),
        "nl_fc_df": pd.read_csv(csv_dir / "net_load_forecast.csv"),
        "pv_fc_df": pd.read_csv(csv_dir / "pv_forecast.csv"),
    }


def test_powerflow_convergence(validation_engine, phase7_data):
    """Verify that both baseline and GridFlex power flows achieve 100% numerical convergence."""
    ts_df = pd.read_csv("outputs/csv/powerflow_timeseries.csv")
    assert not ts_df.empty, "Powerflow timeseries should not be empty."
    assert (ts_df["converged"] == True).all(), f"All power flows must converge. Failures: {(ts_df['converged'] == False).sum()}"


def test_physical_power_balance(validation_engine):
    """Verify that pandapower power flows strictly satisfy physical power balance (error < 0.01 kW)."""
    ts_df = pd.read_csv("outputs/csv/powerflow_timeseries.csv")
    max_err = ts_df["power_balance_error_kw"].max()
    mean_err = ts_df["power_balance_error_kw"].mean()
    assert max_err < 0.01, f"Max power balance error ({max_err} kW) exceeds 0.01 kW threshold."
    assert mean_err < 0.001, f"Mean power balance error ({mean_err} kW) exceeds 0.001 kW threshold."


def test_transformer_and_line_loading(validation_engine):
    """Verify transformer and line loadings are physically valid and non-negative."""
    ts_df = pd.read_csv("outputs/csv/powerflow_timeseries.csv")
    assert (ts_df["transformer_loading_percent"] >= 0.0).all()
    assert (ts_df["transformer_loading_percent"] <= 200.0).all()
    assert (ts_df["max_line_loading_percent"] >= 0.0).all()


def test_voltage_limits_and_improvement(validation_engine):
    """Verify that voltages are within reasonable range and GridFlex improves or maintains voltage."""
    ts_df = pd.read_csv("outputs/csv/powerflow_timeseries.csv")
    assert (ts_df["min_bus_voltage_pu"] >= 0.85).all()
    assert (ts_df["max_bus_voltage_pu"] <= 1.15).all()

    norm_base = ts_df[(ts_df["scenario"] == "NORMAL_DAY") & (ts_df["case"] == "CASE_A_BASELINE")]
    norm_flex = ts_df[(ts_df["scenario"] == "NORMAL_DAY") & (ts_df["case"] == "CASE_B_GRIDFLEX")]

    # During congested evening hours, GridFlex should improve lowest voltage
    min_v_base = norm_base["min_bus_voltage_pu"].min()
    min_v_flex = norm_flex["min_bus_voltage_pu"].min()
    assert min_v_flex >= min_v_base - 1e-5, f"GridFlex min voltage ({min_v_flex}) should not be worse than baseline ({min_v_base})."


def test_reverse_power_detection_and_sign_convention():
    """Verify correct sign convention for external grid import and reverse export."""
    ts_df = pd.read_csv("outputs/csv/powerflow_timeseries.csv")
    for _, row in ts_df.iterrows():
        imp = row["grid_import_kw"]
        exp = row["grid_export_kw"]
        rev = row["reverse_power_kw"]
        assert imp >= 0.0
        assert exp >= 0.0
        assert rev >= 0.0
        if exp > 0.1:
            assert abs(rev - exp) < 1e-2
            assert imp == 0.0


def test_sanity_test_1_and_2_reproducibility(validation_engine, phase7_data):
    """Sanity Tests 1 & 2: Running baseline and GridFlex twice produces identical electrical results."""
    timesteps = [pd.Timestamp("2011-09-16 13:30:00")]
    base_load = [60.0]
    empty_sched = {k: [0.0] for k in validation_engine.pv_meta}
    ev_sched = {k: [0.0] for k in validation_engine.ev_ids}
    fl_sched = {k: [0.0] for k in validation_engine.flex_ids}
    bess_sched = [0.0]

    ts1, _, _, _, _ = validation_engine.run_case_simulation(
        "TEST", "BASE1", timesteps, base_load, empty_sched, ev_sched, fl_sched, bess_sched
    )
    ts2, _, _, _, _ = validation_engine.run_case_simulation(
        "TEST", "BASE2", timesteps, base_load, empty_sched, ev_sched, fl_sched, bess_sched
    )

    np.testing.assert_allclose(
        ts1["transformer_loading_percent"].values,
        ts2["transformer_loading_percent"].values,
        atol=1e-5,
    )
    np.testing.assert_allclose(
        ts1["min_bus_voltage_pu"].values,
        ts2["min_bus_voltage_pu"].values,
        atol=1e-5,
    )


def test_sanity_test_3_and_4_zero_flex_matches_baseline(validation_engine, phase7_data):
    """Sanity Tests 3 & 4: Setting all GridFlex flexibility actions to zero matches baseline exactly."""
    timesteps = [pd.Timestamp("2011-09-16 14:00:00")]
    base_load = [80.0]
    pv_sched = {k: [3.0] for k in validation_engine.pv_meta}
    ev_sched = {k: [0.0] for k in validation_engine.ev_ids}
    fl_sched = {k: [0.0] for k in validation_engine.flex_ids}
    bess_sched = [0.0]

    ts_base, _, _, _, _ = validation_engine.run_case_simulation(
        "TEST", "BASE", timesteps, base_load, pv_sched, ev_sched, fl_sched, bess_sched
    )
    ts_flex_zero, _, _, _, _ = validation_engine.run_case_simulation(
        "TEST", "FLEX_ZERO", timesteps, base_load, pv_sched, ev_sched, fl_sched, bess_sched
    )

    np.testing.assert_allclose(
        ts_base["grid_import_kw"].values,
        ts_flex_zero["grid_import_kw"].values,
        atol=1e-4,
    )
    np.testing.assert_allclose(
        ts_base["transformer_loading_percent"].values,
        ts_flex_zero["transformer_loading_percent"].values,
        atol=1e-4,
    )


def test_sanity_test_5_controlled_battery_injection(validation_engine):
    """Sanity Test 5: A controlled battery discharge reduces grid import consistently with power balance."""
    timesteps = [pd.Timestamp("2011-09-16 17:00:00")]
    base_load = [100.0]
    pv_sched = {k: [0.0] for k in validation_engine.pv_meta}
    ev_sched = {k: [0.0] for k in validation_engine.ev_ids}
    fl_sched = {k: [0.0] for k in validation_engine.flex_ids}

    # BESS idle
    ts_idle, _, _, _, _ = validation_engine.run_case_simulation(
        "TEST", "IDLE", timesteps, base_load, pv_sched, ev_sched, fl_sched, [0.0]
    )
    # BESS discharging 20 kW
    ts_disch, _, _, _, _ = validation_engine.run_case_simulation(
        "TEST", "DISCH", timesteps, base_load, pv_sched, ev_sched, fl_sched, [20.0]
    )

    import_idle = ts_idle["grid_import_kw"].iloc[0]
    import_disch = ts_disch["grid_import_kw"].iloc[0]
    delta_import = import_idle - import_disch

    # Delta import should be approximately 20 kW (minus minor delta in feeder losses)
    assert 19.0 <= delta_import <= 21.0, f"Expected ~20 kW import reduction, got {delta_import:.2f} kW."


def test_causal_integrity_verification():
    """Verify all conditions in comparison_integrity_check.csv are PASS."""
    integrity_df = pd.read_csv("outputs/csv/comparison_integrity_check.csv")
    assert (integrity_df["status"] == "PASS").all(), "All causal comparison integrity checks must pass."


def test_cloud_scenario_consistency():
    """Verify that cloud scenario exhibits increased grid import during the irradiance dip."""
    ts_df = pd.read_csv("outputs/csv/powerflow_timeseries.csv")
    cloud_base = ts_df[(ts_df["scenario"] == "CLOUD_EVENT") & (ts_df["case"] == "CASE_A_BASELINE_CLOUD")]
    norm_base = ts_df[(ts_df["scenario"] == "NORMAL_DAY") & (ts_df["case"] == "CASE_A_BASELINE")]

    # During cloud event hour (index 6 to 9, 15:00 to 15:45), solar drop must increase net grid import
    imp_cloud = cloud_base.iloc[6:10]["grid_import_kw"].mean()
    imp_norm = norm_base.iloc[6:10]["grid_import_kw"].mean()
    assert imp_cloud > imp_norm, "Cloud event must decrease solar and thus increase grid import."


def test_participation_scenario_consistency():
    """Verify that higher participation provides equal or greater peak import reduction."""
    summ_df = pd.read_csv("outputs/csv/gridflex_validation_summary.csv")
    part_df = summ_df[summ_df["scenario"] == "PARTICIPATION"]
    assert not part_df.empty

    row_100 = part_df[part_df["case"] == "GRIDFLEX_100PCT"].iloc[0]
    row_40 = part_df[part_df["case"] == "GRIDFLEX_40PCT"].iloc[0]
    assert row_100["peak_grid_import_kw"] <= row_40["peak_grid_import_kw"] + 1e-3


def test_phase1_baseline_unmutated():
    """Verify Phase 1 generated baseline profiles and registry remain strictly intact."""
    p1_res = Path("data/generated/residential_profiles.csv")
    assert p1_res.exists()
    df = pd.read_csv(p1_res)
    assert df.shape == (96, 101)

    p1_reg = Path("outputs/csv/der_registry.csv")
    assert p1_reg.exists()
    reg = pd.read_csv(p1_reg)
    assert len(reg) == 84
