"""Phase 6 Pipeline Execution Script: Optimization + Dispatch Planning.

Optimizes controllable DER flexibility within Phase 5 Dynamic Operating Envelopes,
generates detailed schedules for all assets, and visualizes grid impact.
"""

import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from typing import Dict, Any
import yaml
import pandas as pd
import numpy as np

from src.utils.config import load_config
from src.optimization.problem import OptimizationProblem
from src.optimization.solver import DispatchOptimizer
from src.optimization.dispatcher import generate_dispatch_plan
from src.optimization.scenarios import run_participation_sensitivities
from src.optimization.plots import generate_all_optimization_plots


def load_optimization_config(path: str = "config/optimization.yaml") -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def run_phase6(
    config_path: str = "config/neighbourhood_config.yaml",
    opt_config_path: str = "config/optimization.yaml",
) -> Dict[str, Any]:
    """Execute complete Phase 6 pipeline."""
    print("=" * 60)
    print("GRIDFLEX LOCAL — PHASE 6: OPTIMIZATION + DISPATCH PLANNING")
    print("=" * 60)

    config = load_config(config_path)
    opt_config = load_optimization_config(opt_config_path)

    csv_dir = Path("outputs/csv")
    plot_dir = Path("outputs/plots")
    csv_dir.mkdir(parents=True, exist_ok=True)
    plot_dir.mkdir(parents=True, exist_ok=True)

    # 1. Load inputs from Phases 1-5
    print("\n[Step 1/5] Loading inputs from Phases 1-5...")
    envs_path = csv_dir / "dynamic_operating_envelopes.csv"
    plan_path = csv_dir / "coordination_plan.csv"
    nl_path = csv_dir / "net_load_forecast.csv"
    pv_path = csv_dir / "pv_forecast.csv"
    load_path = csv_dir / "load_forecast.csv"

    for p in [envs_path, plan_path, nl_path, pv_path, load_path]:
        if not p.exists():
            raise FileNotFoundError(f"Missing required input artifact: {p}")

    envelopes_df = pd.read_csv(envs_path)
    coordination_plan_df = pd.read_csv(plan_path)
    net_load_forecast_df = pd.read_csv(nl_path)
    pv_forecast_df = pd.read_csv(pv_path)
    load_forecast_df = pd.read_csv(load_path)

    print(f" Loaded {len(envelopes_df)} envelope entries and {len(coordination_plan_df)} horizon intervals.")

    # 2. Formulate and solve default 70% participation problem
    print("\n[Step 2/5] Formulating mathematical programming model (Default 70% Participation)...")
    problem = OptimizationProblem(
        config=config,
        opt_config=opt_config,
        envelopes_df=envelopes_df,
        coordination_plan_df=coordination_plan_df,
        net_load_forecast_df=net_load_forecast_df,
        pv_forecast_df=pv_forecast_df,
        load_forecast_df=load_forecast_df,
        initial_bess_soc=0.50,
        participation_rate=0.70,
    )
    solver = DispatchOptimizer(problem)
    res = solver.solve()
    print(f" Solver executed. Status: {res['solver_status']} | Objective: {res['objective_value']:.2f}")

    if not res["success"]:
        print(" Optimization unsuccessful! Writing infeasibility report.")
        return res

    # 3. Generate dispatch schedules and metrics
    print("\n[Step 3/5] Extracting individual DER schedules and compiling dispatch plan...")
    plan_dict = generate_dispatch_plan(problem, res)

    # Print summary metrics
    s = plan_dict["optimization_summary"].iloc[0]
    print(f" - Peak Substation Import: {s['peak_grid_import_kw']} kW (Total: {s['total_grid_import_kwh']} kWh)")
    print(f" - Battery Energy Discharged: {s['battery_discharge_energy_kwh']} kWh (Charged: {s['battery_charge_energy_kwh']} kWh)")
    print(f" - EV Energy Deferred/Shifted: {s['ev_shifted_energy_kwh']} kWh")
    print(f" - Rooftop PV Curtailed: {s['total_pv_curtailment_kwh']} kWh")
    print(f" - Total Active Coordinated DERs: {int(s['number_of_active_ders'])}")
    print(f" - Post-Optimization Constraint Violations: {s['constraint_violation']}")

    # 4. Evaluate participation sensitivities
    print("\n[Step 4/5] Evaluating scenario sensitivities (100%, 70%, 40% participation)...")
    sens_df = run_participation_sensitivities(
        config=config,
        opt_config=opt_config,
        envelopes_df=envelopes_df,
        coordination_plan_df=coordination_plan_df,
        net_load_forecast_df=net_load_forecast_df,
        pv_forecast_df=pv_forecast_df,
        load_forecast_df=load_forecast_df,
        rates=[1.00, 0.70, 0.40],
    )
    for _, r in sens_df.iterrows():
        print(f"   Rate: {r['participation_rate']} -> Peak Import: {r['peak_grid_import_kw']} kW | Obj: {r['objective_value']} | Status: {r['solver_status']}")

    # 5. Export CSVs and Generate Plots
    print("\n[Step 5/5] Exporting all 9 required CSVs and 12 diagnostic figures...")
    plan_dict["optimized_dispatch"].to_csv(csv_dir / "optimized_dispatch.csv", index=False)
    plan_dict["optimization_summary"].to_csv(csv_dir / "optimization_summary.csv", index=False)
    plan_dict["constraint_metrics"].to_csv(csv_dir / "constraint_metrics.csv", index=False)
    plan_dict["der_schedule"].to_csv(csv_dir / "der_schedule.csv", index=False)
    plan_dict["battery_schedule"].to_csv(csv_dir / "battery_schedule.csv", index=False)
    plan_dict["ev_schedule"].to_csv(csv_dir / "ev_schedule.csv", index=False)
    plan_dict["pv_schedule"].to_csv(csv_dir / "pv_schedule.csv", index=False)
    plan_dict["flexible_load_schedule"].to_csv(csv_dir / "flexible_load_schedule.csv", index=False)
    plan_dict["optimization_comparison"].to_csv(csv_dir / "optimization_comparison.csv", index=False)
    sens_df.to_csv(csv_dir / "participation_scenarios_summary.csv", index=False)

    generate_all_optimization_plots(
        dispatch_df=plan_dict["optimized_dispatch"],
        summary_df=plan_dict["optimization_summary"],
        constraint_df=plan_dict["constraint_metrics"],
        battery_df=plan_dict["battery_schedule"],
        ev_df=plan_dict["ev_schedule"],
        pv_df=plan_dict["pv_schedule"],
        fl_df=plan_dict["flexible_load_schedule"],
        comparison_df=plan_dict["optimization_comparison"],
        net_load_fc_df=net_load_forecast_df,
        output_dir=plot_dir,
    )
    print(" Exported all artifacts successfully.")

    print("\n" + "=" * 60)
    print("PHASE 6 OPTIMIZATION COMPLETED SUCCESSFULLY")
    print("=" * 60)

    return plan_dict


if __name__ == "__main__":
    run_phase6()
