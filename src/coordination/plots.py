"""Visualization tools for GridFlex Local Phase 4 Flexibility Coordination.

Generates the 8 required diagnostic figures:
1. required_vs_available_flexibility.png
2. selected_flexibility.png
3. unserved_flexibility.png
4. der_activation_distribution.png
5. participation_sensitivity.png
6. battery_soc_coordination.png
7. ev_shift_schedule.png
8. risk_vs_flexibility.png
"""

import os
from typing import Dict, Any, List, Optional
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates


def setup_style():
    """Apply consistent styling."""
    plt.rcParams["font.sans-serif"] = "DejaVu Sans"
    plt.rcParams["axes.edgecolor"] = "#cccccc"
    plt.rcParams["axes.linewidth"] = 0.8
    plt.rcParams["grid.color"] = "#eeeeee"
    plt.rcParams["grid.linestyle"] = "--"


def plot_required_vs_available(
    plan_df: pd.DataFrame,
    output_path: str,
):
    """Plot required flexibility vs available forward flexibility."""
    setup_style()
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6.0), dpi=150, sharex=True)

    t = pd.to_datetime(plan_df["timestamp"])

    # UP Flexibility
    ax1.plot(t, plan_df["available_up_kw"], label="Available UP Flexibility (BESS Discharge)", color="#2ca02c", linewidth=2.0)
    ax1.plot(t, plan_df["required_up_kw"], label="Required UP Flexibility (Feeder Relief)", color="#d62728", linewidth=2.0, linestyle="--", marker="o", markersize=4)
    ax1.set_title("GridFlex Local — Required vs Available UP Flexibility", fontsize=11, fontweight="bold")
    ax1.set_ylabel("Power (kW)", fontsize=9)
    ax1.grid(True)
    ax1.legend(loc="upper right", fontsize=8)

    # DOWN Flexibility
    ax2.plot(t, plan_df["available_down_kw"], label="Available DOWN Flexibility (PV Curtail + BESS Charge)", color="#1f77b4", linewidth=2.0)
    ax2.plot(t, plan_df["required_down_kw"], label="Required DOWN Flexibility (Overvoltage / Export)", color="#ff7f0e", linewidth=2.0, linestyle="--", marker="s", markersize=4)
    ax2.set_title("GridFlex Local — Required vs Available DOWN Flexibility", fontsize=11, fontweight="bold")
    ax2.set_xlabel("Forecast Timestamp", fontsize=10)
    ax2.set_ylabel("Power (kW)", fontsize=9)
    ax2.grid(True)
    ax2.legend(loc="upper right", fontsize=8)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    fig.autofmt_xdate()

    plt.tight_layout()
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path)
    plt.close(fig)


def plot_selected_flexibility(
    plan_df: pd.DataFrame,
    output_path: str,
):
    """Plot allocated flexibility across timesteps by direction and type."""
    setup_style()
    fig, ax = plt.subplots(figsize=(10, 4.5), dpi=150)

    t = pd.to_datetime(plan_df["timestamp"])
    width = 0.006

    ax.bar(t, plan_df["selected_up_kw"], width=width, label="Selected UP Flexibility (kW)", color="#2ca02c", alpha=0.85)
    ax.bar(t, plan_df["selected_down_kw"], width=width, label="Selected DOWN Flexibility (kW)", color="#1f77b4", alpha=0.85, bottom=plan_df["selected_up_kw"])
    ax.plot(t, plan_df["selected_shift_kw"], label="Shiftable Portion (EV / Flexible Loads)", color="#ff7f0e", linewidth=2.0, marker="^")

    ax.set_title("GridFlex Local — Coordinated Flexibility Allocation Plan (16-Step Forward)", fontsize=12, fontweight="bold", pad=12)
    ax.set_xlabel("Forecast Timestamp", fontsize=10)
    ax.set_ylabel("Selected Capacity (kW)", fontsize=10)
    ax.grid(True)
    ax.legend(loc="upper right", framealpha=0.9)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    fig.autofmt_xdate()

    plt.tight_layout()
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path)
    plt.close(fig)


