"""Visualization Suite for the 5 DER Problem Demonstration Scenarios.

Generates the 9 required figures matching Section 15:
1. voltage_baseline_vs_gridflex.png
2. transformer_loading_baseline_vs_gridflex.png
3. line_loading_baseline_vs_gridflex.png
4. reverse_power_flow.png
5. pv_forecast_uncertainty.png
6. flexibility_availability.png
7. battery_soc.png
8. ev_shift.png
9. scenario_comparison.png
"""

from pathlib import Path
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd
import numpy as np


STYLE_BASE = "#94a3b8"       # Slate gray for baseline
STYLE_GRIDFLEX = "#0284c7"   # Cyan/Sky blue for GridFlex
STYLE_ALERT = "#ef4444"      # Red alert / limit
STYLE_WARN = "#f59e0b"       # Amber warning
STYLE_TEAL = "#0d9488"       # Vibrant teal
STYLE_PURPLE = "#8b5cf6"     # Purple


def setup_style():
    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Segoe UI", "DejaVu Sans", "Arial"],
        "axes.edgecolor": "#cbd5e1",
        "axes.linewidth": 1.0,
        "grid.color": "#e2e8f0",
        "grid.linestyle": "--",
        "grid.alpha": 0.7,
        "figure.facecolor": "#ffffff",
        "axes.facecolor": "#fafafa",
    })


