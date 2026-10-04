"""Plotting and visualization routines for Phase 5 Dynamic Operating Envelopes.

Generates the 9 required publication-quality diagnostic plots in outputs/plots/.
"""

from pathlib import Path
from typing import Dict, Any, List
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


def generate_all_envelope_plots(
    envelopes_df: pd.DataFrame,
    pv_envelopes_df: pd.DataFrame,
    battery_envelopes_df: pd.DataFrame,
    ev_envelopes_df: pd.DataFrame,
    fl_envelopes_df: pd.DataFrame,
    validation_df: pd.DataFrame,
    output_dir: Path = Path("outputs/plots"),
):
    """Generate all 9 required plots for Phase 5."""
    output_dir.mkdir(parents=True, exist_ok=True)
    plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")

    # 1. dynamic_pv_envelopes.png
    _plot_dynamic_pv_envelopes(pv_envelopes_df, output_dir / "dynamic_pv_envelopes.png")

    # 2. battery_charge_discharge_envelopes.png
    _plot_battery_envelopes(battery_envelopes_df, output_dir / "battery_charge_discharge_envelopes.png")

    # 3. ev_charging_envelopes.png
    _plot_ev_envelopes(ev_envelopes_df, output_dir / "ev_charging_envelopes.png")

    # 4. flexible_load_envelopes.png
    _plot_flexible_load_envelopes(fl_envelopes_df, output_dir / "flexible_load_envelopes.png")

    # 5. envelope_timeline.png
    _plot_envelope_timeline(envelopes_df, output_dir / "envelope_timeline.png")

    # 6. constraint_vs_envelope.png
    _plot_constraint_vs_envelope(envelopes_df, validation_df, output_dir / "constraint_vs_envelope.png")

    # 7. baseline_vs_dynamic_loading.png
    _plot_baseline_vs_dynamic_loading(validation_df, output_dir / "baseline_vs_dynamic_loading.png")

    # 8. baseline_vs_dynamic_voltage.png
    _plot_baseline_vs_dynamic_voltage(validation_df, output_dir / "baseline_vs_dynamic_voltage.png")

    # 9. envelope_restriction_heatmap.png
    _plot_envelope_restriction_heatmap(envelopes_df, output_dir / "envelope_restriction_heatmap.png")


def _plot_dynamic_pv_envelopes(df: pd.DataFrame, path: Path):
    fig, axes = plt.subplots(2, 2, figsize=(14, 9), sharex=True)
    axes = axes.flatten()
    sample_ids = ["PV_H002", "PV_H005", "PV_H006", "PV_H021"]
    sample_ids = [sid for sid in sample_ids if sid in df["der_id"].values][:4]
    if len(sample_ids) < 4:
        sample_ids = df["der_id"].drop_duplicates().iloc[:4].tolist()

    for idx, sid in enumerate(sample_ids):
        ax = axes[idx]
        sub = df[df["der_id"] == sid].sort_values("timestamp")
        times = [pd.to_datetime(t).strftime("%H:%M") for t in sub["timestamp"]]
        ax.plot(times, sub["normal_export_limit_kw"], "k--", label="Normal Export Limit (kW)", linewidth=1.5)
        ax.plot(times, sub["available_pv_kw"], color="#f39c12", label="Available PV (kW)", linewidth=2)
        ax.step(times, sub["dynamic_export_limit_kw"], color="#27ae60", where="mid", label="Dynamic Export Envelope (kW)", linewidth=2.5)
        ax.fill_between(times, 0, sub["dynamic_export_limit_kw"], color="#2ecc71", alpha=0.15)
        ax.set_title(f"DER: {sid} (Curtailment Allowed: {sub['curtailment_allowed'].iloc[0]})", fontsize=11, fontweight="bold")
        ax.set_ylabel("Power (kW)")
        ax.grid(True, linestyle="--", alpha=0.6)
        if idx == 0:
            ax.legend(loc="upper right", fontsize=9)
        plt.setp(ax.get_xticklabels(), rotation=45, ha="right")

    fig.suptitle("GridFlex Local — Dynamic Rooftop PV Export Operating Envelopes", fontsize=14, fontweight="bold")
    plt.tight_layout()
    plt.savefig(path, dpi=300)
    plt.close()


