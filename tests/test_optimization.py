"""Unit tests for Phase 6 Optimization + Dispatch Planning.

Tests compliance with:
- Multi-objective LP formulation
- Envelope limit respect
- Battery energy balance and reserve margin
- EV departure energy protection and V2G disabled
- Flexible load service energy conservation
- Optimization Sanity Test (Section 24)
- Extreme Case Tests A-H (Section 25)
- Deterministic reproducibility (Section 26)
- Phase 1 baseline integrity
"""

import pytest
import pandas as pd
import numpy as np
import yaml

from src.utils.config import load_config
from src.optimization.problem import OptimizationProblem
from src.optimization.solver import DispatchOptimizer
from src.optimization.dispatcher import generate_dispatch_plan
from scripts.run_phase6 import load_optimization_config


@pytest.fixture
def config():
    return load_config()


@pytest.fixture
def opt_config():
    return load_optimization_config()


@pytest.fixture
def solved_phase6_plan(config, opt_config):
    envs_df = pd.read_csv("outputs/csv/dynamic_operating_envelopes.csv")
    plan_df = pd.read_csv("outputs/csv/coordination_plan.csv")
    nl_df = pd.read_csv("outputs/csv/net_load_forecast.csv")
    pv_df = pd.read_csv("outputs/csv/pv_forecast.csv")
    load_df = pd.read_csv("outputs/csv/load_forecast.csv")

    prob = OptimizationProblem(
        config=config,
        opt_config=opt_config,
        envelopes_df=envs_df,
        coordination_plan_df=plan_df,
        net_load_forecast_df=nl_df,
        pv_forecast_df=pv_df,
        load_forecast_df=load_df,
        initial_bess_soc=0.50,
        participation_rate=0.70,
    )
    solver = DispatchOptimizer(prob)
    res = solver.solve()
    assert res["success"] is True
    plan = generate_dispatch_plan(prob, res)
    return prob, res, plan


# 1. Objective function and solver status
def test_solver_optimal_solution(solved_phase6_plan):
    _, res, plan = solved_phase6_plan
    assert res["solver_status"] == "OPTIMAL"
    assert res["objective_value"] > 0.0
    summary = plan["optimization_summary"].iloc[0]
    assert summary["solver_status"] == "OPTIMAL"
    assert summary["constraint_violation"] == 0.0


# 2. Operating envelopes respected
def test_dispatch_within_envelopes(solved_phase6_plan):
    _, _, plan = solved_phase6_plan
    dispatch_df = plan["optimized_dispatch"]
    for _, row in dispatch_df.iterrows():
        opt = row["optimized_kw"]
        dyn_min = row["dynamic_min_kw"]
        dyn_max = row["dynamic_max_kw"]
        # Allow tiny numerical tolerance
        assert opt >= dyn_min - 1e-4, f"Violation for {row['der_id']}: {opt} < {dyn_min}"
        assert opt <= dyn_max + 1e-4, f"Violation for {row['der_id']}: {opt} > {dyn_max}"


# 3. Battery constraints (SOC and reserve)
def test_battery_schedule_constraints(solved_phase6_plan):
    _, _, plan = solved_phase6_plan
    bat_df = plan["battery_schedule"]
    for _, row in bat_df.iterrows():
        # SOC floor = 30% (20% min + 10% reserve)
        assert row["soc"] >= (row["soc_min"] + row["reserve_soc"]) - 1e-4
        assert row["soc"] <= row["soc_max"] + 1e-4
        assert row["charge_kw"] >= 0.0
        assert row["discharge_kw"] >= 0.0


# 4. EV energy requirement and V2G disabled
def test_ev_schedule_constraints(solved_phase6_plan):
    _, _, plan = solved_phase6_plan
    ev_df = plan["ev_schedule"]
    assert (ev_df["optimized_charge_kw"] >= 0.0).all()
    assert (ev_df["departure_guaranteed"] == True).all()


# 5. Flexible load energy bounds
def test_flexible_load_constraints(solved_phase6_plan):
    _, _, plan = solved_phase6_plan
    fl_df = plan["flexible_load_schedule"]
    for _, row in fl_df.iterrows():
        assert row["optimized_power_kw"] >= 0.0
        assert row["service_conserved"] is True


# 6. Sanity Test (Section 24)
def test_optimization_sanity_test(config, opt_config):
    """Sanity test: 10 kW required flexibility with 4 candidate resources."""
    # Test problem with 10 kW required
    from scripts.sanity_test_coordination import run_single_timestep_coordination
    r1 = run_single_timestep_coordination(required_kw=10.0)
    r2 = run_single_timestep_coordination(required_kw=10.0)

    # 1. Total allocated <= 10.0 kW
    assert r1["total_allocated_kw"] <= 10.0
    # 2. Never allocate more than available
    assert r1["allocations"]["BESS_01"] <= 4.0
    assert r1["allocations"]["EV_01"] <= 3.0
    assert r1["allocations"]["FL_01"] <= 2.0
    # 3. Preserve SOC and shifted energy
    assert r1["battery_reserve_respected"] is True
    assert r1["shifted_energy_conserved"] is True
    # 4. Determinism
    assert r1 == r2


