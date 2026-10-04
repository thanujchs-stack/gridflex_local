"""Forecasting and Risk Prediction Visualizations for GridFlex Local.

Generates high-quality diagnostic figures for Phase 3:
1. actual_vs_forecast_load.png
2. actual_vs_forecast_pv.png
3. actual_vs_forecast_net_load.png
4. forecast_uncertainty.png
5. forecast_error.png
6. flexibility_forecast.png
7. risk_timeline.png
"""

import os
from typing import Dict, Any, Optional
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates


def setup_style():
    """Apply consistent clean technical styling for figures."""
    plt.rcParams["font.sans-serif"] = "DejaVu Sans"
    plt.rcParams["axes.edgecolor"] = "#cccccc"
    plt.rcParams["axes.linewidth"] = 0.8
    plt.rcParams["grid.color"] = "#eeeeee"
    plt.rcParams["grid.linestyle"] = "--"


def plot_actual_vs_forecast(
    df: pd.DataFrame,
    target_name: str,
    output_path: str,
    unit: str = "kW",
):
    """Plot actual vs point forecast trajectories."""
    setup_style()
    fig, ax = plt.subplots(figsize=(10, 4.5), dpi=150)

    t = pd.to_datetime(df["timestamp"])
    ax.plot(t, df["actual"], label="Actual", color="#1f77b4", linewidth=2.0, marker="o", markersize=4)
    ax.plot(t, df["forecast"], label="ML Forecast (HistGB)", color="#ff7f0e", linewidth=2.0, linestyle="--", marker="s", markersize=4)

    ax.set_title(f"GridFlex Local — Actual vs Forecast: {target_name.upper()} (16-Step / 4-Hour Horizon)", fontsize=12, fontweight="bold", pad=12)
    ax.set_xlabel("Timestamp", fontsize=10)
    ax.set_ylabel(f"Power ({unit})", fontsize=10)
    ax.grid(True)
    ax.legend(loc="upper right", framealpha=0.9)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    fig.autofmt_xdate()

    plt.tight_layout()
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path)
    plt.close(fig)


def plot_forecast_uncertainty(
    df: pd.DataFrame,
    output_path: str,
    target_name: str = "Net Load",
    unit: str = "kW",
):
    """Plot forecast with 90% confidence / prediction interval band."""
    setup_style()
    fig, ax = plt.subplots(figsize=(10, 4.5), dpi=150)

    t = pd.to_datetime(df["timestamp"])
    ax.plot(t, df["actual"], label="Actual", color="#111111", linewidth=1.8, marker="o", markersize=4)
    ax.plot(t, df["forecast"], label="Median Forecast", color="#0052cc", linewidth=2.2)

    ax.fill_between(
        t,
        df["lower_bound"],
        df["upper_bound"],
        color="#0052cc",
        alpha=0.20,
        label="90% Prediction Interval [LB, UB]",
    )

    ax.set_title(f"GridFlex Local — Forecast Uncertainty: {target_name} (Prediction Intervals)", fontsize=12, fontweight="bold", pad=12)
    ax.set_xlabel("Forecast Horizon Timestamp", fontsize=10)
    ax.set_ylabel(f"Power ({unit})", fontsize=10)
    ax.grid(True)
    ax.legend(loc="upper right", framealpha=0.9)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    fig.autofmt_xdate()

    plt.tight_layout()
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path)
    plt.close(fig)


def plot_forecast_error(
    metrics_df: pd.DataFrame,
    output_path: str,
):
    """Plot error metric comparison across models and horizons."""
    setup_style()
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.5), dpi=150)

    # Filter out overall summary row, keep numeric horizons
    sub = metrics_df[metrics_df["horizon_minutes"].isin(["15", "60", "120", "240"])].copy()
    sub["h_num"] = sub["horizon_minutes"].astype(int)
    sub = sub.sort_values("h_num")

    colors = {"Persistence": "#7f7f7f", "MovingAverage": "#2ca02c", "HistGradientBoosting": "#d62728"}

    for model in sub["model"].unique():
        m_data = sub[(sub["model"] == model) & (sub["period_scope"] == "all")]
        if not m_data.empty:
            c = colors.get(model, "#333333")
            ax1.plot(m_data["h_num"], m_data["MAE"], marker="o", label=model, color=c, linewidth=1.8)
            ax2.plot(m_data["h_num"], m_data["RMSE"], marker="s", label=model, color=c, linewidth=1.8)

    ax1.set_title("Mean Absolute Error (MAE) vs Horizon", fontsize=11, fontweight="bold")
    ax1.set_xlabel("Horizon (Minutes)", fontsize=10)
    ax1.set_ylabel("MAE (kW)", fontsize=10)
    ax1.grid(True)
    ax1.legend()

    ax2.set_title("Root Mean Squared Error (RMSE) vs Horizon", fontsize=11, fontweight="bold")
    ax2.set_xlabel("Horizon (Minutes)", fontsize=10)
    ax2.set_ylabel("RMSE (kW)", fontsize=10)
    ax2.grid(True)
    ax2.legend()

    plt.suptitle("GridFlex Local — Forecast Error Scaling with Horizon", fontsize=12, fontweight="bold")
    plt.tight_layout()
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path)
    plt.close(fig)