def plot_unserved_flexibility(
    plan_df: pd.DataFrame,
    output_path: str,
):
    """Plot satisfied vs unserved flexibility requirements."""
    setup_style()
    fig, ax = plt.subplots(figsize=(10, 4.5), dpi=150)

    t = pd.to_datetime(plan_df["timestamp"])
    total_req = plan_df["required_up_kw"] + plan_df["required_down_kw"]
    total_sel = plan_df["selected_up_kw"] + plan_df["selected_down_kw"]
    total_unserved = plan_df["unserved_up_kw"] + plan_df["unserved_down_kw"]

    ax.plot(t, total_req, label="Total Required Flexibility (kW)", color="#111111", linewidth=2.0, marker="o", markersize=4)
    ax.plot(t, total_sel, label="Selected / Satisfied Flexibility (kW)", color="#2ca02c", linewidth=2.0, linestyle="--", marker="s", markersize=4)
    ax.bar(t, total_unserved, width=0.006, label="Unserved Flexibility Deficit (kW)", color="#d62728", alpha=0.7)

    ax.set_title("GridFlex Local — Flexibility Satisfaction & Unserved Deficit Analysis", fontsize=12, fontweight="bold", pad=12)
    ax.set_xlabel("Forecast Timestamp", fontsize=10)
    ax.set_ylabel("Power (kW)", fontsize=10)
    ax.grid(True)
    ax.legend(loc="upper right", framealpha=0.9)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    fig.autofmt_xdate()

    plt.tight_layout()
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path)
    plt.close(fig)


def plot_der_activation_distribution(
    der_summary_df: pd.DataFrame,
    output_path: str,
):
    """Plot distribution of DER activations to assess fairness and concentration."""
    setup_style()
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.5), dpi=150)

    # Active DERs only
    active_df = der_summary_df[der_summary_df["activation_count"] > 0].copy()
    if active_df.empty:
        active_df = der_summary_df.head(10).copy()

    # Sort by allocated energy
    active_df = active_df.sort_values("allocated_energy_kwh", ascending=False).head(15)

    ax1.barh(active_df["der_id"], active_df["allocated_energy_kwh"], color="#1f77b4", edgecolor="#0e4370")
    ax1.set_title("Top-15 DER Allocated Energy (kWh)", fontsize=11, fontweight="bold")
    ax1.set_xlabel("Energy Delivered (kWh)", fontsize=9)
    ax1.invert_yaxis()
    ax1.grid(True)

    # By DER Category
    cat_summary = der_summary_df.groupby("der_type")["allocated_energy_kwh"].sum()
    ax2.pie(
        cat_summary.values if cat_summary.sum() > 0 else [1],
        labels=cat_summary.index if cat_summary.sum() > 0 else ["No Allocation"],
        autopct="%1.1f%%" if cat_summary.sum() > 0 else None,
        colors=["#2ca02c", "#ff7f0e", "#1f77b4", "#d62728"],
        startangle=140,
    )
    ax2.set_title("Energy Allocation Share by DER Type", fontsize=11, fontweight="bold")

    plt.suptitle("GridFlex Local — DER Flexibility Utilization & Fairness Distribution", fontsize=12, fontweight="bold")
    plt.tight_layout()
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path)
    plt.close(fig)


def plot_participation_sensitivity(
    sensitivity_df: pd.DataFrame,
    output_path: str,
):
    """Plot available vs selected flexibility across participation rates (100%, 70%, 40%)."""
    setup_style()
    fig, ax = plt.subplots(figsize=(8.5, 4.5), dpi=150)

    x = np.arange(len(sensitivity_df))
    width = 0.35

    ax.bar(x - width/2, sensitivity_df["total_available_kw"], width, label="Total Available Capacity (kW)", color="#1f77b4")
    ax.bar(x + width/2, sensitivity_df["total_selected_kw"], width, label="Total Selected Capacity (kW)", color="#2ca02c")

    ax.set_title("GridFlex Local — Participation Sensitivity Analysis (100%, 70%, 40%)", fontsize=12, fontweight="bold", pad=12)
    ax.set_xticks(x)
    ax.set_xticklabels(sensitivity_df["scenario"], fontsize=10)
    ax.set_ylabel("Flexibility Volume (kW)", fontsize=10)
    ax.grid(True)
    ax.legend()

    plt.tight_layout()
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path)
    plt.close(fig)