def _plot_battery_envelopes(df: pd.DataFrame, path: Path):
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
    sub = df.sort_values("timestamp")
    times = [pd.to_datetime(t).strftime("%H:%M") for t in sub["timestamp"]]

    # Limits
    ax1.step(times, sub["dynamic_discharge_limit_kw"], color="#2980b9", where="mid", label="Dynamic Discharge Limit (kW)", linewidth=2.5)
    ax1.step(times, -sub["dynamic_charge_limit_kw"], color="#8e44ad", where="mid", label="Dynamic Charge Limit (kW, Load)", linewidth=2.5)
    ax1.axhline(25.0, color="gray", linestyle=":", label="Max Discharge Rating (25 kW)")
    ax1.axhline(-25.0, color="gray", linestyle="--", label="Max Charge Rating (25 kW)")
    ax1.fill_between(times, -sub["dynamic_charge_limit_kw"], sub["dynamic_discharge_limit_kw"], color="#3498db", alpha=0.12)
    ax1.set_ylabel("Permitted Power (kW)", fontsize=11)
    ax1.set_title("Community Battery Permitted Operating Range", fontsize=12, fontweight="bold")
    ax1.legend(loc="upper right", fontsize=9)
    ax1.grid(True, linestyle="--", alpha=0.6)

    # SOC
    soc_pct = sub["soc"] * 100.0
    ax2.plot(times, soc_pct, color="#e67e22", marker="o", linewidth=2.2, label="Battery SOC (%)")
    ax2.axhline(30.0, color="#c0392b", linestyle="--", linewidth=1.8, label="Physical Floor (30% = 20% Min + 10% Reserve)")
    ax2.axhline(90.0, color="#27ae60", linestyle=":", linewidth=1.5, label="Max SOC Limit (90%)")
    ax2.set_ylabel("State of Charge (%)", fontsize=11)
    ax2.set_xlabel("Forecast Timestamp (15-min intervals)", fontsize=11)
    ax2.set_ylim(15, 95)
    ax2.legend(loc="upper right", fontsize=9)
    ax2.grid(True, linestyle="--", alpha=0.6)
    plt.setp(ax2.get_xticklabels(), rotation=45, ha="right")

    fig.suptitle("GridFlex Local — Community Battery Operating Envelope & State Tracking", fontsize=14, fontweight="bold")
    plt.tight_layout()
    plt.savefig(path, dpi=300)
    plt.close()


def _plot_ev_envelopes(df: pd.DataFrame, path: Path):
    fig, axes = plt.subplots(2, 2, figsize=(14, 8), sharex=True)
    axes = axes.flatten()
    ev_ids = df["der_id"].drop_duplicates().iloc[:4].tolist()

    for idx, eid in enumerate(ev_ids):
        ax = axes[idx]
        sub = df[df["der_id"] == eid].sort_values("timestamp")
        times = [pd.to_datetime(t).strftime("%H:%M") for t in sub["timestamp"]]
        ax.plot(times, sub["max_charge_kw"], "k--", label="Rated Charger Limit (7.4 kW)", linewidth=1.2)
        ax.step(times, sub["dynamic_charge_limit_kw"], color="#16a085", where="mid", label="Dynamic Charging Envelope (kW)", linewidth=2.5)
        ax.fill_between(times, 0, sub["dynamic_charge_limit_kw"], color="#1abc9c", alpha=0.15)
        ax.set_title(f"Electric Vehicle: {eid}", fontsize=11, fontweight="bold")
        ax.set_ylabel("Charge Power (kW)")
        ax.set_ylim(-0.5, 8.5)
        ax.grid(True, linestyle="--", alpha=0.6)
        if idx == 0:
            ax.legend(loc="upper right", fontsize=9)
        plt.setp(ax.get_xticklabels(), rotation=45, ha="right")

    fig.suptitle("GridFlex Local — EV Smart Charging Dynamic Operating Envelopes", fontsize=14, fontweight="bold")
    plt.tight_layout()
    plt.savefig(path, dpi=300)
    plt.close()


def _plot_flexible_load_envelopes(df: pd.DataFrame, path: Path):
    fig, axes = plt.subplots(len(df["der_id"].unique()), 1, figsize=(12, 3.5 * len(df["der_id"].unique())), sharex=True)
    if not isinstance(axes, (list, np.ndarray)):
        axes = [axes]

    for idx, (fid, sub) in enumerate(df.groupby("der_id")):
        ax = axes[idx]
        sub = sub.sort_values("timestamp")
        times = [pd.to_datetime(t).strftime("%H:%M") for t in sub["timestamp"]]
        ax.plot(times, sub["baseline_kw"], "k--", label="Baseline Rated Power (kW)", linewidth=1.5)
        ax.plot(times, sub["minimum_kw"], "r:", label="Standby Minimum (kW)", linewidth=1.5)
        ax.step(times, sub["dynamic_max_kw"], color="#e74c3c", where="mid", label="Dynamic Upper Operating Bound (kW)", linewidth=2.5)
        ax.fill_between(times, sub["dynamic_min_kw"], sub["dynamic_max_kw"], color="#e74c3c", alpha=0.15, label="Permitted Operating Window")
        ax.set_title(f"Flexible Load: {fid} (Availability: {sub['availability_window'].iloc[0]})", fontsize=11, fontweight="bold")
        ax.set_ylabel("Power (kW)")
        ax.grid(True, linestyle="--", alpha=0.6)
        if idx == 0:
            ax.legend(loc="upper right", fontsize=9)
        plt.setp(ax.get_xticklabels(), rotation=45, ha="right")

    fig.suptitle("GridFlex Local — Flexible Load Dynamic Operating Envelopes", fontsize=14, fontweight="bold")
    plt.tight_layout()
    plt.savefig(path, dpi=300)
    plt.close()