# 7. Extreme Case A: No constraint -> minimal/no flex activation
def test_extreme_case_no_constraint(config, opt_config):
    envs_df = pd.read_csv("outputs/csv/dynamic_operating_envelopes.csv")
    plan_df = pd.read_csv("outputs/csv/coordination_plan.csv").copy()
    plan_df["required_up_kw"] = 0.0
    plan_df["required_down_kw"] = 0.0
    plan_df["risk_state"] = "NORMAL"
    nl_df = pd.read_csv("outputs/csv/net_load_forecast.csv")
    pv_df = pd.read_csv("outputs/csv/pv_forecast.csv")
    load_df = pd.read_csv("outputs/csv/load_forecast.csv")

    prob = OptimizationProblem(config, opt_config, envs_df, plan_df, nl_df, pv_df, load_df, participation_rate=0.70)
    solver = DispatchOptimizer(prob)
    res = solver.solve()
    assert res["success"] is True
    plan = generate_dispatch_plan(prob, res)
    # Under no constraint, no PV curtailment or battery discharge should occur
    summary = plan["optimization_summary"].iloc[0]
    assert np.isclose(summary["total_pv_curtailment_kwh"], 0.0, atol=1e-4)
    assert np.isclose(summary["battery_discharge_energy_kwh"], 0.0, atol=1e-4)


# 8. Extreme Case D: Constraint greater than available -> slack absorbs gap
def test_extreme_case_constraint_exceeds_available(config, opt_config):
    envs_df = pd.read_csv("outputs/csv/dynamic_operating_envelopes.csv")
    plan_df = pd.read_csv("outputs/csv/coordination_plan.csv").copy()
    # Impose extreme 150 kW requirement (exceeds all feeder DER flex)
    plan_df["required_up_kw"] = 150.0
    nl_df = pd.read_csv("outputs/csv/net_load_forecast.csv")
    pv_df = pd.read_csv("outputs/csv/pv_forecast.csv")
    load_df = pd.read_csv("outputs/csv/load_forecast.csv")

    prob = OptimizationProblem(config, opt_config, envs_df, plan_df, nl_df, pv_df, load_df, participation_rate=0.70)
    solver = DispatchOptimizer(prob)
    res = solver.solve()
    assert res["success"] is True
    plan = generate_dispatch_plan(prob, res)
    # Violations/slack must absorb the deficit
    summary = plan["optimization_summary"].iloc[0]
    assert summary["constraint_violation"] > 0.0


# 9. Extreme Case E: Battery at minimum SOC -> discharge unavailable
def test_extreme_case_battery_at_min_soc(config, opt_config):
    envs_df = pd.read_csv("outputs/csv/dynamic_operating_envelopes.csv")
    plan_df = pd.read_csv("outputs/csv/coordination_plan.csv")
    nl_df = pd.read_csv("outputs/csv/net_load_forecast.csv")
    pv_df = pd.read_csv("outputs/csv/pv_forecast.csv")
    load_df = pd.read_csv("outputs/csv/load_forecast.csv")

    # Initial SOC = 0.30 (floor)
    prob = OptimizationProblem(config, opt_config, envs_df, plan_df, nl_df, pv_df, load_df, initial_bess_soc=0.30)
    solver = DispatchOptimizer(prob)
    res = solver.solve()
    assert res["success"] is True
    plan = generate_dispatch_plan(prob, res)
    bat_df = plan["battery_schedule"]
    assert np.isclose(bat_df["discharge_kw"].sum(), 0.0, atol=1e-4)


# 10. Reproducibility test (Section 26)
def test_phase6_reproducibility(config, opt_config):
    envs_df = pd.read_csv("outputs/csv/dynamic_operating_envelopes.csv")
    plan_df = pd.read_csv("outputs/csv/coordination_plan.csv")
    nl_df = pd.read_csv("outputs/csv/net_load_forecast.csv")
    pv_df = pd.read_csv("outputs/csv/pv_forecast.csv")
    load_df = pd.read_csv("outputs/csv/load_forecast.csv")

    prob1 = OptimizationProblem(config, opt_config, envs_df, plan_df, nl_df, pv_df, load_df, participation_rate=0.70)
    res1 = DispatchOptimizer(prob1).solve()
    plan1 = generate_dispatch_plan(prob1, res1)

    prob2 = OptimizationProblem(config, opt_config, envs_df, plan_df, nl_df, pv_df, load_df, participation_rate=0.70)
    res2 = DispatchOptimizer(prob2).solve()
    plan2 = generate_dispatch_plan(prob2, res2)

    np.testing.assert_allclose(res1["objective_value"], res2["objective_value"], atol=1e-6)
    np.testing.assert_allclose(
        plan1["optimized_dispatch"]["optimized_kw"],
        plan2["optimized_dispatch"]["optimized_kw"],
        atol=1e-6
    )


# 11. Phase 1 baseline unchanged
def test_phase1_baseline_unchanged(config):
    net_cfg = config.get("network", {})
    assert net_cfg.get("transformer", {}).get("sn_mva") == 0.250
    assert net_cfg.get("nominal_lv_kv") == 0.415
    assert config.get("neighbourhood", {}).get("households") == 100
    assert config.get("battery", {}).get("energy_capacity_kwh") == 100.0
