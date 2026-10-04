"""GridFlex Local - Phase 3 Pipeline Execution Script.

Executes monitoring, multi-step time-series forecasting, benchmark comparison,
forward flexibility forecasting, and local physical grid risk evaluation.

Usage:
    python scripts/run_phase3.py
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
from src.data.load_dataset import load_forecasting_dataset
from src.forecasting.features import generate_forecasting_features, get_feature_columns
from src.forecasting.split import chronological_train_val_test_split, verify_no_leakage
from src.forecasting.baselines import PersistenceForecaster, MovingAverageForecaster
from src.forecasting.models import MultiStepHistGradientBoostingForecaster
from src.forecasting.metrics import calculate_forecast_metrics
from src.forecasting.flexibility_forecaster import forecast_available_flexibility
from src.risk.powerflow_evaluator import evaluate_forecast_powerflow
from src.risk.risk_engine import LocalRiskEngine
from src.forecasting.plots import (
    plot_actual_vs_forecast,
    plot_forecast_uncertainty,
    plot_forecast_error,
    plot_flexibility_forecast,
    plot_risk_timeline,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("Phase3Pipeline")


def run_phase3_pipeline(
    sample_weeks: int = 12,
    random_seed: int = 42,
    output_csv_dir: str = "outputs/csv",
    output_plot_dir: str = "outputs/plots",
):
    """Run complete Phase 3 workflow."""
    logger.info("=" * 60)
    logger.info("GRIDFLEX LOCAL — PHASE 3 PIPELINE EXECUTION")
    logger.info("=" * 60)

    os.makedirs(output_csv_dir, exist_ok=True)
    os.makedirs(output_plot_dir, exist_ok=True)

    config = load_config()

    # 1. Load Phase 2.5 Processed Forecasting Data
    logger.info("Loading Phase 2.5 standardized dataset (mode: REAL_PUBLIC)...")
    data_bundle = load_forecasting_dataset(mode="REAL_PUBLIC")
    timestamps = data_bundle["timestamps"]
    load_kw = data_bundle["neighbourhood_load_kw"]
    pv_kw = data_bundle["neighbourhood_pv_kw"]
    solar_df = data_bundle["solar_irradiance"]

    raw_df = pd.DataFrame({
        "timestamp": timestamps,
        "total_load_kw": load_kw,
        "total_pv_kw": pv_kw,
        "ghi_wm2": solar_df["ghi_wm2"],
        "temp_c": solar_df["temp_c"],
    })

    # Select representative multi-week window for fast, high-quality prototype training
    # 12 weeks = 8,064 timesteps at 15-min resolution
    n_sample_steps = min(len(raw_df), sample_weeks * 7 * 96)
    dataset_df = raw_df.iloc[:n_sample_steps].copy().reset_index(drop=True)
    logger.info(f"Loaded {len(dataset_df)} timesteps ({dataset_df['timestamp'].min()} to {dataset_df['timestamp'].max()})")

    # 2. Feature Engineering
    logger.info("Engineering features with strict past-only constraints (no leakage)...")
    # Features for load
    df_load_feats = generate_forecasting_features(
        df=dataset_df,
        target_col="total_load_kw",
        solar_col="total_pv_kw",
        irradiance_col="ghi_wm2",
        include_grid_features=True,
    )
    # Features for PV
    df_pv_feats = generate_forecasting_features(
        df=dataset_df,
        target_col="total_pv_kw",
        solar_col="total_pv_kw",
        irradiance_col="ghi_wm2",
        include_grid_features=False,
    )

    feature_cols_load = get_feature_columns(df_load_feats, target_col="total_load_kw")
    feature_cols_pv = get_feature_columns(df_pv_feats, target_col="total_pv_kw")
    logger.info(f"Generated {len(feature_cols_load)} load features and {len(feature_cols_pv)} PV features.")

    # Export sample feature matrix
    sample_feat_export = df_load_feats.head(500)
    feat_export_path = os.path.join(output_csv_dir, "forecast_features.csv")
    sample_feat_export.to_csv(feat_export_path, index=False)
    logger.info(f"Exported feature samples to {feat_export_path}")

    # 3. Chronological Train/Val/Test Split (70/15/15)
    logger.info("Executing chronological train / validation / test splits...")
    tr_l, val_l, te_l = chronological_train_val_test_split(df_load_feats, train_ratio=0.70, val_ratio=0.15, test_ratio=0.15)
    tr_p, val_p, te_p = chronological_train_val_test_split(df_pv_feats, train_ratio=0.70, val_ratio=0.15, test_ratio=0.15)

    is_valid, msg = verify_no_leakage(tr_l, val_l, te_l)
    logger.info(f"Chronological split verification: {msg}")

    # 4. Train Baselines & ML Models
    # --- A. Load Forecasters ---
    logger.info("Training Load Forecasters (Persistence, Moving Average, HistGradientBoosting)...")
    pers_load = PersistenceForecaster(target_name="load", is_solar=False)
    pers_load.fit(tr_l["total_load_kw"])

    ma_load = MovingAverageForecaster(target_name="load", window=4, is_solar=False)
    ma_load.fit(tr_l["total_load_kw"])

    ml_load = MultiStepHistGradientBoostingForecaster(
        target_name="load",
        horizon_steps=16,
        is_solar=False,
        random_state=random_seed,
        max_iter=80,
    )
    ml_load.fit(tr_l, val_l, target_col="total_load_kw", feature_cols=feature_cols_load)

    # --- B. Solar PV Forecasters ---
    logger.info("Training Solar PV Forecasters (with nighttime physical bounds)...")
    pers_pv = PersistenceForecaster(target_name="pv", is_solar=True)
    pers_pv.fit(tr_p["total_pv_kw"])

    ma_pv = MovingAverageForecaster(target_name="pv", window=4, is_solar=True)
    ma_pv.fit(tr_p["total_pv_kw"])

    ml_pv = MultiStepHistGradientBoostingForecaster(
        target_name="pv",
        horizon_steps=16,
        is_solar=True,
        random_state=random_seed,
        max_iter=80,
    )
    ml_pv.fit(tr_p, val_p, target_col="total_pv_kw", feature_cols=feature_cols_pv)

    # 5. Generate Multi-Step Forecasts on Test Set
    logger.info("Generating 16-step forward forecasts across test set...")
    # Evaluate across test set with 16-step stride
    ml_load_fcs = ml_load.forecast_series(te_l, target_col="total_load_kw", stride=16)
    ml_pv_fcs = ml_pv.forecast_series(te_p, target_col="total_pv_kw", stride=16)

    # Generate baseline forecasts for same origin points
    pers_load_list, ma_load_list = [], []
    pers_pv_list, ma_pv_list = [], []

    origins = ml_load_fcs["forecast_origin"].unique()
    for o_ts in origins:
        idx_match = te_l[te_l["timestamp"] == o_ts].index
        if len(idx_match) > 0:
            pos = te_l.index.get_loc(idx_match[0])
            if pos + 16 < len(te_l):
                act_l = te_l.iloc[pos + 1:pos + 17]["total_load_kw"]
                act_p = te_p.iloc[pos + 1:pos + 17]["total_pv_kw"]

                pers_load_list.append(pers_load.forecast(te_l, pos, "total_load_kw", 16, 15, act_l))
                ma_load_list.append(ma_load.forecast(te_l, pos, "total_load_kw", 16, 15, act_l))
                pers_pv_list.append(pers_pv.forecast(te_p, pos, "total_pv_kw", 16, 15, act_p))
                ma_pv_list.append(ma_pv.forecast(te_p, pos, "total_pv_kw", 16, 15, act_p))

    all_load_eval = pd.concat([ml_load_fcs] + pers_load_list + ma_load_list, ignore_index=True)
    all_pv_eval = pd.concat([ml_pv_fcs] + pers_pv_list + ma_pv_list, ignore_index=True)

    # Compute Net Load Forecasts: net = load - pv
    logger.info("Computing net load forecasts and compound uncertainty intervals...")
    # Representative 16-step test origin
    rep_origin = origins[len(origins) // 2]
    rep_load_fc = ml_load_fcs[ml_load_fcs["forecast_origin"] == rep_origin].copy().reset_index(drop=True)
    rep_pv_fc = ml_pv_fcs[ml_pv_fcs["forecast_origin"] == rep_origin].copy().reset_index(drop=True)

    rep_net_fc = pd.DataFrame({
        "timestamp": rep_load_fc["timestamp"],
        "forecast_origin": rep_origin,
        "horizon_minutes": rep_load_fc["horizon_minutes"],
        "actual": rep_load_fc["actual"] - rep_pv_fc["actual"],
        "forecast": rep_load_fc["forecast"] - rep_pv_fc["forecast"],
        "lower_bound": rep_load_fc["lower_bound"] - rep_pv_fc["upper_bound"],
        "upper_bound": rep_load_fc["upper_bound"] - rep_pv_fc["lower_bound"],
        "model": "HistGradientBoosting",
        "target": "net_load",
    })

    # Export required Forecast CSVs
    rep_load_fc.to_csv(os.path.join(output_csv_dir, "load_forecast.csv"), index=False)
    rep_pv_fc.to_csv(os.path.join(output_csv_dir, "pv_forecast.csv"), index=False)
    rep_net_fc.to_csv(os.path.join(output_csv_dir, "net_load_forecast.csv"), index=False)
    logger.info(f"Exported load_forecast.csv, pv_forecast.csv, net_load_forecast.csv to {output_csv_dir}")

    # 6. Evaluation Metrics
    logger.info("Evaluating forecasting metrics (MAE, RMSE, sMAPE)...")
    m_load = calculate_forecast_metrics(all_load_eval, target_name="neighbourhood_load", is_solar=False)
    m_pv = calculate_forecast_metrics(all_pv_eval, target_name="neighbourhood_pv", is_solar=True)

    # Net load comparison
    net_all_list = []
    for model in ["HistGradientBoosting", "Persistence", "MovingAverage"]:
        sub_l = all_load_eval[all_load_eval["model"] == model]
        sub_p = all_pv_eval[all_pv_eval["model"] == model]
        merged_m = pd.merge(sub_l, sub_p, on=["timestamp", "forecast_origin", "horizon_minutes"], suffixes=("_l", "_p"))
        net_df = pd.DataFrame({
            "timestamp": merged_m["timestamp"],
            "forecast_origin": merged_m["forecast_origin"],
            "horizon_minutes": merged_m["horizon_minutes"],
            "actual": merged_m["actual_l"] - merged_m["actual_p"],
            "forecast": merged_m["forecast_l"] - merged_m["forecast_p"],
            "model": model,
            "target": "neighbourhood_net_load",
        })
        net_all_list.append(net_df)

    all_net_eval = pd.concat(net_all_list, ignore_index=True)
    m_net = calculate_forecast_metrics(all_net_eval, target_name="neighbourhood_net_load", is_solar=False)

    metrics_df = pd.concat([m_load, m_pv, m_net], ignore_index=True)
    metrics_path = os.path.join(output_csv_dir, "forecast_metrics.csv")
    metrics_df.to_csv(metrics_path, index=False)
    logger.info(f"Exported forecast_metrics.csv to {metrics_path}")

    # 7. Flexibility Forecast (Phase 2 Passports)
    logger.info("Projecting forward available flexibility for 16 future steps...")
    flex_df = forecast_available_flexibility(
        forecast_timestamps=rep_load_fc["timestamp"].tolist(),
        pv_forecast_kw=rep_pv_fc["forecast"].values,
        config=config,
        bess_current_soc=0.50,
    )
    flex_path = os.path.join(output_csv_dir, "flexibility_forecast.csv")
    flex_df.to_csv(flex_path, index=False)
    logger.info(f"Exported flexibility_forecast.csv to {flex_path}")

    # 8. Power Flow Simulation & Local Grid Risk Engine
    logger.info("Running AC power flow simulation on 16-step forward forecast trajectory...")
    pf_results = evaluate_forecast_powerflow(
        forecast_df=rep_load_fc,
        pv_forecast_df=rep_pv_fc,
        config=config,
    )

    logger.info("Evaluating local physical grid operational risk states...")
    risk_engine = LocalRiskEngine(config=config)
    risk_df = risk_engine.evaluate_trajectory(
        powerflow_df=pf_results,
        net_load_forecast_df=rep_net_fc,
        flexibility_df=flex_df,
    )
    risk_path = os.path.join(output_csv_dir, "risk_forecast.csv")
    risk_df.to_csv(risk_path, index=False)
    logger.info(f"Exported risk_forecast.csv to {risk_path}")

    # 9. Diagnostic Figures
    logger.info("Rendering diagnostic visualization figures...")
    plot_actual_vs_forecast(
        df=rep_load_fc,
        target_name="Neighbourhood Load",
        output_path=os.path.join(output_plot_dir, "actual_vs_forecast_load.png"),
    )
    plot_actual_vs_forecast(
        df=rep_pv_fc,
        target_name="Neighbourhood PV",
        output_path=os.path.join(output_plot_dir, "actual_vs_forecast_pv.png"),
    )
    plot_actual_vs_forecast(
        df=rep_net_fc,
        target_name="Neighbourhood Net Load",
        output_path=os.path.join(output_plot_dir, "actual_vs_forecast_net_load.png"),
    )
    plot_forecast_uncertainty(
        df=rep_net_fc,
        output_path=os.path.join(output_plot_dir, "forecast_uncertainty.png"),
        target_name="Neighbourhood Net Load",
    )
    plot_forecast_error(
        metrics_df=m_load,
        output_path=os.path.join(output_plot_dir, "forecast_error.png"),
    )
    plot_flexibility_forecast(
        flex_df=flex_df,
        output_path=os.path.join(output_plot_dir, "flexibility_forecast.png"),
    )
    plot_risk_timeline(
        risk_df=risk_df,
        output_path=os.path.join(output_plot_dir, "risk_timeline.png"),
    )
    logger.info(f"Rendered all 7 diagnostic figures in {output_plot_dir}")

    logger.info("=" * 60)
    logger.info("PHASE 3 EXECUTION COMPLETED SUCCESSFULLY")
    logger.info("=" * 60)

    # Print summary highlights
    print("\n--- Phase 3 Key Metric Summary (Overall Horizons) ---")
    summary_print = metrics_df[metrics_df["horizon_minutes"] == "all (15-240m)"][["target", "model", "period_scope", "MAE", "RMSE", "sMAPE"]]
    print(summary_print.to_string(index=False))

    print("\n--- 16-Step Forward Risk Assessment Timeline ---")
    risk_summary = risk_df[["timestamp", "horizon_minutes", "operational_state", "risk_score", "trafo_loading_pct", "min_vm_pu", "primary_constraint", "mitigable_by_flexibility"]]
    print(risk_summary.to_string(index=False))


if __name__ == "__main__":
    run_phase3_pipeline()
