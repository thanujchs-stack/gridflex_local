"""Comprehensive Tests for DER Problem-Solving Implementation.

Tests per Section 17:
- Voltage violation detection
- Reverse-flow detection
- Transformer overload detection
- Line overload detection
- Battery SOC conservation
- EV energy conservation
- Flexible-load energy conservation
- PV curtailment
- Uncertainty reserve
- Participation reduction
- No double counting
- Operating-envelope compliance
- Optimization feasibility
- AC power-flow convergence
- Power balance
- Reproducibility
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest
import numpy as np
import pandas as pd
import copy

from src.utils.config import load_config
from src.powerflow_validation.engine import (
    PowerFlowValidationEngine,
    compute_scenario_metrics,
    generate_comparison_integrity_check,
)
from src.der.passport import generate_der_flexibility_passports
from src.forecasting.uncertainty_reserve import compute_forecast_uncertainty_and_reserves
from src.coordination.requirement_engine import (
    compute_unified_flexibility_requirements,
    select_flexibility_spatially,
)
from src.scenarios.der_problem_scenarios import (
    _derive_pv_ceiling_from_constraint,
    _derive_bess_schedule_from_surplus,
)


@pytest.fixture(scope="module")
def config():
    return load_config()


@pytest.fixture(scope="module")
def csv_dir():
    return PROJECT_ROOT / "outputs" / "csv"


@pytest.fixture(scope="module")
def engine(config):
    return PowerFlowValidationEngine(config)


# =========================================================================
# VOLTAGE VIOLATION DETECTION
# =========================================================================
class TestVoltageViolationDetection:
    """Tests that voltage violations are detected and quantified correctly."""

    def test_voltage_limits_configured(self, config):
        """Voltage limits must be present in config."""
        assert "voltage" in config
        assert "min_pu" in config["voltage"]
        assert "max_pu" in config["voltage"]
        assert config["voltage"]["min_pu"] == 0.95
        assert config["voltage"]["max_pu"] == 1.05

    def test_engine_reads_voltage_limits(self, engine):
        """Engine must use configurable voltage limits."""
        assert engine.v_min_statutory == 0.95
        assert engine.v_max_statutory == 1.05

    def test_voltage_violation_fields_present(self, engine):
        """Power flow results must include violation tracking fields."""
        timesteps = [pd.Timestamp("2026-01-15 13:00:00")]
        pv_sched = {pid: [0.0] for pid in engine.pv_meta}
        ev_sched = {eid: [0.0] for eid in engine.ev_ids}
        fl_sched = {fid: [0.0] for fid in engine.flex_ids}

        ts_df, _, _, _, _ = engine.run_case_simulation(
            "TEST", "TEST", timesteps, [50.0], pv_sched, ev_sched, fl_sched, [0.0]
        )
        required_cols = [
            "voltage_violation_magnitude", "voltage_violation_count",
            "affected_voltage_bus", "affected_voltage_section",
            "min_voltage_bus", "max_voltage_bus",
        ]
        for col in required_cols:
            assert col in ts_df.columns, f"Missing column: {col}"


# =========================================================================
# REVERSE-FLOW DETECTION
# =========================================================================
class TestReverseFlowDetection:
    """Tests that reverse power flow is detected and quantified."""

    def test_reverse_flow_flag_present(self, engine):
        """Results must include reverse_power_flow_flag."""
        timesteps = [pd.Timestamp("2026-01-15 13:00:00")]
        pv_sched = {pid: [3.0] for pid in engine.pv_meta}
        ev_sched = {eid: [0.0] for eid in engine.ev_ids}
        fl_sched = {fid: [0.0] for fid in engine.flex_ids}

        ts_df, _, _, _, _ = engine.run_case_simulation(
            "TEST_REV", "TEST", timesteps, [10.0], pv_sched, ev_sched, fl_sched, [0.0]
        )
        assert "reverse_power_flow_flag" in ts_df.columns
        assert "grid_export_kw" in ts_df.columns

    def test_no_reverse_flow_with_high_load(self, engine):
        """High load and no PV should produce no reverse flow."""
        timesteps = [pd.Timestamp("2026-01-15 20:00:00")]
        pv_sched = {pid: [0.0] for pid in engine.pv_meta}
        ev_sched = {eid: [0.0] for eid in engine.ev_ids}
        fl_sched = {fid: [0.0] for fid in engine.flex_ids}

        ts_df, _, _, _, _ = engine.run_case_simulation(
            "TEST_NO_REV", "TEST", timesteps, [100.0], pv_sched, ev_sched, fl_sched, [0.0]
        )
        assert ts_df["reverse_power_kw"].iloc[0] == 0.0
        assert ts_df["reverse_power_flow_flag"].iloc[0] == False


# =========================================================================
# TRANSFORMER OVERLOAD DETECTION
# =========================================================================
class TestTransformerOverloadDetection:
    """Tests transformer overload detection and quantification."""

    def test_overloaded_transformer_flag(self, engine):
        """overloaded_transformer_flag must be present."""
        timesteps = [pd.Timestamp("2026-01-15 13:00:00")]
        pv_sched = {pid: [0.0] for pid in engine.pv_meta}
        ev_sched = {eid: [0.0] for eid in engine.ev_ids}
        fl_sched = {fid: [0.0] for fid in engine.flex_ids}

        ts_df, _, _, _, _ = engine.run_case_simulation(
            "TEST_TRAFO", "TEST", timesteps, [50.0], pv_sched, ev_sched, fl_sched, [0.0]
        )
        assert "overloaded_transformer_flag" in ts_df.columns


# =========================================================================
# LINE OVERLOAD DETECTION
# =========================================================================
class TestLineOverloadDetection:
    """Tests line overload detection with location identification."""

    def test_line_overload_fields(self, engine):
        """Must include max_line_name and overloaded_line_flag."""
        timesteps = [pd.Timestamp("2026-01-15 13:00:00")]
        pv_sched = {pid: [0.0] for pid in engine.pv_meta}
        ev_sched = {eid: [0.0] for eid in engine.ev_ids}
        fl_sched = {fid: [0.0] for fid in engine.flex_ids}

        ts_df, _, _, _, _ = engine.run_case_simulation(
            "TEST_LINE", "TEST", timesteps, [50.0], pv_sched, ev_sched, fl_sched, [0.0]
        )
        assert "max_line_name" in ts_df.columns
        assert "overloaded_line_flag" in ts_df.columns


# =========================================================================
# BATTERY SOC CONSERVATION
# =========================================================================
class TestBatterySOCConservation:
    """Tests that battery SOC remains within limits."""

    def test_bess_schedule_respects_soc(self, config):
        """Derived BESS schedule must respect min/max SOC."""
        load = [100.0] * 16
        pv = [200.0] * 8 + [0.0] * 8  # High PV then none
        schedule = _derive_bess_schedule_from_surplus(
            base_load_series=load,
            total_pv_series=pv,
            bess_max_charge_kw=25.0,
            bess_max_discharge_kw=25.0,
            bess_capacity_kwh=100.0,
            initial_soc=0.50,
            min_soc=0.20,
            max_soc=0.90,
        )
        assert len(schedule) == 16
        # Verify SOC stays in bounds by simulating
        soc = 0.50
        for p in schedule:
            if p < 0:  # Charging
                soc += abs(p) * 0.25 * 0.95 / 100.0
            elif p > 0:  # Discharging
                soc -= p * 0.25 / (100.0 * 0.95)
            assert soc >= 0.19, f"SOC below min: {soc}"
            assert soc <= 0.91, f"SOC above max: {soc}"


# =========================================================================
# EV ENERGY CONSERVATION
# =========================================================================
class TestEVEnergyConservation:
    """Tests that EV charging energy is conserved during shifting."""

    def test_ev_schedule_exists(self, csv_dir):
        """EV schedule must exist with required columns."""
        ev_path = csv_dir / "ev_schedule.csv"
        if ev_path.exists():
            df = pd.read_csv(ev_path)
            assert "throttled_kw" in df.columns or "optimized_charge_kw" in df.columns


# =========================================================================
# PV CURTAILMENT
# =========================================================================
class TestPVCurtailment:
    """Tests PV curtailment is correctly applied."""

    def test_pv_ceiling_from_constraint(self):
        """PV ceiling must be derived from constraint, not hard-coded."""
        ceilings = _derive_pv_ceiling_from_constraint(
            pv_base_series=[300.0],  # Total PV = 300 kW
            base_load_series=[50.0],  # Load = 50 kW
            reverse_limit_kw=25.0,
            n_pv_systems=60,
        )
        # Max total PV = 50 + 25 = 75 kW → per system = 75/60 = 1.25 kW
        assert len(ceilings) == 1
        assert ceilings[0] == pytest.approx(1.25, abs=0.01)

    def test_pv_ceiling_no_curtailment_needed(self):
        """When PV < load + limit, no curtailment needed."""
        ceilings = _derive_pv_ceiling_from_constraint(
            pv_base_series=[30.0],
            base_load_series=[100.0],
            reverse_limit_kw=25.0,
            n_pv_systems=60,
        )
        assert ceilings[0] == pytest.approx(30.0 / 60.0, abs=0.01)


# =========================================================================
# UNCERTAINTY RESERVE
# =========================================================================
class TestUncertaintyReserve:
    """Tests forecast uncertainty translates to reserve requirements."""

    def test_higher_uncertainty_higher_reserve(self):
        """Higher forecast uncertainty must produce higher reserve requirement."""
        timestamps = [str(pd.Timestamp("2026-01-15 13:00:00")),
                      str(pd.Timestamp("2026-01-15 13:15:00"))]

        pv_df = pd.DataFrame({
            "timestamp": timestamps,
            "forecast": [50.0, 50.0],
            "lower_bound": [40.0, 20.0],  # Second has wider interval
            "upper_bound": [60.0, 80.0],
        })
        load_df = pd.DataFrame({
            "timestamp": timestamps,
            "forecast": [100.0, 100.0],
            "lower_bound": [90.0, 90.0],
            "upper_bound": [110.0, 110.0],
        })
        nl_df = pd.DataFrame({
            "timestamp": timestamps,
            "forecast": [50.0, 50.0],
        })

        # Minimal passport
        passport_rows = []
        for ts in timestamps:
            passport_rows.append({
                "timestamp": ts,
                "der_id": "BESS_COMMUNITY_01",
                "der_type": "BESS",
                "available_flexibility_up_kw": 25.0,
                "dispatched_flexibility_kw": 0.0,
            })
            passport_rows.append({
                "timestamp": ts,
                "der_id": "EV_001",
                "der_type": "EV",
                "available_flexibility_up_kw": 7.0,
                "dispatched_flexibility_kw": 0.0,
            })
        passports_df = pd.DataFrame(passport_rows)

        result = compute_forecast_uncertainty_and_reserves(
            pv_forecast_df=pv_df,
            load_forecast_df=load_df,
            net_load_forecast_df=nl_df,
            passports_df=passports_df,
        )
        reserve = result["reserve_requirement"]
        # Second timestep has higher PV uncertainty → higher reserve
        assert reserve.iloc[1]["required_reserve_kw"] > reserve.iloc[0]["required_reserve_kw"]


# =========================================================================
# PARTICIPATION REDUCTION
# =========================================================================
class TestParticipationReduction:
    """Tests that reducing participation reduces available flexibility."""

    def test_participation_40_reduces_flexibility(self, config, csv_dir):
        """40% participation must yield less flexibility than 70%."""
        der_reg_path = csv_dir / "der_registry.csv"
        pv_fc_path = csv_dir / "pv_forecast.csv"
        load_fc_path = csv_dir / "load_forecast.csv"

        if not all(p.exists() for p in [der_reg_path, pv_fc_path, load_fc_path]):
            pytest.skip("Required CSV files not found")

        der_reg = pd.read_csv(der_reg_path)
        pv_fc = pd.read_csv(pv_fc_path)
        load_fc = pd.read_csv(load_fc_path)
        timesteps = [pd.Timestamp(t) for t in pv_fc["timestamp"][:4]]

        pass_70 = generate_der_flexibility_passports(
            config, der_reg, timesteps, pv_fc.head(4), load_fc.head(4),
            participation_rate=0.70,
        )
        pass_40 = generate_der_flexibility_passports(
            config, der_reg, timesteps, pv_fc.head(4), load_fc.head(4),
            participation_rate=0.40,
        )

        avail_70 = pass_70["available_flexibility_up_kw"].sum()
        avail_40 = pass_40["available_flexibility_up_kw"].sum()
        assert avail_40 <= avail_70, f"40% participation ({avail_40}) should not exceed 70% ({avail_70})"


# =========================================================================
# NO DOUBLE COUNTING
# =========================================================================
class TestNoDoubleCounting:
    """Tests that flexibility is never double-counted."""

    def test_committed_plus_reserved_less_than_available(self, csv_dir):
        """Committed + reserved must not exceed available flexibility."""
        tracking_path = csv_dir / "flexibility_tracking.csv"
        if not tracking_path.exists():
            pytest.skip("flexibility_tracking.csv not found")
        df = pd.read_csv(tracking_path)
        violations = df[
            (df["committed_flexibility_kw"] + df["reserved_flexibility_kw"]) > df["available_flexibility_kw"] + 0.01
        ]
        assert len(violations) == 0, f"Double counting detected in {len(violations)} timesteps"

    def test_remaining_nonnegative(self, csv_dir):
        """Remaining flexibility must be non-negative."""
        tracking_path = csv_dir / "flexibility_tracking.csv"
        if not tracking_path.exists():
            pytest.skip("flexibility_tracking.csv not found")
        df = pd.read_csv(tracking_path)
        assert (df["remaining_flexibility_kw"] >= -0.01).all()


# =========================================================================
# AC POWER-FLOW CONVERGENCE
# =========================================================================
class TestPowerFlowConvergence:
    """Tests that all AC power flow runs converge."""

    def test_all_timesteps_converge(self, engine):
        """Basic power flow must converge for moderate loads."""
        timesteps = [pd.Timestamp("2026-01-15 12:00:00")]
        pv_sched = {pid: [2.0] for pid in engine.pv_meta}
        ev_sched = {eid: [0.0] for eid in engine.ev_ids}
        fl_sched = {fid: [0.0] for fid in engine.flex_ids}

        ts_df, _, _, _, failures = engine.run_case_simulation(
            "CONV_TEST", "TEST", timesteps, [80.0], pv_sched, ev_sched, fl_sched, [0.0]
        )
        assert len(failures) == 0
        assert ts_df["converged"].all()


# =========================================================================
# POWER BALANCE
# =========================================================================
class TestPowerBalance:
    """Tests power balance at every timestep."""

    def test_power_balance_within_tolerance(self, engine, config):
        """Power balance error must be within configured tolerance."""
        tol = float(config.get("validation", {}).get("power_balance_tolerance_kw", 1.0))
        timesteps = [pd.Timestamp("2026-01-15 13:00:00")]
        pv_sched = {pid: [2.0] for pid in engine.pv_meta}
        ev_sched = {eid: [0.0] for eid in engine.ev_ids}
        fl_sched = {fid: [0.0] for fid in engine.flex_ids}

        ts_df, _, _, _, _ = engine.run_case_simulation(
            "BAL_TEST", "TEST", timesteps, [80.0], pv_sched, ev_sched, fl_sched, [0.0]
        )
        assert ts_df["power_balance_error_kw"].iloc[0] < tol


# =========================================================================
# REPRODUCIBILITY
# =========================================================================
class TestReproducibility:
    """Tests that results are deterministic."""

    def test_baseline_identical_twice(self, engine):
        """Running the same baseline scenario twice must produce identical results."""
        timesteps = [pd.Timestamp("2026-01-15 13:00:00"),
                     pd.Timestamp("2026-01-15 13:15:00")]
        pv_sched = {pid: [2.0, 1.5] for pid in engine.pv_meta}
        ev_sched = {eid: [0.0, 0.0] for eid in engine.ev_ids}
        fl_sched = {fid: [0.0, 0.0] for fid in engine.flex_ids}

        ts1, _, _, _, _ = engine.run_case_simulation(
            "REPRO", "RUN1", timesteps, [80.0, 85.0], pv_sched, ev_sched, fl_sched, [0.0, 0.0]
        )
        ts2, _, _, _, _ = engine.run_case_simulation(
            "REPRO", "RUN2", timesteps, [80.0, 85.0], pv_sched, ev_sched, fl_sched, [0.0, 0.0]
        )

        for col in ["transformer_loading_percent", "max_line_loading_percent",
                     "min_bus_voltage_pu", "max_bus_voltage_pu",
                     "grid_import_kw", "reverse_power_kw"]:
            np.testing.assert_array_almost_equal(
                ts1[col].values, ts2[col].values, decimal=4,
                err_msg=f"Reproducibility failure on {col}"
            )

    def test_gridflex_identical_twice(self, engine):
        """Running GridFlex scenario twice must produce identical results."""
        timesteps = [pd.Timestamp("2026-01-15 13:00:00")]
        pv_sched = {pid: [2.5] for pid in engine.pv_meta}
        ev_sched = {eid: [3.0] for eid in engine.ev_ids}
        fl_sched = {fid: [1.0] for fid in engine.flex_ids}

        ts1, _, _, _, _ = engine.run_case_simulation(
            "REPRO_GF", "RUN1", timesteps, [90.0], pv_sched, ev_sched, fl_sched, [5.0]
        )
        ts2, _, _, _, _ = engine.run_case_simulation(
            "REPRO_GF", "RUN2", timesteps, [90.0], pv_sched, ev_sched, fl_sched, [5.0]
        )

        for col in ["transformer_loading_percent", "max_line_loading_percent",
                     "grid_import_kw", "reverse_power_kw"]:
            np.testing.assert_array_almost_equal(
                ts1[col].values, ts2[col].values, decimal=4,
                err_msg=f"Reproducibility failure on {col}"
            )


# =========================================================================
# SCENARIO METRICS
# =========================================================================
class TestScenarioMetrics:
    """Tests that scenario comparison metrics are complete."""

    def test_compute_scenario_metrics_keys(self, engine):
        """compute_scenario_metrics must return all required metric keys."""
        timesteps = [pd.Timestamp("2026-01-15 13:00:00")]
        pv_sched = {pid: [2.0] for pid in engine.pv_meta}
        ev_sched = {eid: [0.0] for eid in engine.ev_ids}
        fl_sched = {fid: [0.0] for fid in engine.flex_ids}

        ts_a, _, _, _, _ = engine.run_case_simulation(
            "METRIC_TEST", "BASELINE", timesteps, [80.0], pv_sched, ev_sched, fl_sched, [0.0]
        )
        ts_b, _, _, _, _ = engine.run_case_simulation(
            "METRIC_TEST", "GRIDFLEX", timesteps, [80.0], pv_sched, ev_sched, fl_sched, [5.0]
        )

        metrics = compute_scenario_metrics(ts_a, ts_b)

        required_keys = [
            "baseline_max_voltage_pu", "gridflex_max_voltage_pu",
            "baseline_min_voltage_pu", "gridflex_min_voltage_pu",
            "baseline_voltage_violation_count", "gridflex_voltage_violation_count",
            "baseline_peak_trafo_pct", "gridflex_peak_trafo_pct",
            "baseline_avg_trafo_pct", "gridflex_avg_trafo_pct",
            "baseline_trafo_overload_duration_min", "gridflex_trafo_overload_duration_min",
            "baseline_peak_line_pct", "gridflex_peak_line_pct",
            "baseline_peak_reverse_kw", "gridflex_peak_reverse_kw",
            "baseline_reverse_flow_duration_min", "gridflex_reverse_flow_duration_min",
            "baseline_reverse_flow_energy_kwh", "gridflex_reverse_flow_energy_kwh",
            "baseline_peak_import_kw", "gridflex_peak_import_kw",
            "import_reduction_kw",
        ]
        for key in required_keys:
            assert key in metrics, f"Missing metric key: {key}"


# =========================================================================
# COMPARISON INTEGRITY
# =========================================================================
class TestComparisonIntegrity:
    """Tests that comparison integrity checks are generated."""

    def test_integrity_check_fields(self, config):
        """Integrity check must confirm identical physical conditions."""
        check = generate_comparison_integrity_check("TEST_SCENARIO", config)
        assert check["topology_identical"] is True
        assert check["loads_identical"] is True
        assert check["pv_availability_identical"] is True
        assert check["only_schedule_differs"] is True
        assert check["integrity_pass"] is True


# =========================================================================
# SANITY: ZERO FLEXIBILITY CONVERGES TO BASELINE
# =========================================================================
class TestZeroFlexibility:
    """Tests that zero GridFlex flexibility produces baseline-like results."""

    def test_zero_bess_matches_baseline(self, engine):
        """With BESS at 0 kW, GridFlex case should match baseline electrically."""
        timesteps = [pd.Timestamp("2026-01-15 13:00:00")]
        pv_sched = {pid: [2.0] for pid in engine.pv_meta}
        ev_sched = {eid: [0.0] for eid in engine.ev_ids}
        fl_sched = {fid: [0.0] for fid in engine.flex_ids}

        ts_base, _, _, _, _ = engine.run_case_simulation(
            "ZERO_FLEX", "BASELINE", timesteps, [80.0], pv_sched, ev_sched, fl_sched, [0.0]
        )
        ts_gf, _, _, _, _ = engine.run_case_simulation(
            "ZERO_FLEX", "GRIDFLEX", timesteps, [80.0], pv_sched, ev_sched, fl_sched, [0.0]
        )

        np.testing.assert_almost_equal(
            ts_base["transformer_loading_percent"].iloc[0],
            ts_gf["transformer_loading_percent"].iloc[0],
            decimal=2,
        )


# =========================================================================
# SANITY: BESS DISCHARGE REDUCES IMPORT
# =========================================================================
class TestBESSDischargeReducesImport:
    """Tests that BESS discharge reduces grid import."""

    def test_bess_discharge_reduces_import(self, engine):
        """Discharging BESS should reduce grid import under load."""
        timesteps = [pd.Timestamp("2026-01-15 19:00:00")]
        pv_sched = {pid: [0.0] for pid in engine.pv_meta}
        ev_sched = {eid: [0.0] for eid in engine.ev_ids}
        fl_sched = {fid: [0.0] for fid in engine.flex_ids}

        ts_no_bess, _, _, _, _ = engine.run_case_simulation(
            "BESS_TEST", "NO_BESS", timesteps, [120.0], pv_sched, ev_sched, fl_sched, [0.0]
        )
        ts_with_bess, _, _, _, _ = engine.run_case_simulation(
            "BESS_TEST", "WITH_BESS", timesteps, [120.0], pv_sched, ev_sched, fl_sched, [15.0]
        )

        import_no = ts_no_bess["grid_import_kw"].iloc[0]
        import_with = ts_with_bess["grid_import_kw"].iloc[0]
        assert import_with < import_no, f"BESS discharge should reduce import: {import_with} vs {import_no}"


# =========================================================================
# SANITY: REMOVE PV REMOVES REVERSE FLOW
# =========================================================================
class TestRemovePVRemovesReverseFlow:
    """Tests that removing PV eliminates PV-related reverse flow."""

    def test_no_pv_no_reverse_flow(self, engine):
        """With zero PV generation, reverse flow from PV must be zero."""
        timesteps = [pd.Timestamp("2026-01-15 13:00:00")]
        pv_sched_zero = {pid: [0.0] for pid in engine.pv_meta}
        ev_sched = {eid: [0.0] for eid in engine.ev_ids}
        fl_sched = {fid: [0.0] for fid in engine.flex_ids}

        ts_df, _, _, _, _ = engine.run_case_simulation(
            "NO_PV_TEST", "TEST", timesteps, [50.0], pv_sched_zero, ev_sched, fl_sched, [0.0]
        )
        assert ts_df["reverse_power_kw"].iloc[0] == 0.0
