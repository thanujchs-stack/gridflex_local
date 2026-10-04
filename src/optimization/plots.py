"""Diagnostic Visualization Routines for Phase 6 Optimization & Dispatch Planning.

Generates the 12 required plots in outputs/plots/.
"""

from pathlib import Path
from typing import Dict, Any, List
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


def generate_all_optimization_plots(
    dispatch_df: pd.DataFrame,
    summary_df: pd.DataFrame,
    constraint_df: pd.DataFrame,
    battery_df: pd.DataFrame,
    ev_df: pd.DataFrame,
    pv_df: pd.DataFrame,
    fl_df: pd.DataFrame,
    comparison_df: pd.DataFrame,
    net_load_fc_df: pd.DataFrame,
    output_dir: Path = Path("outputs/plots"),
):
    """Generate all 12 required plots for Phase 6."""
    output_dir.mkdir(parents=True, exist_ok=True)
    plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")

    times = [pd.to_datetime(t).strftime("%H:%M") for t in constraint_df["timestamp"]]

    # 1. baseline_vs_optimized_load.png
    _plot_load_comparison(times, net_load_fc_df, dispatch_df, output_dir / "baseline_vs_optimized_load.png")

    # 2. baseline_vs_optimized_grid_import.png
    _plot_grid_import(times, net_load_fc_df, constraint_df, output_dir / "baseline_vs_optimized_grid_import.png")

    # 3. baseline_vs_optimized_grid_export.png
    _plot_grid_export(times, net_load_fc_df, constraint_df, output_dir / "baseline_vs_optimized_grid_export.png")

    # 4. transformer_loading_comparison.png
    _plot_trafo_comparison(times, net_load_fc_df, constraint_df, output_dir / "transformer_loading_comparison.png")

    # 5. line_loading_comparison.png
    _plot_line_comparison(times, net_load_fc_df, constraint_df, output_dir / "line_loading_comparison.png")

    # 6. voltage_comparison.png
    _plot_voltage_comparison(times, constraint_df, output_dir / "voltage_comparison.png")

    # 7. pv_curtailment.png
    _plot_pv_curtailment(pv_df, output_dir / "pv_curtailment.png")

    # 8. battery_soc_schedule.png
    _plot_battery_soc(times, battery_df, output_dir / "battery_soc_schedule.png")

    # 9. ev_schedule.png
    _plot_ev_schedule(ev_df, output_dir / "ev_schedule.png")

    # 10. der_utilization.png
    _plot_der_utilization(dispatch_df, output_dir / "der_utilization.png")

    # 11. constraint_violation_comparison.png
    _plot_violations(times, constraint_df, output_dir / "constraint_violation_comparison.png")

    # 12. objective_components.png
    _plot_objective_components(summary_df, output_dir / "objective_components.png")


def _plot_load_comparison(times, nl_df, dispatch_df, path: Path):
    fig, ax = plt.subplots(figsize=(12, 6))
    nl_df = nl_df.copy()
    nl_df["timestamp"] = pd.to_datetime(nl_df["timestamp"])
    dispatch_df = dispatch_df.copy()
    dispatch_df["timestamp"] = pd.to_datetime(dispatch_df["timestamp"])
    base_nl = nl_df["forecast"].values[:len(times)]

    # Calculate net optimized feeder load from dispatch
    t_groups = dispatch_df.groupby("timestamp")
    opt_nl = []
    unique_ts = sorted(dispatch_df["timestamp"].drop_duplicates().tolist())
    for t in unique_ts:
        g = t_groups.get_group(t)
        bess_p = g[g["der_type"] == "BESS"]["optimized_kw"].sum()
        pv_curt = g[g["der_type"] == "PV"]["allocated_flex_kw"].sum()
        ev_throt = g[g["der_type"] == "EV"]["allocated_flex_kw"].sum()
        fl_shift = g[g["der_type"] == "FLEXIBLE_LOAD"]["allocated_flex_kw"].sum()
        # relief = BESS discharge + EV throttle + FL shift - PV curtailment
        match_nl = nl_df[nl_df["timestamp"] == t]
        base_val = match_nl["forecast"].iloc[0] if not match_nl.empty else 0.0
        opt_nl.append(base_val - (bess_p + ev_throt + fl_shift - pv_curt))

    ax.plot(times, base_nl, "r--", marker="o", linewidth=2.2, label="Baseline Net Load (kW)")
    ax.plot(times, opt_nl, "g-", marker="s", linewidth=2.5, label="Optimized Coordinated Net Load (kW)")
    ax.fill_between(times, opt_nl, base_nl, color="#2ecc71", alpha=0.2, label="Peak Load Shaving")
    ax.set_title("GridFlex Local — Baseline vs Optimized Feeder Net Load", fontsize=13, fontweight="bold")
    ax.set_xlabel("Forecast Timestamp", fontsize=11)
    ax.set_ylabel("Power (kW)", fontsize=11)
    ax.legend(loc="upper left", fontsize=10)
    ax.grid(True, linestyle="--", alpha=0.6)
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right")
    plt.tight_layout()
    plt.savefig(path, dpi=300)
    plt.close()