def plot_flexibility_forecast(
    flex_df: pd.DataFrame,
    output_path: str,
):
    """Plot projected available forward flexibility breakdown across 16 steps."""
    setup_style()
    fig, ax = plt.subplots(figsize=(10, 4.5), dpi=150)

    t = pd.to_datetime(flex_df["timestamp"])
    ax.plot(t, flex_df["total_up_available_kw"], label="Available UP Flexibility (BESS Discharge)", color="#2ca02c", linewidth=2.2, marker="^")
    ax.plot(t, flex_df["total_down_available_kw"], label="Available DOWN Flexibility (PV Curtail + BESS Charge + EV)", color="#d62728", linewidth=2.2, marker="v")
    ax.plot(t, flex_df["total_shiftable_available_kw"], label="Shiftable Demand (Flexible Loads)", color="#ff7f0e", linewidth=1.8, linestyle="--")

    ax.set_title("GridFlex Local — 4-Hour Forward Available Flexibility Forecast (Phase 2 Passports)", fontsize=12, fontweight="bold", pad=12)
    ax.set_xlabel("Forecast Timestamp", fontsize=10)
    ax.set_ylabel("Available Capacity (kW)", fontsize=10)
    ax.grid(True)
    ax.legend(loc="upper right", framealpha=0.9)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    fig.autofmt_xdate()

    plt.tight_layout()
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path)
    plt.close(fig)


def plot_risk_timeline(
    risk_df: pd.DataFrame,
    output_path: str,
):
    """Plot risk score trajectory, operational states, and transformer loading."""
    setup_style()
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6.0), dpi=150, sharex=True)

    t = pd.to_datetime(risk_df["timestamp"])

    # Top: Risk Score and Operational States
    ax1.plot(t, risk_df["risk_score"], label="Risk Score (0-100)", color="#8b0000", linewidth=2.2, marker="o", markersize=4)
    ax1.axhline(25.0, color="#2ca02c", linestyle=":", label="NORMAL / WATCH boundary (25)")
    ax1.axhline(50.0, color="#ff7f0e", linestyle=":", label="WATCH / CONSTRAINED boundary (50)")
    ax1.axhline(75.0, color="#d62728", linestyle=":", label="CONSTRAINED / CRITICAL boundary (75)")

    state_colors = {"NORMAL": "#2ca02c", "WATCH": "#e6a100", "CONSTRAINED": "#ff7f0e", "CRITICAL": "#d62728"}
    for idx, row in risk_df.iterrows():
        st = row["operational_state"]
        c = state_colors.get(st, "#333333")
        ax1.scatter(row["timestamp"], row["risk_score"], color=c, s=60, zorder=5)

    ax1.set_title("GridFlex Local — Local Operational Risk Timeline (16-Step Forward)", fontsize=12, fontweight="bold")
    ax1.set_ylabel("Risk Score", fontsize=10)
    ax1.set_ylim(-5, 105)
    ax1.grid(True)
    ax1.legend(loc="upper right", fontsize=8, framealpha=0.9)

    # Bottom: Transformer Loading & Voltage Margin
    ax2.plot(t, risk_df["trafo_loading_pct"], label="Transformer Loading (%)", color="#1f77b4", linewidth=2.0)
    ax2.axhline(80.0, color="#ff7f0e", linestyle="--", label="Warning Threshold (80%)")
    ax2.axhline(100.0, color="#d62728", linestyle="--", label="Critical Threshold (100%)")

    ax2.set_xlabel("Forecast Timestamp", fontsize=10)
    ax2.set_ylabel("Trafo Loading (%)", fontsize=10)
    ax2.grid(True)
    ax2.legend(loc="upper right", fontsize=8, framealpha=0.9)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    fig.autofmt_xdate()

    plt.tight_layout()
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path)
    plt.close(fig)
