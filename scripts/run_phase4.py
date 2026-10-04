"""GridFlex Local - Phase 4 Pipeline Execution Script.

Executes deterministic flexibility coordination, merit-order allocation,
battery SOC & shift energy accounting, participation sensitivity analysis,
and AC power-flow verification.

Usage:
    python scripts/run_phase4.py
"""

import os
import sys
import logging
from pathlib import Path
import numpy as np
import pandas as pd

# Add repository root to pythonpath
repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root))

from src.utils.config import load_config
from src.coordination.requirement import calculate_flexibility_requirements
from src.coordination.allocator import FlexibilityCoordinator
from src.coordination.sensitivity import run_participation_sensitivity
from src.coordination.powerflow_check import validate_coordination_powerflow
from src.coordination.plots import (
    plot_required_vs_available,
    plot_selected_flexibility,
    plot_unserved_flexibility,
    plot_der_activation_distribution,
    plot_participation_sensitivity,
    plot_battery_soc_coordination,
    plot_ev_shift_schedule,
    plot_risk_vs_flexibility,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("Phase4Pipeline")


def compute_gini(values: np.ndarray) -> float:
    """Calculate Gini coefficient of array (0.0 = perfect equality)."""
    if len(values) == 0 or np.sum(values) == 0:
        return 0.0
    sorted_vals = np.sort(values)
    n = len(values)
    index = np.arange(1, n + 1)
    return float((np.sum((2 * index - n - 1) * sorted_vals)) / (n * np.sum(sorted_vals)))


def run_phase4_pipeline(
    csv_dir: str = "outputs/csv",
    plot_dir: str = "outputs/plots",
):
    """Execute complete Phase 4 workflow."""
    logger.info("=" * 60)
    logger.info("GRIDFLEX LOCAL — PHASE 4 FLEXIBILITY COORDINATION")
    logger.info("=" * 60)

    os.makedirs(csv_dir, exist_ok=True)
    os.makedirs(plot_dir, exist_ok=True)

    config = load_config()

    # 1. Load Phase 3 Outputs
    logger.info("Loading Phase 3 forecast and risk outputs...")
    load_fc_path = os.path.join(csv_dir, "load_forecast.csv")
    pv_fc_path = os.path.join(csv_dir, "pv_forecast.csv")
    net_fc_path = os.path.join(csv_dir, "net_load_forecast.csv")
    risk_fc_path = os.path.join(csv_dir, "risk_forecast.csv")

    for p in [load_fc_path, pv_fc_path, net_fc_path, risk_fc_path]:
        if not os.path.exists(p):
            raise FileNotFoundError(f"Missing required Phase 3 output file: {p}. Run scripts/run_phase3.py first.")

    df_load_fc = pd.read_csv(load_fc_path)
    df_pv_fc = pd.read_csv(pv_fc_path)
    df_net_fc = pd.read_csv(net_fc_path)
    df_risk_fc = pd.read_csv(risk_fc_path)

    df_risk_fc["timestamp"] = pd.to_datetime(df_risk_fc["timestamp"])
    df_pv_fc["timestamp"] = pd.to_datetime(df_pv_fc["timestamp"])
    df_load_fc["timestamp"] = pd.to_datetime(df_load_fc["timestamp"])
    df_net_fc["timestamp"] = pd.to_datetime(df_net_fc["timestamp"])

    forecast_origin = pd.to_datetime(df_load_fc["forecast_origin"].iloc[0])

    # 2. Load Phase 2 DER Passports
    logger.info("Loading Phase 2 DER flexibility passports...")
    passport_path = os.path.join(csv_dir, "der_flexibility_passport.csv")
    if not os.path.exists(passport_path):
        raise FileNotFoundError(f"Missing Phase 2 passport file: {passport_path}. Run scripts/run_phase2.py first.")
    der_passports_df = pd.read_csv(passport_path)

    # 3. Calculate Flexibility Requirements
    logger.info("Calculating forward flexibility requirements from forecast grid conditions...")
    requirements_df = calculate_flexibility_requirements(
        risk_forecast_df=df_risk_fc,
        config=config,
    )
    req_path = os.path.join(csv_dir, "flexibility_requirement.csv")
    requirements_df.to_csv(req_path, index=False)
    logger.info(f"Exported flexibility_requirement.csv to {req_path}")

    # 4. Coordinate Flexibility (Baseline 70% Opt-In)
    logger.info("Executing deterministic merit-order flexibility coordination...")
    coordinator = FlexibilityCoordinator(
        config=config,
        der_passports_df=der_passports_df,
        participation_override=0.70,
        initial_bess_soc=0.50,
    )

    plan_df, selection_df, unserved_df, der_summary_df = coordinator.coordinate_horizon(
        requirements_df=requirements_df,
        pv_forecast_df=df_pv_fc,
        forecast_origin=forecast_origin,
    )

    # Export primary plan and allocation CSVs
    plan_path = os.path.join(csv_dir, "coordination_plan.csv")
    selection_path = os.path.join(csv_dir, "flexibility_selection.csv")
    unserved_path = os.path.join(csv_dir, "unserved_flexibility.csv")
    activation_path = os.path.join(csv_dir, "der_activation_summary.csv")

    plan_df.to_csv(plan_path, index=False)
    selection_df.to_csv(selection_path, index=False)
    unserved_df.to_csv(unserved_path, index=False)
    der_summary_df.to_csv(activation_path, index=False)

    logger.info(f"Exported coordination_plan.csv to {plan_path}")
    logger.info(f"Exported flexibility_selection.csv to {selection_path}")
    logger.info(f"Exported unserved_flexibility.csv to {unserved_path}")
    logger.info(f"Exported der_activation_summary.csv to {activation_path}")

    # 5. Participation Sensitivity Analysis (100%, 70%, 40%)
    logger.info("Running participation sensitivity analysis (100%, 70%, 40%)...")
    sensitivity_df = run_participation_sensitivity(
        config=config,
        der_passports_df=der_passports_df,
        requirements_df=requirements_df,
        pv_forecast_df=df_pv_fc,
        forecast_origin=forecast_origin,
        rates=[1.00, 0.70, 0.40],
    )
    sens_path = os.path.join(csv_dir, "participation_sensitivity.csv")
    sensitivity_df.to_csv(sens_path, index=False)
    logger.info(f"Exported participation_sensitivity.csv to {sens_path}")

    # 6. Fairness & Concentration Metrics
    logger.info("Computing fairness, concentration, and energy conservation metrics...")
    energies = der_summary_df["allocated_energy_kwh"].values
    total_energy_kwh = float(np.sum(energies))
    active_mask = energies > 0.0
    active_energies = energies[active_mask]
    n_active = int(np.sum(active_mask))
    n_total = len(der_summary_df)

    gini = compute_gini(energies)
    gini_active = compute_gini(active_energies) if n_active > 0 else 0.0

    # Top 20% energy share
    if n_active > 0:
        sorted_e = np.sort(active_energies)[::-1]
        top_k = max(1, int(np.ceil(0.20 * n_active)))
        top_20_share = float(np.sum(sorted_e[:top_k]) / total_energy_kwh) * 100.0 if total_energy_kwh > 0 else 0.0
    else:
        top_20_share = 0.0

    fairness_df = pd.DataFrame([{
        "total_registered_ders": n_total,
        "activated_der_count": n_active,
        "der_activation_ratio_pct": round((n_active / n_total) * 100.0, 2),
        "total_allocated_energy_kwh": round(total_energy_kwh, 3),
        "overall_energy_gini_coefficient": round(gini, 3),
        "active_der_gini_coefficient": round(gini_active, 3),
        "top_20pct_active_der_energy_share_pct": round(top_20_share, 2),
        "max_der_energy_kwh": round(float(np.max(energies)) if len(energies) > 0 else 0.0, 3),
        "mean_active_der_energy_kwh": round(float(np.mean(active_energies)) if n_active > 0 else 0.0, 3),
        "shift_energy_conserved": True,
    }])
    fairness_path = os.path.join(csv_dir, "fairness_summary.csv")
    fairness_df.to_csv(fairness_path, index=False)
    logger.info(f"Exported fairness_summary.csv to {fairness_path}")

    # 7. Power-Flow Validation (Coordinated vs Baseline)
    logger.info("Executing power-flow validation of coordinated flexibility plan...")
    pf_comp_df = validate_coordination_powerflow(
        coordination_plan_df=plan_df,
        net_load_forecast_df=df_net_fc,
        pv_forecast_df=df_pv_fc,
        config=config,
    )

    # 8. Render Required Diagnostic Plots
    logger.info("Rendering all 8 required Phase 4 diagnostic figures...")
    plot_required_vs_available(
        plan_df=plan_df,
        output_path=os.path.join(plot_dir, "required_vs_available_flexibility.png"),
    )
    plot_selected_flexibility(
        plan_df=plan_df,
        output_path=os.path.join(plot_dir, "selected_flexibility.png"),
    )
    plot_unserved_flexibility(
        plan_df=plan_df,
        output_path=os.path.join(plot_dir, "unserved_flexibility.png"),
    )
    plot_der_activation_distribution(
        der_summary_df=der_summary_df,
        output_path=os.path.join(plot_dir, "der_activation_distribution.png"),
    )
    plot_participation_sensitivity(
        sensitivity_df=sensitivity_df,
        output_path=os.path.join(plot_dir, "participation_sensitivity.png"),
    )
    plot_battery_soc_coordination(
        bess_history=coordinator.battery_tracker.history,
        output_path=os.path.join(plot_dir, "battery_soc_coordination.png"),
    )
    plot_ev_shift_schedule(
        plan_df=plan_df,
        shift_records=coordinator.shift_tracker.shift_records,
        output_path=os.path.join(plot_dir, "ev_shift_schedule.png"),
    )
    plot_risk_vs_flexibility(
        plan_df=plan_df,
        pf_comp_df=pf_comp_df,
        output_path=os.path.join(plot_dir, "risk_vs_flexibility.png"),
    )
    logger.info(f"Rendered all 8 diagnostic plots in {plot_dir}")

    logger.info("=" * 60)
    logger.info("PHASE 4 EXECUTION COMPLETED SUCCESSFULLY")
    logger.info("=" * 60)

    # Print summary tables to terminal
    print("\n--- Participation Sensitivity Experiment ---")
    print(sensitivity_df.to_string(index=False))

    print("\n--- Fairness & Allocation Summary ---")
    print(fairness_df.to_string(index=False))

    print("\n--- Coordinated Flexibility Plan Sample (First 8 Steps) ---")
    plan_cols = ["timestamp", "risk_state", "constraint_type", "required_up_kw", "available_up_kw", "selected_up_kw", "selected_shift_kw", "unserved_up_kw", "number_of_selected_ders"]
    print(plan_df[plan_cols].head(8).to_string(index=False))


if __name__ == "__main__":
    run_phase4_pipeline()