def generate_all_der_problem_plots(
    ts_df: pd.DataFrame,
    scenario_summary_df: pd.DataFrame,
    passport_df: pd.DataFrame,
    uncertainty_df: pd.DataFrame,
    reserve_df: pd.DataFrame,
    ev_df: pd.DataFrame,
    bess_df: pd.DataFrame,
    output_dir: Path,
):
    """Generate all 9 required publication-grade plots."""
    setup_style()
    output_dir.mkdir(parents=True, exist_ok=True)

    ts_df = ts_df.copy()
    ts_df["timestamp"] = pd.to_datetime(ts_df["timestamp"])

    # -------------------------------------------------------------------------
    # 1. voltage_baseline_vs_gridflex.png (Scenario 1 & 5 focus)
    # -------------------------------------------------------------------------
    s1_df = ts_df[ts_df["scenario"] == "SCENARIO_1_HIGH_PV_LOW_DEMAND"]
    s1_base = s1_df[s1_df["case"] == "BASELINE"].sort_values("timestamp")
    s1_opt = s1_df[s1_df["case"] == "GRIDFLEX"].sort_values("timestamp")

    fig, ax = plt.subplots(figsize=(10, 5), dpi=300)
    ax.plot(s1_base["timestamp"], s1_base["max_bus_voltage_pu"], label="Baseline Max Voltage (Solar Noon Rise)", color=STYLE_ALERT, lw=2.2, marker="o", ms=4)
    ax.plot(s1_opt["timestamp"], s1_opt["max_bus_voltage_pu"], label="GridFlex Max Voltage (Mitigated)", color=STYLE_GRIDFLEX, lw=2.5, marker="s", ms=4)
    ax.axhline(1.050, color=STYLE_WARN, linestyle="--", lw=1.8, label="1.050 pu Statutory Voltage Ceiling")
    ax.axhline(1.000, color="#64748b", linestyle=":", lw=1.0, alpha=0.6)
    ax.set_ylabel("Maximum Bus Voltage (p.u.)", fontsize=11, fontweight="bold")
    ax.set_title("Problem 1: Feeder Voltage Rise Mitigation via Coordinated Inverter Envelopes", fontsize=13, fontweight="bold", pad=12)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax.grid(True)
    ax.legend(frameon=True, facecolor="#ffffff", edgecolor="#e2e8f0")
    plt.tight_layout()
    fig.savefig(output_dir / "voltage_baseline_vs_gridflex.png", dpi=300)
    plt.close(fig)

    # -------------------------------------------------------------------------
    # 2. transformer_loading_baseline_vs_gridflex.png (Scenario 2 focus)
    # -------------------------------------------------------------------------
    s2_df = ts_df[ts_df["scenario"] == "SCENARIO_2_EV_PEAK_CONGESTION"]
    s2_base = s2_df[s2_df["case"] == "BASELINE"].sort_values("timestamp")
    s2_opt = s2_df[s2_df["case"] == "GRIDFLEX"].sort_values("timestamp")

    fig, ax = plt.subplots(figsize=(10, 5), dpi=300)
    ax.plot(s2_base["timestamp"], s2_base["transformer_loading_percent"], label="Baseline Transformer Loading", color=STYLE_BASE, lw=2.2, marker="o", ms=4)
    ax.plot(s2_opt["timestamp"], s2_opt["transformer_loading_percent"], label="GridFlex Optimized Loading", color=STYLE_GRIDFLEX, lw=2.5, marker="s", ms=4)
    ax.axhline(80.0, color=STYLE_WARN, linestyle=":", lw=1.8, label="80% Warning Limit")
    ax.axhline(100.0, color=STYLE_ALERT, linestyle="--", lw=1.8, label="100% Thermal Rating")
    ax.set_ylabel("Transformer Loading (%)", fontsize=11, fontweight="bold")
    ax.set_title("Problem 3: Distribution Transformer Congestion Relief (Evening EV & Load Peak)", fontsize=13, fontweight="bold", pad=12)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax.grid(True)
    ax.legend(frameon=True, facecolor="#ffffff", edgecolor="#e2e8f0")
    plt.tight_layout()
    fig.savefig(output_dir / "transformer_loading_baseline_vs_gridflex.png", dpi=300)
    plt.close(fig)

    # -------------------------------------------------------------------------
    # 3. line_loading_baseline_vs_gridflex.png (Scenario 2 focus)
    # -------------------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(10, 5), dpi=300)
    ax.plot(s2_base["timestamp"], s2_base["max_line_loading_percent"], label="Baseline Line Loading (EV Trunk)", color=STYLE_BASE, lw=2.2, marker="o", ms=4)
    ax.plot(s2_opt["timestamp"], s2_opt["max_line_loading_percent"], label="GridFlex Line Loading (Decongested)", color=STYLE_TEAL, lw=2.5, marker="^", ms=4)
    ax.axhline(80.0, color=STYLE_WARN, linestyle=":", lw=1.8, label="80% Feeder Warning")
    ax.axhline(100.0, color=STYLE_ALERT, linestyle="--", lw=1.8, label="100% Thermal Limit")
    ax.set_ylabel("Maximum Line Loading (%)", fontsize=11, fontweight="bold")
    ax.set_title("Problem 3: Feeder Line Congestion Relief via Spatial EV Demand Throttling", fontsize=13, fontweight="bold", pad=12)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax.grid(True)
    ax.legend(frameon=True, facecolor="#ffffff", edgecolor="#e2e8f0")
    plt.tight_layout()
    fig.savefig(output_dir / "line_loading_baseline_vs_gridflex.png", dpi=300)
    plt.close(fig)

    # -------------------------------------------------------------------------
    # 4. reverse_power_flow.png (Scenario 1 focus)
    # -------------------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(10, 5), dpi=300)
    ax.plot(s1_base["timestamp"], s1_base["reverse_power_kw"], label="Baseline Reverse Flow (Substation Export)", color=STYLE_ALERT, lw=2.2, marker="o", ms=4)
    ax.plot(s1_opt["timestamp"], s1_opt["reverse_power_kw"], label="GridFlex Mitigated Reverse Flow", color=STYLE_PURPLE, lw=2.5, marker="D", ms=4)
    ax.axhline(100.0, color=STYLE_WARN, linestyle="--", lw=1.8, label="100 kW Substation Reverse Flow Limit")
    ax.set_ylabel("Reverse Power Flow at Transformer (kW)", fontsize=11, fontweight="bold")
    ax.set_title("Problem 2: Reverse Power Flow Suppression via BESS Absorptive Charging", fontsize=13, fontweight="bold", pad=12)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax.grid(True)
    ax.legend(frameon=True, facecolor="#ffffff", edgecolor="#e2e8f0")
    plt.tight_layout()
    fig.savefig(output_dir / "reverse_power_flow.png", dpi=300)
    plt.close(fig)

    # -------------------------------------------------------------------------
    # 5. pv_forecast_uncertainty.png (Problem 4 focus)
    # -------------------------------------------------------------------------
    unc_df = uncertainty_df.copy()
    unc_df["timestamp"] = pd.to_datetime(unc_df["timestamp"])
    res_df = reserve_df.copy()
    res_df["timestamp"] = pd.to_datetime(res_df["timestamp"])

    fig, ax = plt.subplots(figsize=(10, 5), dpi=300)
    ax.plot(unc_df["timestamp"], unc_df["forecast_mean"], label="Net Load Forecast Mean", color="#2563eb", lw=2.2)
    ax.fill_between(
        unc_df["timestamp"],
        unc_df["forecast_lower"],
        unc_df["forecast_upper"],
        color="#93c5fd",
        alpha=0.4,
        label="90% Prediction Interval (Uncertainty)",
    )
    ax.plot(res_df["timestamp"], res_df["required_reserve_kw"], label="Forecast-Aware Required Reserve (kW)", color=STYLE_WARN, lw=2.0, linestyle="--")
    ax.set_ylabel("Active Power / Reserve (kW)", fontsize=11, fontweight="bold")
    ax.set_title("Problem 4: Solar Intermittency Forecast Uncertainty & Dynamic Flexibility Reserve", fontsize=13, fontweight="bold", pad=12)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax.grid(True)
    ax.legend(frameon=True, facecolor="#ffffff", edgecolor="#e2e8f0")
    plt.tight_layout()
    fig.savefig(output_dir / "pv_forecast_uncertainty.png", dpi=300)
    plt.close(fig)

    # -------------------------------------------------------------------------
    # 6. flexibility_availability.png (Problem 5: 4-tier hierarchy)
    # -------------------------------------------------------------------------
    # Aggregate across timesteps
    p_steps = passport_df.copy()
    p_steps["timestamp"] = pd.to_datetime(p_steps["timestamp"])
    agg_flex = p_steps.groupby("timestamp").agg({
        "technical_flexibility_up_kw": "sum",
        "available_flexibility_up_kw": "sum",
        "selectable_flexibility_up_kw": "sum",
        "dispatched_flexibility_kw": "sum",
    }).reset_index()

    fig, ax = plt.subplots(figsize=(10, 5), dpi=300)
    ax.plot(agg_flex["timestamp"], agg_flex["technical_flexibility_up_kw"], label="1. Technical Flexibility (Nameplate)", color="#94a3b8", lw=2.0, linestyle=":")
    ax.plot(agg_flex["timestamp"], agg_flex["available_flexibility_up_kw"], label="2. Available Flexibility (Derated by Participation/SOC)", color=STYLE_WARN, lw=2.2)
    ax.plot(agg_flex["timestamp"], agg_flex["selectable_flexibility_up_kw"], label="3. Selectable Flexibility (Within Envelopes)", color=STYLE_TEAL, lw=2.2)
    ax.plot(agg_flex["timestamp"], agg_flex["dispatched_flexibility_kw"], label="4. Dispatched Flexibility (Phase 6 LP)", color=STYLE_GRIDFLEX, lw=2.5, marker="o", ms=4)
    ax.set_ylabel("Fleet Aggregate Flexibility (kW)", fontsize=11, fontweight="bold")
    ax.set_title("Problem 5: True DER Visibility — The 4-Tier Flexibility Hierarchy", fontsize=13, fontweight="bold", pad=12)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax.grid(True)
    ax.legend(frameon=True, facecolor="#ffffff", edgecolor="#e2e8f0")
    plt.tight_layout()
    fig.savefig(output_dir / "flexibility_availability.png", dpi=300)
    plt.close(fig)

    # -------------------------------------------------------------------------
    # 7. battery_soc.png
    # -------------------------------------------------------------------------
    b_df = bess_df.copy()
    b_df["timestamp"] = pd.to_datetime(b_df["timestamp"])

    fig, ax = plt.subplots(figsize=(10, 5), dpi=300)
    ax.plot(b_df["timestamp"], b_df["soc"] * 100.0, label="Community Battery SOC (%)", color=STYLE_TEAL, lw=2.5, marker="s", ms=4)
    ax.axhline(30.0, color=STYLE_WARN, linestyle="--", lw=1.8, label="30% Emergency Reserve Floor")
    ax.axhline(20.0, color=STYLE_ALERT, linestyle=":", lw=1.5, label="20% Minimum Technical Limit")
    ax.axhline(90.0, color=STYLE_ALERT, linestyle=":", lw=1.5, label="90% Maximum Battery Limit")
    ax.set_ylabel("State of Charge (%)", fontsize=11, fontweight="bold")
    ax.set_title("Community BESS Energy Trajectory: Reserve Floor & Cycling Control", fontsize=13, fontweight="bold", pad=12)
    ax.set_ylim(15.0, 95.0)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax.grid(True)
    ax.legend(frameon=True, facecolor="#ffffff", edgecolor="#e2e8f0")
    plt.tight_layout()
    fig.savefig(output_dir / "battery_soc.png", dpi=300)
    plt.close(fig)

    # -------------------------------------------------------------------------
    # 8. ev_shift.png
    # -------------------------------------------------------------------------
    e_df = ev_df.copy()
    e_df["timestamp"] = pd.to_datetime(e_df["timestamp"])
    ev_hourly = e_df.groupby("timestamp").agg({
        "throttled_kw": "sum",
        "optimized_charge_kw": "sum",
    }).reset_index()

    fig, ax = plt.subplots(figsize=(10, 5), dpi=300)
    ax.bar(ev_hourly["timestamp"], ev_hourly["throttled_kw"], width=0.008, label="Throttled EV Demand (Congestion Relief)", color="#f43f5e", alpha=0.85)
    ax.plot(ev_hourly["timestamp"], ev_hourly["throttled_kw"], color="#be123c", lw=1.8, marker="o", ms=4)
    ax.set_ylabel("Aggregated Throttled Power (kW)", fontsize=11, fontweight="bold")
    ax.set_title("EV Demand Throttling: Peak Congestion Shifting Out of Evening Hours", fontsize=13, fontweight="bold", pad=12)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax.grid(axis="y")
    ax.legend(frameon=True, facecolor="#ffffff", edgecolor="#e2e8f0")
    plt.tight_layout()
    fig.savefig(output_dir / "ev_shift.png", dpi=300)
    plt.close(fig)

    # -------------------------------------------------------------------------
    # 9. scenario_comparison.png (Cross-Scenario Scorecard)
    # -------------------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(12, 6), dpi=300)
    scen_labels = [
        "1. High PV\nLow Demand",
        "2. Evening EV\nCongestion",
        "3. Cloud\nIntermittency",
        "4. Low\nParticipation",
        "5. Combined\nDiurnal Stress",
    ]
    base_trafo = scenario_summary_df["baseline_peak_trafo_pct"].tolist()
    opt_trafo = scenario_summary_df["gridflex_peak_trafo_pct"].tolist()

    x = np.arange(len(scen_labels))
    width = 0.35
    ax.bar(x - width / 2, base_trafo, width, label="Baseline Peak Trafo Loading (%)", color=STYLE_BASE, edgecolor="#334155")
    ax.bar(x + width / 2, opt_trafo, width, label="GridFlex Peak Trafo Loading (%)", color=STYLE_GRIDFLEX, edgecolor="#334155")
    ax.axhline(80.0, color=STYLE_WARN, linestyle="--", lw=1.8, label="80% Transformer Warning Threshold")
    ax.set_xticks(x)
    ax.set_xticklabels(scen_labels, fontweight="bold", fontsize=10)
    ax.set_ylabel("Peak Transformer Loading (%)", fontsize=11, fontweight="bold")
    ax.set_title("Cross-Scenario Performance: GridFlex Local Constraint Mitigation across 5 DER Stress Regimes", fontsize=13, fontweight="bold", pad=14)
    ax.set_ylim(0, max(base_trafo + opt_trafo) * 1.25)
    ax.grid(axis="y")
    ax.legend(frameon=True, facecolor="#ffffff", edgecolor="#e2e8f0")
    plt.tight_layout()
    fig.savefig(output_dir / "scenario_comparison.png", dpi=300)
    plt.close(fig)