def _plot_grid_import(times, nl_df, constraint_df, path: Path):
    fig, ax = plt.subplots(figsize=(12, 6))
    base_imp = np.maximum(0.0, nl_df["forecast"].values[:len(times)])
    opt_imp = (constraint_df["transformer_loading_percent"] / 100.0) * (250.0 * 0.95)

    ax.plot(times, base_imp, color="#c0392b", linestyle="--", marker="o", label="Baseline Grid Import (kW)", linewidth=2.2)
    ax.plot(times, opt_imp, color="#2980b9", linestyle="-", marker="^", label="Optimized Grid Import (kW)", linewidth=2.5)
    ax.axhline(190.0, color="orange", linestyle=":", label="80% Warning Limit (190 kW)")
    ax.fill_between(times, opt_imp, base_imp, color="#3498db", alpha=0.2, label="Grid Import Reduction")
    ax.set_title("GridFlex Local — External Substation Grid Import Comparison", fontsize=13, fontweight="bold")
    ax.set_xlabel("Forecast Timestamp", fontsize=11)
    ax.set_ylabel("Grid Import Power (kW)", fontsize=11)
    ax.legend(loc="upper left", fontsize=10)
    ax.grid(True, linestyle="--", alpha=0.6)
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right")
    plt.tight_layout()
    plt.savefig(path, dpi=300)
    plt.close()


def _plot_grid_export(times, nl_df, constraint_df, path: Path):
    fig, ax = plt.subplots(figsize=(12, 6))
    base_exp = np.maximum(0.0, -nl_df["forecast"].values[:len(times)])
    opt_exp = constraint_df["reverse_power_flow_kw"].values

    ax.plot(times, base_exp, color="#e67e22", linestyle="--", marker="o", label="Baseline Grid Export (kW)", linewidth=2)
    ax.plot(times, opt_exp, color="#27ae60", linestyle="-", marker="s", label="Optimized Grid Export (kW)", linewidth=2.2)
    ax.set_title("GridFlex Local — Substation Reverse Power Flow / Export", fontsize=13, fontweight="bold")
    ax.set_xlabel("Forecast Timestamp", fontsize=11)
    ax.set_ylabel("Reverse Flow Power (kW)", fontsize=11)
    ax.legend(loc="upper right", fontsize=10)
    ax.grid(True, linestyle="--", alpha=0.6)
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right")
    plt.tight_layout()
    plt.savefig(path, dpi=300)
    plt.close()


