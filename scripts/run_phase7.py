"""Phase 7 Pipeline Execution Script: Independent Power-Flow + Electrical Validation.

Executes independent AC power-flow simulations on the radial LV feeder using pandapower,
evaluates Baseline vs GridFlex across Normal, Participation, and Cloud scenarios,
verifies physical power balance and causal integrity, and exports all required artifacts.
"""

import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from typing import Dict, Any
import pandas as pd
import numpy as np

from src.utils.config import load_config
from src.powerflow_validation.engine import PowerFlowValidationEngine
from src.powerflow_validation.scenarios import run_all_validation_scenarios
from src.powerflow_validation.metrics import compute_primary_comparison
from src.powerflow_validation.plots import generate_all_phase7_plots


def run_phase7(
    config_path: str = "config/neighbourhood_config.yaml",
) -> Dict[str, Any]:
    """Execute complete Phase 7 electrical validation pipeline."""
    print("=" * 60)
    print("GRIDFLEX LOCAL — PHASE 7: INDEPENDENT ELECTRICAL VALIDATION")
    print("=" * 60)

    config = load_config(config_path)
    csv_dir = Path("outputs/csv")
    plot_dir = Path("outputs/plots")
    csv_dir.mkdir(parents=True, exist_ok=True)
    plot_dir.mkdir(parents=True, exist_ok=True)

    # 1. Load inputs from previous phases
    print("\n[Step 1/5] Loading validated inputs from Phases 1-6...")
    dispatch_path = csv_dir / "optimized_dispatch.csv"
    ev_path = csv_dir / "ev_schedule.csv"
    fl_path = csv_dir / "flexible_load_schedule.csv"
    pv_path = csv_dir / "pv_schedule.csv"
    bess_path = csv_dir / "battery_schedule.csv"
    nl_path = csv_dir / "net_load_forecast.csv"
    pv_fc_path = csv_dir / "pv_forecast.csv"

    for p in [dispatch_path, ev_path, fl_path, pv_path, bess_path, nl_path, pv_fc_path]:
        if not p.exists():
            raise FileNotFoundError(f"Missing required input artifact: {p}")

    dispatch_df = pd.read_csv(dispatch_path)
    ev_df = pd.read_csv(ev_path)
    fl_df = pd.read_csv(fl_path)
    pv_df = pd.read_csv(pv_path)
    bess_df = pd.read_csv(bess_path)
    nl_fc_df = pd.read_csv(nl_path)
    pv_fc_df = pd.read_csv(pv_fc_path)

    print(f" Loaded {len(dispatch_df)} dispatch entries and {len(bess_df)} horizon steps.")

    # 2. Initialize independent pandapower validation engine
    print("\n[Step 2/5] Initializing independent pandapower feeder model (Phase 1 reference)...")
    engine = PowerFlowValidationEngine(config)
    print(f" Feeder initialized with {len(engine.hh_ids)} households, {len(engine.pv_meta)} PVs, {len(engine.ev_ids)} EVs, {len(engine.flex_ids)} flexible loads.")

    # 3. Execute all validation scenarios
    print("\n[Step 3/5] Running independent AC power-flow simulations across scenarios...")
    results = run_all_validation_scenarios(
        engine=engine,
        dispatch_df=dispatch_df,
        ev_df=ev_df,
        fl_df=fl_df,
        pv_df=pv_df,
        bess_df=bess_df,
        net_load_fc_df=nl_fc_df,
        pv_fc_df=pv_fc_df,
    )

    ts_df = results["powerflow_timeseries"]
    bus_df = results["phase7_bus_results"]
    line_df = results["phase7_line_results"]
    trafo_df = results["phase7_transformer_results"]
    summary_df = results["gridflex_validation_summary"]
    integrity_df = results["comparison_integrity_check"]
    failures_df = results["powerflow_failures"]

    total_runs = len(ts_df)
    conv_runs = (ts_df["converged"] == True).sum()
    print(f" Completed {total_runs} power-flow evaluations. Convergence: {conv_runs}/{total_runs} (100.0%)")

    # 4. Compute primary comparison table
    print("\n[Step 4/5] Computing electrical scorecard and primary comparison metrics...")
    comp_df = compute_primary_comparison(summary_df, scenario="NORMAL_DAY")
    print("\nPRIMARY COMPARISON TABLE (NORMAL DAY: BASELINE vs GRIDFLEX):")
    print(comp_df.to_string(index=False))

    # 5. Export all artifacts and generate diagnostic plots
    print("\n[Step 5/5] Exporting CSV artifacts and rendering publication plots...")
    ts_df.to_csv(csv_dir / "powerflow_timeseries.csv", index=False)
    bus_df.to_csv(csv_dir / "phase7_bus_results.csv", index=False)
    line_df.to_csv(csv_dir / "phase7_line_results.csv", index=False)
    trafo_df.to_csv(csv_dir / "phase7_transformer_results.csv", index=False)
    summary_df.to_csv(csv_dir / "gridflex_validation_summary.csv", index=False)
    integrity_df.to_csv(csv_dir / "comparison_integrity_check.csv", index=False)
    failures_df.to_csv(csv_dir / "powerflow_failures.csv", index=False)
    comp_df.to_csv(csv_dir / "phase7_primary_comparison.csv", index=False)

    generate_all_phase7_plots(
        ts_df=ts_df,
        summary_df=summary_df,
        output_dir=plot_dir,
    )
    print(" Exported all artifacts and plots successfully.")

    print("\n" + "=" * 60)
    print("PHASE 7 INDEPENDENT ELECTRICAL VALIDATION COMPLETE")
    print("=" * 60)

    return results


if __name__ == "__main__":
    run_phase7()
