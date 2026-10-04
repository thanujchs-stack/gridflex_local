"""Publication-grade engineering visualizations for Phase 7 Electrical Validation.

Generates 8 high-resolution diagnostic plots comparing Baseline vs GridFlex across:
1. Transformer Loading
2. Line Loading
3. Voltage Profile
4. Reverse Power Flow
5. Grid Import
6. Constraint Durations
7. Participation Scenarios
8. Cloud Event Intermittency
"""

from pathlib import Path
from typing import Optional
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd
import numpy as np


# Palette & Styling
STYLE_BASE = "#94a3b8"       # Slate gray for baseline
STYLE_GRIDFLEX = "#0284c7"   # Cyan/Sky blue for GridFlex
STYLE_ALERT = "#ef4444"      # Red alert / limit
STYLE_WARN = "#f59e0b"       # Amber warning
STYLE_TEAL = "#0d9488"       # Vibrant teal
STYLE_PURPLE = "#8b5cf6"     # Purple for scenarios


def setup_plot_style():
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


def generate_all_phase7_plots(
    ts_df: pd.DataFrame,
    summary_df: pd.DataFrame,
    output_dir: Path,
):
    """Generate all 8 required Phase 7 engineering plots."""
    setup_plot_style()
    output_dir.mkdir(parents=True, exist_ok=True)

    ts_df = ts_df.copy()
    ts_df["timestamp"] = pd.to_datetime(ts_df["timestamp"])

    # Normal Day subsets
    norm_base = ts_df[(ts_df["scenario"] == "NORMAL_DAY") & (ts_df["case"] == "CASE_A_BASELINE")].sort_values("timestamp")
    norm_flex = ts_df[(ts_df["scenario"] == "NORMAL_DAY") & (ts_df["case"] == "CASE_B_GRIDFLEX")].sort_values("timestamp")

    # 1. Baseline vs GridFlex Transformer Loading
    fig, ax = plt.subplots(figsize=(10, 5), dpi=300)
    ax.plot(norm_base["timestamp"], norm_base["transformer_loading_percent"], label="Baseline (Uncontrolled)", color=STYLE_BASE, lw=2.2, marker="o", ms=4)
    ax.plot(norm_flex["timestamp"], norm_flex["transformer_loading_percent"], label="GridFlex Optimized (70%)", color=STYLE_GRIDFLEX, lw=2.5, marker="s", ms=4)
    ax.axhline(80.0, color=STYLE_WARN, linestyle=":", lw=1.8, label="80% Warning Threshold")
    ax.axhline(100.0, color=STYLE_ALERT, linestyle="--", lw=1.8, label="100% Thermal Rating")
    ax.set_ylabel("Transformer Loading (%)", fontsize=11, fontweight="bold")
    ax.set_title("Transformer Loading: Baseline vs GridFlex Coordinated Dispatch", fontsize=13, fontweight="bold", pad=12)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax.grid(True)
    ax.legend(frameon=True, facecolor="#ffffff", edgecolor="#e2e8f0")
    plt.tight_layout()
    fig.savefig(output_dir / "baseline_vs_gridflex_transformer_loading.png", dpi=300)
    plt.close(fig)

    # 2. Baseline vs GridFlex Line Loading
    fig, ax = plt.subplots(figsize=(10, 5), dpi=300)
    ax.plot(norm_base["timestamp"], norm_base["max_line_loading_percent"], label="Baseline Max Line Loading", color=STYLE_BASE, lw=2.2, marker="o", ms=4)
    ax.plot(norm_flex["timestamp"], norm_flex["max_line_loading_percent"], label="GridFlex Max Line Loading", color=STYLE_TEAL, lw=2.5, marker="^", ms=4)
    ax.axhline(80.0, color=STYLE_WARN, linestyle=":", lw=1.8, label="80% Feeder Warning")
    ax.axhline(100.0, color=STYLE_ALERT, linestyle="--", lw=1.8, label="100% Feeder Rating")
    ax.set_ylabel("Maximum Line Loading (%)", fontsize=11, fontweight="bold")
    ax.set_title("Feeder Line Loading: Baseline vs GridFlex Feeder Congestion Relief", fontsize=13, fontweight="bold", pad=12)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax.grid(True)
    ax.legend(frameon=True, facecolor="#ffffff", edgecolor="#e2e8f0")
    plt.tight_layout()
    fig.savefig(output_dir / "baseline_vs_gridflex_line_loading.png", dpi=300)
    plt.close(fig)

    # 3. Baseline vs GridFlex Voltage Profile
    fig, ax = plt.subplots(figsize=(10, 5), dpi=300)
    ax.plot(norm_base["timestamp"], norm_base["min_bus_voltage_pu"], label="Baseline Min Voltage", color=STYLE_BASE, lw=2.2, marker="o", ms=4)
    ax.plot(norm_flex["timestamp"], norm_flex["min_bus_voltage_pu"], label="GridFlex Min Voltage", color=STYLE_GRIDFLEX, lw=2.5, marker="s", ms=4)
    ax.axhline(0.94, color=STYLE_ALERT, linestyle="--", lw=1.8, label="0.94 pu Undervoltage Limit")
    ax.axhline(1.00, color="#64748b", linestyle="-", lw=1.0, alpha=0.5)
    ax.axhline(1.06, color=STYLE_ALERT, linestyle="--", lw=1.8, label="1.06 pu Overvoltage Limit")
    ax.set_ylabel("Bus Voltage (p.u.)", fontsize=11, fontweight="bold")
    ax.set_title("Nodal Voltage Compliance: Baseline vs GridFlex Voltage Support", fontsize=13, fontweight="bold", pad=12)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax.grid(True)
    ax.legend(frameon=True, facecolor="#ffffff", edgecolor="#e2e8f0")
    plt.tight_layout()
    fig.savefig(output_dir / "baseline_vs_gridflex_voltage.png", dpi=300)
    plt.close(fig)

    # 4. Baseline vs GridFlex Reverse Power Flow
    fig, ax = plt.subplots(figsize=(10, 5), dpi=300)
    ax.plot(norm_base["timestamp"], norm_base["reverse_power_kw"], label="Baseline Reverse Flow", color=STYLE_BASE, lw=2.2, marker="o", ms=4)
    ax.plot(norm_flex["timestamp"], norm_flex["reverse_power_kw"], label="GridFlex Reverse Flow", color=STYLE_PURPLE, lw=2.5, marker="D", ms=4)
    ax.set_ylabel("Reverse Power Flow at Transformer (kW)", fontsize=11, fontweight="bold")
    ax.set_title("Distribution Transformer Reverse Power Flow Trajectory", fontsize=13, fontweight="bold", pad=12)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax.grid(True)
    ax.legend(frameon=True, facecolor="#ffffff", edgecolor="#e2e8f0")
    plt.tight_layout()
    fig.savefig(output_dir / "baseline_vs_gridflex_reverse_power.png", dpi=300)
    plt.close(fig)

    # 5. Baseline vs GridFlex Grid Import
    fig, ax = plt.subplots(figsize=(10, 5), dpi=300)
    ax.plot(norm_base["timestamp"], norm_base["grid_import_kw"], label="Baseline Substation Import", color=STYLE_BASE, lw=2.2, marker="o", ms=4)
    ax.plot(norm_flex["timestamp"], norm_flex["grid_import_kw"], label="GridFlex Substation Import", color=STYLE_GRIDFLEX, lw=2.5, marker="s", ms=4)
    ax.set_ylabel("External Grid Import (kW)", fontsize=11, fontweight="bold")
    ax.set_title("Substation Active Power Import: Peak Shaving & Load Deferral", fontsize=13, fontweight="bold", pad=12)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax.grid(True)
    ax.legend(frameon=True, facecolor="#ffffff", edgecolor="#e2e8f0")
    plt.tight_layout()
    fig.savefig(output_dir / "baseline_vs_gridflex_grid_import.png", dpi=300)
    plt.close(fig)

    # 6. Constraint Duration Comparison
    fig, ax = plt.subplots(figsize=(9, 5), dpi=300)
    cases = ["CASE_A_BASELINE", "CASE_B_GRIDFLEX"]
    labels = ["Baseline", "GridFlex"]
    durations = []
    for c in cases:
        row = summary_df[(summary_df["scenario"] == "NORMAL_DAY") & (summary_df["case"] == c)]
        durations.append(int(row["transformer_overload_duration_min"].iloc[0]) if not row.empty else 0)

    bars = ax.bar(labels, durations, color=[STYLE_BASE, STYLE_GRIDFLEX], width=0.45, edgecolor="#334155", lw=1.2)
    for bar in bars:
        yval = bar.get_height()
        ax.text(bar.get_x() + bar.get_width() / 2.0, yval + 1.0, f"{yval} min", ha="center", va="bottom", fontweight="bold")
    ax.set_ylabel("Overload Duration (Minutes)", fontsize=11, fontweight="bold")
    ax.set_title("Transformer Constraint Exposure Duration (Loading > 80%)", fontsize=13, fontweight="bold", pad=12)
    ax.set_ylim(0, max(15, max(durations) * 1.3))
    ax.grid(axis="y")
    plt.tight_layout()
    fig.savefig(output_dir / "constraint_duration_comparison.png", dpi=300)
    plt.close(fig)

    # 7. Participation Scenario Comparison
    fig, ax = plt.subplots(figsize=(10, 5), dpi=300)
    part_df = summary_df[summary_df["scenario"] == "PARTICIPATION"]
    if not part_df.empty:
        rates = part_df["case"].tolist()
        rates_clean = [r.replace("GRIDFLEX_", "").replace("PCT", "%") for r in rates]
        peak_trafo_vals = part_df["peak_transformer_loading_percent"].tolist()
        peak_import_vals = part_df["peak_grid_import_kw"].tolist()

        x = np.arange(len(rates_clean))
        width = 0.35
        ax.bar(x - width / 2, peak_trafo_vals, width, label="Peak Trafo Loading (%)", color=STYLE_TEAL, edgecolor="#334155")
        ax.bar(x + width / 2, peak_import_vals, width, label="Peak Grid Import (kW)", color=STYLE_PURPLE, edgecolor="#334155")
        ax.set_xticks(x)
        ax.set_xticklabels(rates_clean, fontweight="bold")
        ax.set_ylabel("Electrical Metric Magnitude", fontsize=11, fontweight="bold")
        ax.set_title("Participation Sensitivity: Feeder Relief Across 100%, 70%, 40% Opt-in", fontsize=13, fontweight="bold", pad=12)
        ax.grid(axis="y")
        ax.legend(frameon=True, facecolor="#ffffff", edgecolor="#e2e8f0")
    plt.tight_layout()
    fig.savefig(output_dir / "participation_scenario_comparison.png", dpi=300)
    plt.close(fig)

    # 8. Cloud Event Intermittency Comparison
    fig, ax = plt.subplots(figsize=(10, 5), dpi=300)
    cloud_base = ts_df[(ts_df["scenario"] == "CLOUD_EVENT") & (ts_df["case"] == "CASE_A_BASELINE_CLOUD")].sort_values("timestamp")
    cloud_flex = ts_df[(ts_df["scenario"] == "CLOUD_EVENT") & (ts_df["case"] == "CASE_B_GRIDFLEX_CLOUD")].sort_values("timestamp")

    if not cloud_base.empty and not cloud_flex.empty:
        ax.plot(cloud_base["timestamp"], cloud_base["grid_import_kw"], label="Baseline Cloud Substation Import", color=STYLE_BASE, lw=2.2, marker="o", ms=4)
        ax.plot(cloud_flex["timestamp"], cloud_flex["grid_import_kw"], label="GridFlex Cloud Substation Import", color=STYLE_ALERT, lw=2.5, marker="s", ms=4)
        ax.axvspan(
            cloud_base["timestamp"].iloc[6],
            cloud_base["timestamp"].iloc[9],
            color="#fef08a",
            alpha=0.35,
            label="Cloud Event Window (15:00 - 16:00)",
        )
        ax.set_ylabel("Substation Active Power Import (kW)", fontsize=11, fontweight="bold")
        ax.set_title("Solar Intermittency (Cloud Dip): Baseline vs GridFlex Grid Support", fontsize=13, fontweight="bold", pad=12)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
        ax.grid(True)
        ax.legend(frameon=True, facecolor="#ffffff", edgecolor="#e2e8f0")
    plt.tight_layout()
    fig.savefig(output_dir / "cloud_event_comparison.png", dpi=300)
    plt.close(fig)