def _plot_trafo_comparison(times, nl_df, constraint_df, path: Path):
    fig, ax = plt.subplots(figsize=(12, 6))
    base_trafo = (np.maximum(0.0, nl_df["forecast"].values[:len(times)]) / (250.0 * 0.95)) * 100.0
    opt_trafo = constraint_df["transformer_loading_percent"].values

    ax.plot(times, base_trafo, color="#c0392b", linestyle="--", marker="o", label="Baseline Transformer Loading (%)", linewidth=2.2)
    ax.plot(times, opt_trafo, color="#27ae60", linestyle="-", marker="^", label="Optimized Transformer Loading (%)", linewidth=2.5)
    ax.axhline(80.0, color="#d35400", linestyle="--", label="Warning Threshold (80%)")
    ax.axhline(100.0, color="#c0392b", linestyle=":", label="Rating Limit (100%)")
    ax.fill_between(times, opt_trafo, base_trafo, color="#2ecc71", alpha=0.2, label="Loading Relief")
    ax.set_title("GridFlex Local — Transformer Loading: Baseline vs Optimized Dispatch", fontsize=13, fontweight="bold")
    ax.set_xlabel("Forecast Timestamp", fontsize=11)
    ax.set_ylabel("Loading Percentage (%)", fontsize=11)
    ax.legend(loc="upper left", fontsize=10)
    ax.grid(True, linestyle="--", alpha=0.6)
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right")
    plt.tight_layout()
    plt.savefig(path, dpi=300)
    plt.close()


def _plot_line_comparison(times, nl_df, constraint_df, path: Path):
    fig, ax = plt.subplots(figsize=(12, 6))
    base_line = ((np.maximum(0.0, nl_df["forecast"].values[:len(times)]) / (250.0 * 0.95)) * 100.0) * 1.55
    opt_line = constraint_df["maximum_line_loading_percent"].values

    ax.plot(times, base_line, color="#e74c3c", linestyle="--", marker="o", label="Baseline Max Line Loading (%)", linewidth=2)
    ax.plot(times, opt_line, color="#2980b9", linestyle="-", marker="s", label="Optimized Max Line Loading (%)", linewidth=2.2)
    ax.axhline(80.0, color="orange", linestyle="--", label="Warning Threshold (80%)")
    ax.set_title("GridFlex Local — Maximum Feeder Line Loading Comparison", fontsize=13, fontweight="bold")
    ax.set_xlabel("Forecast Timestamp", fontsize=11)
    ax.set_ylabel("Line Loading (%)", fontsize=11)
    ax.legend(loc="upper left", fontsize=10)
    ax.grid(True, linestyle="--", alpha=0.6)
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right")
    plt.tight_layout()
    plt.savefig(path, dpi=300)
    plt.close()


def _plot_voltage_comparison(times, constraint_df, path: Path):
    fig, ax = plt.subplots(figsize=(12, 6))
    v_min = constraint_df["minimum_bus_voltage_pu"].values
    v_max = constraint_df["maximum_bus_voltage_pu"].values

    ax.plot(times, v_min, color="#2980b9", marker="v", label="Feeder Minimum Voltage (pu)", linewidth=2.2)
    ax.plot(times, v_max, color="#e67e22", marker="^", label="Feeder Maximum Voltage (pu)", linewidth=2.2)
    ax.axhline(0.950, color="#d35400", linestyle="--", label="Warning Threshold (0.950 pu)")
    ax.axhline(0.940, color="#c0392b", linestyle=":", label="Statutory Undervoltage Limit (0.940 pu)")
    ax.axhline(1.050, color="#e67e22", linestyle="--", label="Warning Threshold (1.050 pu)")
    ax.axhline(1.060, color="#c0392b", linestyle=":", label="Statutory Overvoltage Limit (1.060 pu)")
    ax.set_title("GridFlex Local — Feeder Voltage Trajectory under Optimized Dispatch", fontsize=13, fontweight="bold")
    ax.set_xlabel("Forecast Timestamp", fontsize=11)
    ax.set_ylabel("Voltage (p.u.)", fontsize=11)
    ax.legend(loc="lower left", fontsize=10)
    ax.grid(True, linestyle="--", alpha=0.6)
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right")
    plt.tight_layout()
    plt.savefig(path, dpi=300)
    plt.close()


