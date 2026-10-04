"""Envelope Quality Metrics Calculator for GridFlex Local.

Calculates the 10 required envelope performance and quality metrics across the forecast horizon.
"""

from typing import Dict, Any
import numpy as np
import pandas as pd


def calculate_envelope_metrics(
    envelopes_df: pd.DataFrame,
    events_df: pd.DataFrame,
    timestep_hours: float = 0.25,
) -> pd.DataFrame:
    """Calculate the 10 envelope quality metrics.

    Returns:
        DataFrame summarizing metrics (envelope_summary.csv).
    """
    if envelopes_df.empty:
        return pd.DataFrame()

    # 1. Envelope Tightening: normal_capacity - dynamic_capacity
    # normal_capacity = normal_max_kw - normal_min_kw
    # dynamic_capacity = dynamic_max_kw - dynamic_min_kw
    envelopes_df = envelopes_df.copy()
    envelopes_df["normal_cap"] = envelopes_df["normal_max_kw"] - envelopes_df["normal_min_kw"]
    envelopes_df["dynamic_cap"] = envelopes_df["dynamic_max_kw"] - envelopes_df["dynamic_min_kw"]
    envelopes_df["tightening_kw"] = np.maximum(0.0, envelopes_df["normal_cap"] - envelopes_df["dynamic_cap"])

    total_tightening_kw = float(envelopes_df["tightening_kw"].sum())
    mean_tightening_kw = float(envelopes_df["tightening_kw"].mean())

    # 2. Envelope Utilization: allocated_flex_kw / max(0.001, tightening_kw)
    total_allocated_kw = float(envelopes_df["allocated_flex_kw"].sum())
    utilization_pct = (total_allocated_kw / max(0.001, total_tightening_kw) * 100.0) if total_tightening_kw > 0 else 0.0

    # 3. Percentage of timesteps with dynamic restriction
    unique_timesteps = envelopes_df["timestamp"].nunique()
    timesteps_with_restriction = envelopes_df.groupby("timestamp")["tightening_kw"].sum()
    restricted_steps_count = int((timesteps_with_restriction > 0.01).sum())
    pct_timesteps_restricted = (restricted_steps_count / max(1, unique_timesteps)) * 100.0

    # 4. Total curtailed PV capability (kWh)
    pv_df = envelopes_df[envelopes_df["der_type"] == "PV"]
    pv_curt_kw = np.maximum(0.0, pv_df["normal_max_kw"] - pv_df["dynamic_max_kw"]).sum()
    pv_curtailed_kwh = float(pv_curt_kw * timestep_hours)

    # 5. Battery flexibility reserved (average restricted charging/discharging power)
    bat_df = envelopes_df[envelopes_df["der_type"] == "BESS"]
    bat_tightening_kw = float(bat_df["tightening_kw"].sum()) if not bat_df.empty else 0.0

    # 6. EV charging flexibility restricted (kWh throttled)
    ev_df = envelopes_df[envelopes_df["der_type"] == "EV"]
    ev_tightening_kw = float(ev_df["tightening_kw"].sum()) if not ev_df.empty else 0.0
    ev_restricted_kwh = float(ev_tightening_kw * timestep_hours)

    # 7. Flexible-load range restricted (kWh)
    fl_df = envelopes_df[envelopes_df["der_type"] == "FLEXIBLE_LOAD"]
    fl_tightening_kw = float(fl_df["tightening_kw"].sum()) if not fl_df.empty else 0.0
    fl_restricted_kwh = float(fl_tightening_kw * timestep_hours)

    # 8. Number of unique DERs affected (with tightening > 0.05 kW at any time)
    der_max_tightening = envelopes_df.groupby("der_id")["tightening_kw"].max()
    affected_ders_count = int((der_max_tightening > 0.05).sum())

    # 9. Number of constraint events
    num_constraint_events = len(events_df[events_df["new_state"].isin(["CONSTRAINED", "WATCH"])])

    # 10. Average envelope recovery time (minutes between entering restriction and returning to NORMAL)
    recovery_times_min = []
    if not events_df.empty:
        for der_id, g in events_df.groupby("der_id"):
            enter_t = None
            for _, r in g.sort_values("timestamp").iterrows():
                if r["new_state"] in ["CONSTRAINED", "WATCH"] and enter_t is None:
                    enter_t = pd.to_datetime(r["timestamp"])
                elif r["new_state"] == "NORMAL" and enter_t is not None:
                    recovery_times_min.append((pd.to_datetime(r["timestamp"]) - enter_t).total_seconds() / 60.0)
                    enter_t = None
    avg_recovery_min = float(np.mean(recovery_times_min)) if recovery_times_min else 0.0

    metrics_records = [
        {"metric_name": "total_envelope_tightening_kw", "metric_value": round(total_tightening_kw, 2), "unit": "kW"},
        {"metric_name": "mean_envelope_tightening_kw", "metric_value": round(mean_tightening_kw, 2), "unit": "kW"},
        {"metric_name": "envelope_utilization_pct", "metric_value": round(utilization_pct, 2), "unit": "%"},
        {"metric_name": "pct_timesteps_restricted", "metric_value": round(pct_timesteps_restricted, 2), "unit": "%"},
        {"metric_name": "total_curtailed_pv_kwh", "metric_value": round(pv_curtailed_kwh, 3), "unit": "kWh"},
        {"metric_name": "battery_flexibility_reserved_kw", "metric_value": round(bat_tightening_kw, 2), "unit": "kW"},
        {"metric_name": "ev_charging_restricted_kwh", "metric_value": round(ev_restricted_kwh, 3), "unit": "kWh"},
        {"metric_name": "flexible_load_restricted_kwh", "metric_value": round(fl_restricted_kwh, 3), "unit": "kWh"},
        {"metric_name": "number_of_ders_affected", "metric_value": affected_ders_count, "unit": "count"},
        {"metric_name": "number_of_constraint_events", "metric_value": num_constraint_events, "unit": "count"},
        {"metric_name": "average_envelope_recovery_minutes", "metric_value": round(avg_recovery_min, 1), "unit": "minutes"},
    ]

    return pd.DataFrame(metrics_records)