def _plot_envelope_timeline(df: pd.DataFrame, path: Path):
    fig, ax = plt.subplots(figsize=(13, 6))
    times = df["timestamp"].drop_duplicates().sort_values().tolist()
    time_strs = [pd.to_datetime(t).strftime("%H:%M") for t in times]

    # Aggregate normal vs dynamic capacities across all DERs
    t_groups = df.groupby("timestamp")
    norm_caps = [t_groups.get_group(t)["normal_max_kw"].sum() for t in times]
    dyn_caps = [t_groups.get_group(t)["dynamic_max_kw"].sum() for t in times]

    ax.plot(time_strs, norm_caps, "k--", label="Total Normal Feeder Capacity (kW)", linewidth=2)
    ax.step(time_strs, dyn_caps, color="#2c3e50", where="mid", label="Total Dynamic Envelope Capacity (kW)", linewidth=2.8)
    ax.fill_between(time_strs, dyn_caps, norm_caps, color="#e74c3c", alpha=0.25, label="Envelope Restriction / Capacity Held")

    # Shading risk states
    risk_states = [t_groups.get_group(t)["risk_state"].iloc[0] for t in times]
    for i, r in enumerate(risk_states):
        if r == "WATCH":
            ax.axvspan(i - 0.5, i + 0.5, color="#f1c40f", alpha=0.15)
        elif r in ["CONSTRAINED", "CRITICAL"]:
            ax.axvspan(i - 0.5, i + 0.5, color="#e74c3c", alpha=0.20)

    ax.set_title("GridFlex Local — Total Neighbourhood Dynamic Operating Envelope Timeline", fontsize=13, fontweight="bold")
    ax.set_xlabel("Forecast Timestamp (15-min horizon)", fontsize=11)
    ax.set_ylabel("Aggregate Feeder DER Capacity (kW)", fontsize=11)
    ax.legend(loc="lower left", fontsize=10)
    ax.grid(True, linestyle="--", alpha=0.6)
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right")
    plt.tight_layout()
    plt.savefig(path, dpi=300)
    plt.close()


def _plot_constraint_vs_envelope(envelopes_df: pd.DataFrame, val_df: pd.DataFrame, path: Path):
    fig, ax1 = plt.subplots(figsize=(12, 6))
    times = val_df["timestamp"]
    time_strs = [pd.to_datetime(t).strftime("%H:%M") for t in times]

    # Tightening
    t_groups = envelopes_df.groupby("timestamp")
    tightening = [(t_groups.get_group(t)["normal_max_kw"].sum() - t_groups.get_group(t)["dynamic_max_kw"].sum()) for t in times]

    color = "#e74c3c"
    ax1.set_xlabel("Timestamp", fontsize=11)
    ax1.set_ylabel("Aggregate Envelope Tightening (kW)", color=color, fontsize=11)
    ax1.bar(time_strs, tightening, color=color, alpha=0.6, width=0.5, label="Envelope Tightening (kW)")
    ax1.tick_params(axis="y", labelcolor=color)
    plt.setp(ax1.get_xticklabels(), rotation=45, ha="right")

    ax2 = ax1.twinx()
    color2 = "#2980b9"
    ax2.set_ylabel("Substation Transformer Loading (%)", color=color2, fontsize=11)
    ax2.plot(time_strs, val_df["baseline_trafo_loading_pct"], color=color2, marker="s", linewidth=2, label="Baseline Trafo Loading (%)")
    ax2.axhline(80.0, color="orange", linestyle="--", label="Warning Threshold (80%)")
    ax2.tick_params(axis="y", labelcolor=color2)

    fig.suptitle("Feeder Constraint Severity vs Dynamic Operating Envelope Tightening", fontsize=13, fontweight="bold")
    plt.tight_layout()
    plt.savefig(path, dpi=300)
    plt.close()


