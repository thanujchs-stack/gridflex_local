"""Plotting utilities for GridFlex Local Phase 1 electrical figures."""

from pathlib import Path
from typing import Dict, Optional
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def generate_phase1_figures(
    df_ts_base: pd.DataFrame,
    df_ts_cloud: pd.DataFrame,
    figures_dir: Path
) -> None:
    """Generate all 7 mandatory engineering figures comparing Baseline vs Cloud scenario."""
    figures_dir.mkdir(parents=True, exist_ok=True)

    # Style configuration
    plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")
    plt.rcParams["font.sans-serif"] = "DejaVu Sans"
    plt.rcParams["axes.edgecolor"] = "#cccccc"
    plt.rcParams["axes.linewidth"] = 0.8

    # Extract time labels for clean plotting (every 8 timesteps = every 2 hours)
    x_ticks = range(0, len(df_ts_base), 8)
    x_labels = [df_ts_base["timestamp"].iloc[i].split(" ")[-1] for i in x_ticks]
    x_indices = range(len(df_ts_base))

    # 1. Total Load vs PV Generation
    fig, ax = plt.subplots(figsize=(10, 5), dpi=150)
    ax.plot(x_indices, df_ts_base["total_load_kw"], label="Total Neighbourhood Demand", color="#1f77b4", linewidth=2.2)
    ax.plot(x_indices, df_ts_base["pv_generation_kw"], label="Solar PV Generation (Baseline)", color="#ff7f0e", linewidth=2.0)
    ax.plot(x_indices, df_ts_cloud["pv_generation_kw"], label="Solar PV Generation (Cloud Event)", color="#d62728", linestyle="--", linewidth=2.0)
    ax.axvspan(60, 64, color="#ffdddd", alpha=0.5, label="Cloud Event Window (15:00 - 16:00)")
    ax.set_title("GridFlex Local: Total Feeder Demand vs. Solar PV Generation", fontsize=12, fontweight="bold", pad=12)
    ax.set_xlabel("Time of Day (HH:MM)", fontsize=10)
    ax.set_ylabel("Active Power (kW)", fontsize=10)
    ax.set_xticks(x_ticks)
    ax.set_xticklabels(x_labels, rotation=0)
    ax.legend(loc="upper right", frameon=True)
    fig.tight_layout()
    fig.savefig(figures_dir / "01_total_load_vs_pv_generation.png")
    plt.close(fig)

    # 2. Net Load Comparison
    fig, ax = plt.subplots(figsize=(10, 5), dpi=150)
    ax.plot(x_indices, df_ts_base["net_load_kw"], label="Net Load (Baseline)", color="#2ca02c", linewidth=2.0)
    ax.plot(x_indices, df_ts_cloud["net_load_kw"], label="Net Load (Cloud Event)", color="#d62728", linestyle="--", linewidth=2.0)
    ax.axhline(0, color="gray", linestyle=":", linewidth=1.0)
    ax.set_title("GridFlex Local: Feeder Net Load ($P_{load} - P_{PV}$)", fontsize=12, fontweight="bold", pad=12)
    ax.set_xlabel("Time of Day (HH:MM)", fontsize=10)
    ax.set_ylabel("Net Active Power (kW)", fontsize=10)
    ax.set_xticks(x_ticks)
    ax.set_xticklabels(x_labels)
    ax.legend(loc="upper right", frameon=True)
    fig.tight_layout()
    fig.savefig(figures_dir / "02_net_load.png")
    plt.close(fig)

    # 3. Transformer Loading
    fig, ax = plt.subplots(figsize=(10, 5), dpi=150)
    ax.plot(x_indices, df_ts_base["transformer_loading_pct"], label="Transformer Loading (Baseline)", color="#1f77b4", linewidth=2.0)
    ax.plot(x_indices, df_ts_cloud["transformer_loading_pct"], label="Transformer Loading (Cloud Event)", color="#d62728", linestyle="--", linewidth=2.0)
    ax.axhline(80.0, color="#ff7f0e", linestyle="--", label="Warning Threshold (80%)", linewidth=1.2)
    ax.axhline(100.0, color="#d62728", linestyle="-", label="Rated Capacity Limit (100%)", linewidth=1.5)
    ax.set_title("Distribution Transformer (250 kVA) Loading Profile", fontsize=12, fontweight="bold", pad=12)
    ax.set_xlabel("Time of Day (HH:MM)", fontsize=10)
    ax.set_ylabel("Loading Percentage (%)", fontsize=10)
    ax.set_xticks(x_ticks)
    ax.set_xticklabels(x_labels)
    ax.legend(loc="upper right", frameon=True)
    fig.tight_layout()
    fig.savefig(figures_dir / "03_transformer_loading.png")
    plt.close(fig)

    # 4. Maximum Line Loading
    fig, ax = plt.subplots(figsize=(10, 5), dpi=150)
    ax.plot(x_indices, df_ts_base["max_line_loading_pct"], label="Max Line Loading (Baseline)", color="#9467bd", linewidth=2.0)
    ax.plot(x_indices, df_ts_cloud["max_line_loading_pct"], label="Max Line Loading (Cloud Event)", color="#d62728", linestyle="--", linewidth=2.0)
    ax.axhline(80.0, color="#ff7f0e", linestyle="--", label="Warning Threshold (80%)", linewidth=1.2)
    ax.set_title("Maximum Feeder Line Conductor Loading", fontsize=12, fontweight="bold", pad=12)
    ax.set_xlabel("Time of Day (HH:MM)", fontsize=10)
    ax.set_ylabel("Conductor Thermal Loading (%)", fontsize=10)
    ax.set_xticks(x_ticks)
    ax.set_xticklabels(x_labels)
    ax.legend(loc="upper right", frameon=True)
    fig.tight_layout()
    fig.savefig(figures_dir / "04_maximum_line_loading.png")
    plt.close(fig)

    # 5. Bus Voltage Bounds (Min & Max Voltage p.u.)
    fig, ax = plt.subplots(figsize=(10, 5), dpi=150)
    ax.plot(x_indices, df_ts_base["max_bus_voltage_pu"], label="Max Bus Voltage (Baseline)", color="#2ca02c", linewidth=1.8)
    ax.plot(x_indices, df_ts_base["min_bus_voltage_pu"], label="Min Bus Voltage (Baseline)", color="#1f77b4", linewidth=1.8)
    ax.plot(x_indices, df_ts_cloud["min_bus_voltage_pu"], label="Min Bus Voltage (Cloud Event)", color="#d62728", linestyle=":", linewidth=2.0)
    ax.axhline(1.06, color="red", linestyle="--", label="Overvoltage Limit (1.06 p.u.)", linewidth=1.2)
    ax.axhline(0.94, color="red", linestyle="-.", label="Undervoltage Limit (0.94 p.u.)", linewidth=1.2)
    ax.set_title("Feeder Bus Voltage Profile (Min / Max across LV Network)", fontsize=12, fontweight="bold", pad=12)
    ax.set_xlabel("Time of Day (HH:MM)", fontsize=10)
    ax.set_ylabel("Voltage Magnitude (p.u.)", fontsize=10)
    ax.set_xticks(x_ticks)
    ax.set_xticklabels(x_labels)
    ax.legend(loc="lower right", frameon=True)
    fig.tight_layout()
    fig.savefig(figures_dir / "05_bus_voltage_bounds.png")
    plt.close(fig)

    # 6. Grid Import / Export Profile
    fig, ax = plt.subplots(figsize=(10, 5), dpi=150)
    ax.plot(x_indices, df_ts_base["grid_import_kw"], label="Grid Import (Baseline)", color="#1f77b4", linewidth=2.0)
    ax.plot(x_indices, df_ts_base["grid_export_kw"], label="Grid Export (Baseline)", color="#ff7f0e", linewidth=2.0)
    ax.plot(x_indices, df_ts_cloud["grid_import_kw"], label="Grid Import (Cloud Event)", color="#d62728", linestyle="--", linewidth=1.8)
    ax.set_title("External Grid Substation Exchange (Active Power)", fontsize=12, fontweight="bold", pad=12)
    ax.set_xlabel("Time of Day (HH:MM)", fontsize=10)
    ax.set_ylabel("Active Power Exchange (kW)", fontsize=10)
    ax.set_xticks(x_ticks)
    ax.set_xticklabels(x_labels)
    ax.legend(loc="upper right", frameon=True)
    fig.tight_layout()
    fig.savefig(figures_dir / "06_grid_import_export.png")
    plt.close(fig)

    # 7. Battery SOC Profile
    fig, ax = plt.subplots(figsize=(10, 5), dpi=150)
    ax.plot(x_indices, df_ts_base["battery_soc"] * 100.0, label="Community BESS SOC (Baseline Idle)", color="#17becf", linewidth=2.2)
    ax.axhline(90.0, color="#d62728", linestyle="--", label="Max SOC Limit (90%)", linewidth=1.2)
    ax.axhline(20.0, color="#d62728", linestyle="-.", label="Min SOC Limit (20%)", linewidth=1.2)
    ax.set_title("Community Battery Energy Storage System (100 kWh) State of Charge", fontsize=12, fontweight="bold", pad=12)
    ax.set_xlabel("Time of Day (HH:MM)", fontsize=10)
    ax.set_ylabel("State of Charge (%)", fontsize=10)
    ax.set_ylim(0, 100)
    ax.set_xticks(x_ticks)
    ax.set_xticklabels(x_labels)
    ax.legend(loc="upper right", frameon=True)
    fig.tight_layout()
    fig.savefig(figures_dir / "07_battery_soc.png")
    plt.close(fig)