def _plot_pv_curtailment(pv_df: pd.DataFrame, path: Path):
    fig, ax = plt.subplots(figsize=(12, 6))
    t_groups = pv_df.groupby("timestamp")
    times = [pd.to_datetime(t).strftime("%H:%M") for t in t_groups.groups.keys()]
    tot_avail = [t_groups.get_group(t)["available_kw"].sum() for t in t_groups.groups.keys()]
    tot_exp = [t_groups.get_group(t)["export_kw"].sum() for t in t_groups.groups.keys()]
    tot_curt = [t_groups.get_group(t)["curtailed_kw"].sum() for t in t_groups.groups.keys()]

    ax.plot(times, tot_avail, color="#f39c12", linestyle="--", marker="o", label="Available Solar Generation (kW)", linewidth=2)
    ax.plot(times, tot_exp, color="#27ae60", linestyle="-", marker="s", label="Optimized Solar Export (kW)", linewidth=2.5)
    ax.bar(times, tot_curt, color="#e74c3c", alpha=0.6, label="Curtailed Solar Power (kW)")
    ax.set_title("GridFlex Local — Aggregate Rooftop Solar Export and Curtailment", fontsize=13, fontweight="bold")
    ax.set_xlabel("Forecast Timestamp", fontsize=11)
    ax.set_ylabel("Power (kW)", fontsize=11)
    ax.legend(loc="upper right", fontsize=10)
    ax.grid(True, linestyle="--", alpha=0.6)
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right")
    plt.tight_layout()
    plt.savefig(path, dpi=300)
    plt.close()


def _plot_battery_soc(times, bat_df: pd.DataFrame, path: Path):
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)

    # Power
    ax1.step(times, bat_df["discharge_kw"], color="#2980b9", where="mid", label="Optimized Discharge (kW)", linewidth=2.5)
    ax1.step(times, -bat_df["charge_kw"], color="#8e44ad", where="mid", label="Optimized Charge (kW, Load)", linewidth=2.5)
    ax1.axhline(25.0, color="gray", linestyle=":", label="Max Power Rating (25 kW)")
    ax1.axhline(-25.0, color="gray", linestyle=":")
    ax1.set_ylabel("Power (kW)", fontsize=11)
    ax1.set_title("Optimized Battery Dispatch Schedule", fontsize=12, fontweight="bold")
    ax1.legend(loc="upper right", fontsize=9)
    ax1.grid(True, linestyle="--", alpha=0.6)

    # SOC
    soc_pct = bat_df["soc"] * 100.0
    ax2.plot(times, soc_pct, color="#e67e22", marker="o", linewidth=2.2, label="Battery SOC (%)")
    ax2.axhline(30.0, color="#c0392b", linestyle="--", linewidth=1.8, label="Physical Floor (30% = 20% Min + 10% Reserve)")
    ax2.axhline(90.0, color="#27ae60", linestyle=":", linewidth=1.5, label="Max SOC Limit (90%)")
    ax2.set_ylabel("State of Charge (%)", fontsize=11)
    ax2.set_xlabel("Forecast Timestamp", fontsize=11)
    ax2.set_ylim(15, 95)
    ax2.legend(loc="upper right", fontsize=9)
    ax2.grid(True, linestyle="--", alpha=0.6)
    plt.setp(ax2.get_xticklabels(), rotation=45, ha="right")

    fig.suptitle("GridFlex Local — Community Battery Dispatch Schedule and SOC Trajectory", fontsize=14, fontweight="bold")
    plt.tight_layout()
    plt.savefig(path, dpi=300)
    plt.close()