def _plot_baseline_vs_dynamic_loading(val_df: pd.DataFrame, path: Path):
    fig, ax = plt.subplots(figsize=(12, 6))
    times = [pd.to_datetime(t).strftime("%H:%M") for t in val_df["timestamp"]]

    ax.plot(times, val_df["baseline_trafo_loading_pct"], color="#c0392b", marker="o", linewidth=2.2, label="Case A: Static Baseline Loading (%)")
    ax.plot(times, val_df["dynamic_trafo_loading_pct"], color="#27ae60", marker="^", linewidth=2.5, label="Case B: Dynamic Envelope Loading (%)")
    ax.axhline(80.0, color="#d35400", linestyle="--", linewidth=1.5, label="Warning Threshold (80%)")
    ax.axhline(100.0, color="#c0392b", linestyle=":", linewidth=1.5, label="Rating Limit (100%)")
    ax.fill_between(times, val_df["dynamic_trafo_loading_pct"], val_df["baseline_trafo_loading_pct"], color="#2ecc71", alpha=0.2, label="Feeder Loading Relief")

    ax.set_title("GridFlex Local — Transformer Loading: Static Baseline vs Dynamic DOE", fontsize=13, fontweight="bold")
    ax.set_xlabel("Forecast Timestamp", fontsize=11)
    ax.set_ylabel("Transformer Loading (%)", fontsize=11)
    ax.legend(loc="upper left", fontsize=10)
    ax.grid(True, linestyle="--", alpha=0.6)
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right")
    plt.tight_layout()
    plt.savefig(path, dpi=300)
    plt.close()


def _plot_baseline_vs_dynamic_voltage(val_df: pd.DataFrame, path: Path):
    fig, ax = plt.subplots(figsize=(12, 6))
    times = [pd.to_datetime(t).strftime("%H:%M") for t in val_df["timestamp"]]

    ax.plot(times, val_df["baseline_min_vm_pu"], color="#e74c3c", marker="o", linewidth=2.2, label="Case A: Static Baseline Min Voltage (pu)")
    ax.plot(times, val_df["dynamic_min_vm_pu"], color="#2980b9", marker="^", linewidth=2.5, label="Case B: Dynamic Envelope Min Voltage (pu)")
    ax.axhline(0.940, color="#c0392b", linestyle="--", linewidth=1.8, label="Statutory Undervoltage Limit (0.940 pu)")
    ax.axhline(0.950, color="#e67e22", linestyle=":", linewidth=1.5, label="Precautionary Warning Threshold (0.950 pu)")
    ax.fill_between(times, val_df["baseline_min_vm_pu"], val_df["dynamic_min_vm_pu"], color="#3498db", alpha=0.2, label="Voltage Support Improvement")

    ax.set_title("GridFlex Local — Feeder Minimum Bus Voltage: Case A vs Case B", fontsize=13, fontweight="bold")
    ax.set_xlabel("Forecast Timestamp", fontsize=11)
    ax.set_ylabel("Bus Voltage (p.u.)", fontsize=11)
    ax.legend(loc="lower left", fontsize=10)
    ax.grid(True, linestyle="--", alpha=0.6)
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right")
    plt.tight_layout()
    plt.savefig(path, dpi=300)
    plt.close()


def _plot_envelope_restriction_heatmap(df: pd.DataFrame, path: Path):
    fig, ax = plt.subplots(figsize=(14, 8))
    # Select representative DER sample (e.g. 20 DERs spanning types)
    sample_ders = (
        ["BESS_COMMUNITY_01"]
        + df[df["der_type"] == "FL"]["der_id"].drop_duplicates().tolist()
        + df[df["der_type"] == "EV"]["der_id"].drop_duplicates().iloc[:5].tolist()
        + df[df["der_type"] == "PV"]["der_id"].drop_duplicates().iloc[:12].tolist()
    )
    sample_ders = [did for did in sample_ders if did in df["der_id"].values]

    sub = df[df["der_id"].isin(sample_ders)].copy()
    sub["restriction_pct"] = np.maximum(
        0.0,
        (sub["normal_max_kw"] - sub["dynamic_max_kw"]) / np.maximum(0.001, sub["normal_max_kw"]) * 100.0
    )

    pivot = sub.pivot(index="der_id", columns="timestamp", values="restriction_pct")
    pivot.columns = [pd.to_datetime(c).strftime("%H:%M") for c in pivot.columns]

    cax = ax.imshow(pivot.values, cmap="YlOrRd", aspect="auto", vmin=0, vmax=100)
    ax.set_xticks(range(len(pivot.columns)))
    ax.set_xticklabels(pivot.columns, rotation=45, ha="right")
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels(pivot.index, fontsize=9)

    cbar = fig.colorbar(cax, ax=ax)
    cbar.set_label("Envelope Restriction Level (%)", fontsize=11)

    ax.set_title("Dynamic Operating Envelope Restriction Heatmap across Horizon", fontsize=13, fontweight="bold")
    ax.set_xlabel("Timestamp", fontsize=11)
    ax.set_ylabel("DER Identifier", fontsize=11)
    plt.tight_layout()
    plt.savefig(path, dpi=300)
    plt.close()