def generate_phase2_figures(
    df_flex_summary: pd.DataFrame,
    df_der_ts: pd.DataFrame,
    df_der_reg: pd.DataFrame,
    df_avail: pd.DataFrame,
    sensitivity_summaries: Dict[str, pd.DataFrame],
    figures_dir: Path
) -> None:
    """Generate all 6 mandatory Phase 2 engineering figures."""
    figures_dir.mkdir(parents=True, exist_ok=True)

    plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")
    plt.rcParams["font.sans-serif"] = "DejaVu Sans"

    x_ticks = range(0, len(df_flex_summary), 8)
    x_labels = [df_flex_summary["timestamp"].iloc[i].split(" ")[-1] for i in x_ticks]
    x_indices = range(len(df_flex_summary))

    # 1. Total Available Flexibility over time (UP vs DOWN vs SHIFT)
    fig, ax = plt.subplots(figsize=(10, 5), dpi=150)
    ax.plot(x_indices, df_flex_summary["total_up_kw"], label="Total Available UP Flexibility (Supply Increase)", color="#2ca02c", linewidth=2.0)
    ax.plot(x_indices, df_flex_summary["total_down_kw"], label="Total Available DOWN Flexibility (Curtailment/Reduction)", color="#d62728", linewidth=2.0)
    ax.plot(x_indices, df_flex_summary["total_shiftable_kw"], label="Total Shiftable Demand Flexibility", color="#1f77b4", linestyle="--", linewidth=1.8)
    ax.set_title("GridFlex Local: Aggregated Feeder Flexibility Pools Over 24 Hours", fontsize=12, fontweight="bold", pad=12)
    ax.set_xlabel("Time of Day (HH:MM)", fontsize=10)
    ax.set_ylabel("Available Active Power Flexibility (kW)", fontsize=10)
    ax.set_xticks(x_ticks)
    ax.set_xticklabels(x_labels)
    ax.legend(loc="upper right", frameon=True)
    fig.tight_layout()
    fig.savefig(figures_dir / "08_total_available_flexibility.png")
    plt.close(fig)

    # 2. Flexibility by DER Type
    fig, ax = plt.subplots(figsize=(10, 5), dpi=150)
    ax.plot(x_indices, df_flex_summary["pv_down_kw"], label="Rooftop PV (Down / Curtailment)", color="#ff7f0e", linewidth=2.0)
    ax.plot(x_indices, df_flex_summary["battery_up_kw"], label="Community BESS (Up / Discharge)", color="#2ca02c", linewidth=1.8)
    ax.plot(x_indices, df_flex_summary["battery_down_kw"], label="Community BESS (Down / Charge)", color="#17becf", linestyle=":", linewidth=1.8)
    ax.plot(x_indices, df_flex_summary["ev_down_kw"], label="EV Charging (Down / Throttle)", color="#9467bd", linewidth=1.8)
    ax.plot(x_indices, df_flex_summary["flexible_load_down_kw"], label="Flexible Loads (Down / Shed)", color="#8c564b", linewidth=1.8)
    ax.set_title("Available Active Flexibility Disaggregated by Resource Category", fontsize=12, fontweight="bold", pad=12)
    ax.set_xlabel("Time of Day (HH:MM)", fontsize=10)
    ax.set_ylabel("Available Flexibility (kW)", fontsize=10)
    ax.set_xticks(x_ticks)
    ax.set_xticklabels(x_labels)
    ax.legend(loc="upper right", frameon=True)
    fig.tight_layout()
    fig.savefig(figures_dir / "09_flexibility_by_der_type.png")
    plt.close(fig)

    # 3. Battery Available Flexibility vs SOC
    soc_sweep = np.linspace(0.0, 1.0, 101)
    bess_cap_kwh = 100.0
    min_soc = 0.20
    reserve_soc = 0.10
    usable_min_soc = min_soc + reserve_soc  # 0.30
    max_soc = 0.90
    max_dis_kw = 25.0
    max_ch_kw = 25.0
    dt_h = 0.25

    avail_dis_kw = np.clip(np.maximum(0.0, (soc_sweep - usable_min_soc) * bess_cap_kwh * 0.95 / dt_h), 0.0, max_dis_kw)
    avail_ch_kw = np.clip(np.maximum(0.0, (max_soc - soc_sweep) * bess_cap_kwh / (0.95 * dt_h)), 0.0, max_ch_kw)

    fig, ax = plt.subplots(figsize=(10, 5), dpi=150)
    ax.plot(soc_sweep * 100, avail_dis_kw, label="Available Discharge Flexibility (UP)", color="#2ca02c", linewidth=2.2)
    ax.plot(soc_sweep * 100, avail_ch_kw, label="Available Charge Flexibility (DOWN)", color="#17becf", linewidth=2.2)
    ax.axvline(20.0, color="#d62728", linestyle="--", label="Absolute Min SOC (20%)", linewidth=1.2)
    ax.axvline(30.0, color="#ff7f0e", linestyle="-.", label="Effective Min with 10% Reserve (30%)", linewidth=1.2)
    ax.axvline(90.0, color="#d62728", linestyle=":", label="Max SOC Limit (90%)", linewidth=1.2)
    ax.set_title("Community BESS (100 kWh) Headroom Curves vs. State of Charge", fontsize=12, fontweight="bold", pad=12)
    ax.set_xlabel("Battery State of Charge (%)", fontsize=10)
    ax.set_ylabel("Available Dispatchable Power (kW)", fontsize=10)
    ax.legend(loc="center right", frameon=True)
    fig.tight_layout()
    fig.savefig(figures_dir / "10_battery_flexibility_vs_soc.png")
    plt.close(fig)

    # 4. EV Availability & Charging Profile
    ev_cols = [c for c in df_avail.columns if c.startswith("EV_")]
    ev_active_count = df_avail[ev_cols].sum(axis=1)

    fig, ax = plt.subplots(figsize=(10, 5), dpi=150)
    ax.plot(x_indices, ev_active_count, label="Connected EV Count", color="#9467bd", linewidth=2.2)
    ax.set_title("Electric Vehicle Fleet Connection & Charging Window Profile", fontsize=12, fontweight="bold", pad=12)
    ax.set_xlabel("Time of Day (HH:MM)", fontsize=10)
    ax.set_ylabel("Number of Connected / Charging EVs", fontsize=10)
    ax.set_xticks(x_ticks)
    ax.set_xticklabels(x_labels)
    ax.set_ylim(0, 22)
    ax.legend(loc="upper left", frameon=True)
    fig.tight_layout()
    fig.savefig(figures_dir / "11_ev_availability.png")
    plt.close(fig)

    # 5. PV Available Power vs Curtailment Flexibility
    pv_cols = [c for c in df_der_ts.columns if c.startswith("PV_")]
    total_pv_power = df_der_ts[pv_cols].sum(axis=1)
    participating_pv_flex = df_flex_summary["pv_down_kw"]

    fig, ax = plt.subplots(figsize=(10, 5), dpi=150)
    ax.plot(x_indices, total_pv_power, label="Total Technical Solar PV Generation", color="#ff7f0e", linewidth=2.0)
    ax.plot(x_indices, participating_pv_flex, label="Opted-in Dispatchable Curtailment Flexibility", color="#2ca02c", linestyle="--", linewidth=2.0)
    ax.set_title("Rooftop PV: Technical Output vs. Participating Curtailment Capacity", fontsize=12, fontweight="bold", pad=12)
    ax.set_xlabel("Time of Day (HH:MM)", fontsize=10)
    ax.set_ylabel("Active Power (kW)", fontsize=10)
    ax.set_xticks(x_ticks)
    ax.set_xticklabels(x_labels)
    ax.legend(loc="upper right", frameon=True)
    fig.tight_layout()
    fig.savefig(figures_dir / "12_pv_curtailment_flexibility.png")
    plt.close(fig)

    # 6. Participation Sensitivity Experiment
    fig, ax = plt.subplots(figsize=(10, 5), dpi=150)
    colors = {"100%": "#1f77b4", "70%": "#2ca02c", "40%": "#ff7f0e"}
    for label, df_s in sensitivity_summaries.items():
        c = colors.get(label, "#333333")
        ax.plot(x_indices, df_s["total_down_kw"], label=f"Total DOWN Flex ({label} Participation)", color=c, linewidth=1.8)

    ax.set_title("Sensitivity of Feeder Available Flexibility to Consumer Opt-In Rates", fontsize=12, fontweight="bold", pad=12)
    ax.set_xlabel("Time of Day (HH:MM)", fontsize=10)
    ax.set_ylabel("Available Downward Flexibility (kW)", fontsize=10)
    ax.set_xticks(x_ticks)
    ax.set_xticklabels(x_labels)
    ax.legend(loc="upper right", frameon=True)
    fig.tight_layout()
    fig.savefig(figures_dir / "13_participation_sensitivity.png")
    plt.close(fig)