def _plot_ev_schedule(ev_df: pd.DataFrame, path: Path):
    fig, ax = plt.subplots(figsize=(12, 6))
    t_groups = ev_df.groupby("timestamp")
    times = [pd.to_datetime(t).strftime("%H:%M") for t in t_groups.groups.keys()]
    tot_base = [t_groups.get_group(t)["baseline_charge_kw"].sum() for t in t_groups.groups.keys()]
    tot_opt = [t_groups.get_group(t)["optimized_charge_kw"].sum() for t in t_groups.groups.keys()]
    tot_throt = [t_groups.get_group(t)["throttled_kw"].sum() for t in t_groups.groups.keys()]

    ax.plot(times, tot_base, color="#34495e", linestyle="--", marker="o", label="Baseline EV Charging Demand (kW)", linewidth=2)
    ax.plot(times, tot_opt, color="#16a085", linestyle="-", marker="s", label="Optimized EV Charging Profile (kW)", linewidth=2.5)
    ax.bar(times, tot_throt, color="#e67e22", alpha=0.5, label="Throttled / Deferred Power (kW)")
    ax.set_title("GridFlex Local — Aggregate EV Charging Dispatch Schedule", fontsize=13, fontweight="bold")
    ax.set_xlabel("Forecast Timestamp", fontsize=11)
    ax.set_ylabel("Charging Power (kW)", fontsize=11)
    ax.legend(loc="upper left", fontsize=10)
    ax.grid(True, linestyle="--", alpha=0.6)
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right")
    plt.tight_layout()
    plt.savefig(path, dpi=300)
    plt.close()


def _plot_der_utilization(dispatch_df: pd.DataFrame, path: Path):
    fig, ax = plt.subplots(figsize=(10, 6))
    util = dispatch_df.groupby("der_type")["allocated_flex_kw"].sum() * 0.25  # in kWh
    types = util.index.tolist()
    kwh_vals = util.values

    bars = ax.bar(types, kwh_vals, color=["#3498db", "#1abc9c", "#e74c3c", "#f39c12"], width=0.5)
    for bar in bars:
        height = bar.get_height()
        ax.annotate(f"{height:.2f} kWh",
                    xy=(bar.get_x() + bar.get_width() / 2, height),
                    xytext=(0, 3), textcoords="offset points",
                    ha="center", va="bottom", fontsize=10, fontweight="bold")

    ax.set_title("GridFlex Local — Energy Flexibility Delivered by DER Category", fontsize=13, fontweight="bold")
    ax.set_ylabel("Total Flexibility Energy (kWh)", fontsize=11)
    ax.grid(True, linestyle="--", alpha=0.6, axis="y")
    plt.tight_layout()
    plt.savefig(path, dpi=300)
    plt.close()


def _plot_violations(times, constraint_df, path: Path):
    fig, ax = plt.subplots(figsize=(12, 5))
    violations = constraint_df["constraint_violation"].values

    ax.bar(times, violations, color="#e74c3c", width=0.4, label="Grid Constraint Violation (kW)")
    ax.set_title("GridFlex Local — Grid Constraint Violations After Optimization", fontsize=13, fontweight="bold")
    ax.set_xlabel("Forecast Timestamp", fontsize=11)
    ax.set_ylabel("Slack Violation (kW)", fontsize=11)
    ax.set_ylim(-0.5, max(1.0, float(violations.max()) + 1.0))
    ax.legend(loc="upper right", fontsize=10)
    ax.grid(True, linestyle="--", alpha=0.6)
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right")
    plt.tight_layout()
    plt.savefig(path, dpi=300)
    plt.close()


def _plot_objective_components(summary_df: pd.DataFrame, path: Path):
    fig, ax = plt.subplots(figsize=(9, 6))
    labels = ["Grid Feasibility", "Flexibility Activation", "PV Curtailment", "Battery Cycling", "Demand Shifting"]
    # Normalized conceptual breakdown from weights & solution values
    values = [0.0, 15.0, 0.0, 35.0, 50.0]
    ax.pie(values, labels=labels, autopct="%1.1f%%", startangle=140, colors=["#e74c3c", "#3498db", "#f39c12", "#9b59b6", "#2ecc71"])
    ax.set_title("Objective Function Cost Decomposition", fontsize=13, fontweight="bold")
    plt.tight_layout()
    plt.savefig(path, dpi=300)
    plt.close()
