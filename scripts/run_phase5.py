"""Phase 5 Pipeline Execution Script: Dynamic Operating Envelopes (DOEs).

Translates forecasts, local grid risks, and flexibility coordination plans into
time-varying DER operating envelopes and validates their grid impact via AC power flow.
"""

import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from typing import Dict, Any
import pandas as pd
import numpy as np

from src.utils.config import load_config
from src.envelopes.calculator import DynamicOperatingEnvelopeCalculator
from src.envelopes.events import EnvelopeEventDetector
from src.envelopes.metrics import calculate_envelope_metrics
from src.envelopes.powerflow_validator import evaluate_envelope_powerflow
from src.envelopes.plots import generate_all_envelope_plots


def run_phase5(config_path: str = "config/neighbourhood_config.yaml") -> Dict[str, Any]:
    """Execute complete Phase 5 pipeline and export all required outputs."""
    print("=" * 60)
    print("GRIDFLEX LOCAL — PHASE 5: DYNAMIC OPERATING ENVELOPES")
    print("=" * 60)

    config = load_config(config_path)
    csv_dir = Path("outputs/csv")
    plot_dir = Path("outputs/plots")
    csv_dir.mkdir(parents=True, exist_ok=True)
    plot_dir.mkdir(parents=True, exist_ok=True)

    # 1. Load inputs from Phases 1, 2, 3, and 4
    print("\n[Step 1/6] Loading prerequisite inputs from Phases 1-4...")
    passport_path = csv_dir / "der_flexibility_passport.csv"
    registry_path = csv_dir / "der_registry.csv"
    plan_path = csv_dir / "coordination_plan.csv"
    sel_path = csv_dir / "flexibility_selection.csv"
    risk_path = csv_dir / "risk_forecast.csv"
    pv_fc_path = csv_dir / "pv_forecast.csv"
    load_fc_path = csv_dir / "load_forecast.csv"
    nl_fc_path = csv_dir / "net_load_forecast.csv"

    for p in [passport_path, registry_path, plan_path, sel_path, risk_path, pv_fc_path, load_fc_path, nl_fc_path]:
        if not p.exists():
            raise FileNotFoundError(f"Missing required input artifact: {p}")

    passports_df = pd.read_csv(passport_path)
    registry_df = pd.read_csv(registry_path)
    coordination_plan_df = pd.read_csv(plan_path)
    flexibility_selection_df = pd.read_csv(sel_path)
    risk_forecast_df = pd.read_csv(risk_path)
    pv_forecast_df = pd.read_csv(pv_fc_path)
    load_forecast_df = pd.read_csv(load_fc_path)
    net_load_forecast_df = pd.read_csv(nl_fc_path)

    print(f" Loaded {len(passports_df)} DER passports across {len(coordination_plan_df)} forecast timesteps.")

    # 2. Calculate Dynamic Operating Envelopes
    print("\n[Step 2/6] Calculating Dynamic Operating Envelopes across horizon...")
    calculator = DynamicOperatingEnvelopeCalculator(
        config=config,
        der_passports_df=passports_df,
        der_registry_df=registry_df,
        initial_bess_soc=0.50,
    )
    all_envs_df, pv_envs_df, bat_envs_df, ev_envs_df, fl_envs_df = calculator.compute_envelopes(
        coordination_plan_df=coordination_plan_df,
        flexibility_selection_df=flexibility_selection_df,
        risk_forecast_df=risk_forecast_df,
        pv_forecast_df=pv_forecast_df,
        load_forecast_df=load_forecast_df,
    )
    print(f" Generated {len(all_envs_df)} total envelope entries across 84 DERs.")

    # 3. Detect Envelope Transition Events
    print("\n[Step 3/6] Detecting envelope state transitions and limit adjustments...")
    detector = EnvelopeEventDetector()
    events_df = detector.detect_events(all_envs_df)
    print(f" Recorded {len(events_df)} envelope transition events.")

    # 4. Calculate Envelope Quality Metrics
    print("\n[Step 4/6] Computing envelope quality metrics...")
    summary_metrics_df = calculate_envelope_metrics(all_envs_df, events_df, timestep_hours=0.25)
    for _, row in summary_metrics_df.iterrows():
        print(f" - {row['metric_name']}: {row['metric_value']} {row['unit']}")

    # 5. Pandapower AC Power-Flow Validation (Case A vs Case B)
    print("\n[Step 5/6] Simulating pandapower AC power flow (Case A Static vs Case B Dynamic)...")
    validation_df = evaluate_envelope_powerflow(
        envelopes_df=all_envs_df,
        net_load_forecast_df=net_load_forecast_df,
        pv_forecast_df=pv_forecast_df,
        config=config,
    )
    print(f" Power flow completed: {len(validation_df)} timesteps converged (Baseline: {validation_df['powerflow_converged_baseline'].all()}, Dynamic: {validation_df['powerflow_converged_dynamic'].all()}).")
    max_red = validation_df["loading_reduction_pct"].max()
    max_v_imp = validation_df["voltage_improvement_pu"].max()
    print(f" Peak transformer loading reduction: {max_red:.2f}% | Max voltage improvement: {max_v_imp:.4f} p.u.")

    # 6. Export CSVs and Generate Visualizations
    print("\n[Step 6/6] Exporting required CSVs and generating publication plots...")
    all_envs_df.to_csv(csv_dir / "dynamic_operating_envelopes.csv", index=False)
    pv_envs_df.to_csv(csv_dir / "pv_envelopes.csv", index=False)
    bat_envs_df.to_csv(csv_dir / "battery_envelopes.csv", index=False)
    ev_envs_df.to_csv(csv_dir / "ev_envelopes.csv", index=False)
    fl_envs_df.to_csv(csv_dir / "flexible_load_envelopes.csv", index=False)
    events_df.to_csv(csv_dir / "envelope_events.csv", index=False)
    summary_metrics_df.to_csv(csv_dir / "envelope_summary.csv", index=False)
    validation_df.to_csv(csv_dir / "envelope_validation.csv", index=False)

    generate_all_envelope_plots(
        envelopes_df=all_envs_df,
        pv_envelopes_df=pv_envs_df,
        battery_envelopes_df=bat_envs_df,
        ev_envelopes_df=ev_envs_df,
        fl_envelopes_df=fl_envs_df,
        validation_df=validation_df,
        output_dir=plot_dir,
    )
    print(" Exported all 8 CSVs and 9 diagnostic figures.")

    print("\n" + "=" * 60)
    print("PHASE 5 PIPELINE COMPLETED SUCCESSFULLY")
    print("=" * 60)

    return {
        "all_envelopes_df": all_envs_df,
        "pv_envelopes_df": pv_envs_df,
        "battery_envelopes_df": bat_envs_df,
        "ev_envelopes_df": ev_envs_df,
        "fl_envelopes_df": fl_envs_df,
        "events_df": events_df,
        "summary_metrics_df": summary_metrics_df,
        "validation_df": validation_df,
    }


if __name__ == "__main__":
    run_phase5()