def plot_battery_soc_coordination(
    bess_history: List[Dict[str, Any]],
    output_path: str,
):
    """Plot battery state of charge (SOC) evolution under coordinated plan."""
    setup_style()
    fig, ax = plt.subplots(figsize=(9, 4.2), dpi=150)

    socs = [h["soc"] * 100.0 for h in bess_history]
    steps = list(range(len(socs)))

    ax.plot(steps, socs, label="Community BESS SOC (%)", color="#0052cc", linewidth=2.2, marker="o", markersize=4)
    ax.axhline(90.0, color="#d62728", linestyle="--", label="Max SOC (90%)")
    ax.axhline(30.0, color="#ff7f0e", linestyle="--", label="Reserve Floor (30% = 20% Min + 10% Reserve)")
    ax.axhline(20.0, color="#990000", linestyle=":", label="Hard Minimum SOC (20%)")

    ax.set_title("GridFlex Local — Community BESS State of Charge (SOC) Evolution", fontsize=12, fontweight="bold", pad=12)
    ax.set_xlabel("Horizon Step (15-min intervals)", fontsize=10)
    ax.set_ylabel("State of Charge (%)", fontsize=10)
    ax.set_ylim(15, 95)
    ax.grid(True)
    ax.legend(loc="upper right", framealpha=0.9)

    plt.tight_layout()
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path)
    plt.close(fig)


def plot_ev_shift_schedule(
    plan_df: pd.DataFrame,
    shift_records: List[Dict[str, Any]],
    output_path: str,
):
    """Plot shiftable load / EV energy deferral and conservation profile."""
    setup_style()
    fig, ax = plt.subplots(figsize=(10, 4.5), dpi=150)

    t = pd.to_datetime(plan_df["timestamp"])
    ax.plot(t, plan_df["selected_shift_kw"], label="Deferred Power (kW) [EV & Flexible Loads]", color="#ff7f0e", linewidth=2.0, marker="o")

    # Shifted energy cumulative
    cum_energy = (plan_df["selected_shift_kw"] * 0.25).cumsum()
    ax2 = ax.twinx()
    ax2.plot(t, cum_energy, label="Cumulative Shifted Energy (kWh)", color="#2ca02c", linestyle="--", linewidth=2.0)

    ax.set_title("GridFlex Local — EV & Flexible Load Demand Shift Schedule", fontsize=12, fontweight="bold", pad=12)
    ax.set_xlabel("Forecast Timestamp", fontsize=10)
    ax.set_ylabel("Shifted Power (kW)", color="#ff7f0e", fontsize=10)
    ax2.set_ylabel("Cumulative Energy (kWh)", color="#2ca02c", fontsize=10)
    ax.grid(True)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    fig.autofmt_xdate()

    plt.tight_layout()
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path)
    plt.close(fig)


def plot_risk_vs_flexibility(
    plan_df: pd.DataFrame,
    pf_comp_df: pd.DataFrame,
    output_path: str,
):
    """Plot grid constraint risk comparison: Baseline vs Coordinated Plan."""
    setup_style()
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6.0), dpi=150, sharex=True)

    t = pd.to_datetime(plan_df["timestamp"])

    # Transformer loading comparison
    ax1.plot(t, pf_comp_df["baseline_trafo_loading_pct"], label="Baseline Trafo Loading (No Flexibility)", color="#d62728", linewidth=2.0, linestyle="--")
    ax1.plot(t, pf_comp_df["coordinated_trafo_loading_pct"], label="Coordinated Trafo Loading (With Flex)", color="#2ca02c", linewidth=2.2, marker="o", markersize=4)
    ax1.axhline(80.0, color="#ff7f0e", linestyle=":", label="Warning Threshold (80%)")
    ax1.set_title("GridFlex Local — Transformer Loading Relief (Baseline vs Coordinated)", fontsize=11, fontweight="bold")
    ax1.set_ylabel("Loading (%)", fontsize=9)
    ax1.grid(True)
    ax1.legend(loc="upper right", fontsize=8)

    # Bus voltage comparison
    ax2.plot(t, pf_comp_df["baseline_min_vm_pu"], label="Baseline Min Bus Voltage", color="#d62728", linewidth=2.0, linestyle="--")
    ax2.plot(t, pf_comp_df["coordinated_min_vm_pu"], label="Coordinated Min Bus Voltage", color="#2ca02c", linewidth=2.2, marker="s", markersize=4)
    ax2.axhline(0.94, color="#990000", linestyle=":", label="Statutory Undervoltage Limit (0.94 p.u.)")
    ax2.set_title("GridFlex Local — Feeder Minimum Bus Voltage Improvement", fontsize=11, fontweight="bold")
    ax2.set_xlabel("Forecast Timestamp", fontsize=10)
    ax2.set_ylabel("Voltage (p.u.)", fontsize=9)
    ax2.grid(True)
    ax2.legend(loc="lower right", fontsize=8)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    fig.autofmt_xdate()

    plt.tight_layout()
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path)
    plt.close(fig)
