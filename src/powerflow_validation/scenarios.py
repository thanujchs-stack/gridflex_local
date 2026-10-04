"""Scenario simulation coordinator for Phase 7 Electrical Validation.

Simulates:
1. NORMAL_DAY: Case A (Baseline) vs Case B (GridFlex 70% default)
2. PARTICIPATION: 100%, 70%, 40% participation sensitivities
3. CLOUD_EVENT: Case A (Baseline Cloud) vs Case B (GridFlex Cloud)
"""

from typing import Dict, Any, List, Tuple
import pandas as pd
import numpy as np

from src.powerflow_validation.engine import PowerFlowValidationEngine
from src.powerflow_validation.metrics import compute_electrical_scorecard, verify_causal_integrity


def run_all_validation_scenarios(
    engine: PowerFlowValidationEngine,
    dispatch_df: pd.DataFrame,
    ev_df: pd.DataFrame,
    fl_df: pd.DataFrame,
    pv_df: pd.DataFrame,
    bess_df: pd.DataFrame,
    net_load_fc_df: pd.DataFrame,
    pv_fc_df: pd.DataFrame,
) -> Dict[str, Any]:
    """Execute all Phase 7 power-flow validation scenarios.

    Returns:
        Dict containing DataFrames for:
        - powerflow_timeseries
        - phase7_bus_results
        - phase7_line_results
        - phase7_transformer_results
        - gridflex_validation_summary
        - comparison_integrity_check
        - powerflow_failures
    """
    dispatch_df = dispatch_df.copy()
    dispatch_df["timestamp"] = pd.to_datetime(dispatch_df["timestamp"])
    timesteps = sorted(dispatch_df["timestamp"].drop_duplicates().tolist())
    n_steps = len(timesteps)

    # Base uncontrollable load (residential background)
    base_load_series = []
    for i in range(n_steps):
        nl_row = net_load_fc_df.iloc[min(i, len(net_load_fc_df) - 1)]
        pv_row = pv_fc_df.iloc[min(i, len(pv_fc_df) - 1)]
        tot_fc = float(nl_row["forecast"]) + float(pv_row["forecast"])
        base_load_series.append(tot_fc)

    # Compile DER schedule dictionaries
    pv_ids = engine.pv_meta.keys()
    ev_ids = engine.ev_ids
    fl_ids = engine.flex_ids

    # 1. Baseline schedules
    pv_sched_base = {pid: [] for pid in pv_ids}
    pv_sched_opt = {pid: [] for pid in pv_ids}
    for pid in pv_ids:
        sub = pv_df[pv_df["der_id"] == pid].sort_values("timestamp")
        if not sub.empty and len(sub) == n_steps:
            pv_sched_base[pid] = sub["available_kw"].tolist()
            pv_sched_opt[pid] = sub["export_kw"].tolist()
        else:
            pv_sched_base[pid] = [0.0] * n_steps
            pv_sched_opt[pid] = [0.0] * n_steps

    ev_sched_base = {eid: [] for eid in ev_ids}
    ev_sched_opt = {eid: [] for eid in ev_ids}
    for eid in ev_ids:
        sub = ev_df[ev_df["der_id"] == eid].sort_values("timestamp")
        if not sub.empty and len(sub) == n_steps:
            # Baseline EV load includes unthrottled charging demand
            ev_sched_base[eid] = sub["throttled_kw"].tolist()
            ev_sched_opt[eid] = sub["optimized_charge_kw"].tolist()
        else:
            ev_sched_base[eid] = [0.0] * n_steps
            ev_sched_opt[eid] = [0.0] * n_steps

    fl_sched_base = {fid: [] for fid in fl_ids}
    fl_sched_opt = {fid: [] for fid in fl_ids}
    for fid in fl_ids:
        sub = fl_df[fl_df["der_id"] == fid].sort_values("timestamp")
        if not sub.empty and len(sub) == n_steps:
            fl_sched_base[fid] = sub["baseline_power_kw"].tolist()
            fl_sched_opt[fid] = sub["optimized_power_kw"].tolist()
        else:
            fl_sched_base[fid] = [0.0] * n_steps
            fl_sched_opt[fid] = [0.0] * n_steps

    bess_sched_base = [0.0] * n_steps
    bess_sched_opt = bess_df.sort_values("timestamp")["net_power_kw"].tolist() if not bess_df.empty else [0.0] * n_steps

    all_ts = []
    all_bus = []
    all_line = []
    all_trafo = []
    all_failures = []
    flex_metrics_map = {}

    # =========================================================================
    # SCENARIO 1: NORMAL_DAY (CASE A: BASELINE vs CASE B: GRIDFLEX)
    # =========================================================================
    print(" [Phase 7] Executing NORMAL_DAY: Case A (Baseline)...")
    ts_a, bus_a, line_a, trafo_a, fail_a = engine.run_case_simulation(
        scenario_name="NORMAL_DAY",
        case_name="CASE_A_BASELINE",
        timesteps=timesteps,
        base_load_series=base_load_series,
        pv_schedules=pv_sched_base,
        ev_schedules=ev_sched_base,
        fl_schedules=fl_sched_base,
        bess_schedule=bess_sched_base,
    )
    all_ts.append(ts_a)
    all_bus.append(bus_a)
    all_line.append(line_a)
    all_trafo.append(trafo_a)
    all_failures.extend(fail_a)
    flex_metrics_map[("NORMAL_DAY", "CASE_A_BASELINE")] = {
        "total_pv_curtailment_kwh": 0.0,
        "battery_discharge_kwh": 0.0,
        "ev_shifted_energy_kwh": 0.0,
        "unserved_flexibility_kwh": 0.0,
    }

    print(" [Phase 7] Executing NORMAL_DAY: Case B (GridFlex 70% Default)...")
    ts_b, bus_b, line_b, trafo_b, fail_b = engine.run_case_simulation(
        scenario_name="NORMAL_DAY",
        case_name="CASE_B_GRIDFLEX",
        timesteps=timesteps,
        base_load_series=base_load_series,
        pv_schedules=pv_sched_opt,
        ev_schedules=ev_sched_opt,
        fl_schedules=fl_sched_opt,
        bess_schedule=bess_sched_opt,
    )
    all_ts.append(ts_b)
    all_bus.append(bus_b)
    all_line.append(line_b)
    all_trafo.append(trafo_b)
    all_failures.extend(fail_b)

    # Compute actual flexibility dispatched
    ev_shifted_kwh = sum(ev_df["throttled_kw"]) * 0.25
    bess_disch_kwh = sum(max(0.0, p) for p in bess_sched_opt) * 0.25
    pv_curt_kwh = sum(pv_df["curtailed_kw"]) * 0.25
    flex_metrics_map[("NORMAL_DAY", "CASE_B_GRIDFLEX")] = {
        "total_pv_curtailment_kwh": pv_curt_kwh,
        "battery_discharge_kwh": bess_disch_kwh,
        "ev_shifted_energy_kwh": ev_shifted_kwh,
        "unserved_flexibility_kwh": 0.0,
    }

    # =========================================================================
    # SCENARIO 2: PARTICIPATION SENSITIVITIES (100%, 70%, 40%)
    # =========================================================================
    participation_rates = [1.00, 0.70, 0.40]
    for rate in participation_rates:
        pct_label = f"GRIDFLEX_{int(rate * 100)}PCT"
        print(f" [Phase 7] Executing PARTICIPATION: {pct_label}...")

        # Scale EV throttle and BESS action according to participation opt-in
        ev_sched_part = {}
        for eid in ev_ids:
            is_part = (hash(eid) % 100 < rate * 100)
            if is_part:
                ev_sched_part[eid] = ev_sched_opt[eid]
            else:
                ev_sched_part[eid] = ev_sched_base[eid]

        fl_sched_part = {}
        for fid in fl_ids:
            is_part = (hash(fid) % 100 < rate * 100)
            if is_part:
                fl_sched_part[fid] = fl_sched_opt[fid]
            else:
                fl_sched_part[fid] = fl_sched_base[fid]

        pv_sched_part = {}
        for pid in pv_ids:
            is_part = (hash(pid) % 100 < rate * 100)
            if is_part:
                pv_sched_part[pid] = pv_sched_opt[pid]
            else:
                pv_sched_part[pid] = pv_sched_base[pid]

        ts_p, bus_p, line_p, trafo_p, fail_p = engine.run_case_simulation(
            scenario_name="PARTICIPATION",
            case_name=pct_label,
            timesteps=timesteps,
            base_load_series=base_load_series,
            pv_schedules=pv_sched_part,
            ev_schedules=ev_sched_part,
            fl_schedules=fl_sched_part,
            bess_schedule=bess_sched_opt,
        )
        all_ts.append(ts_p)
        all_bus.append(bus_p)
        all_line.append(line_p)
        all_trafo.append(trafo_p)
        all_failures.extend(fail_p)
        flex_metrics_map[("PARTICIPATION", pct_label)] = {
            "total_pv_curtailment_kwh": pv_curt_kwh * rate,
            "battery_discharge_kwh": bess_disch_kwh,
            "ev_shifted_energy_kwh": ev_shifted_kwh * rate,
            "unserved_flexibility_kwh": 0.0,
        }

    # =========================================================================
    # SCENARIO 3: CLOUD_EVENT (BASELINE CLOUD vs GRIDFLEX CLOUD)
    # =========================================================================
    print(" [Phase 7] Executing CLOUD_EVENT: Case A (Baseline Cloud)...")
    cloud_factor = 0.30  # 70% irradiance dip between 15:00 and 16:00
    cloud_mask = [(t.hour == 15) for t in timesteps]

    pv_sched_cloud_base = {}
    for pid in pv_ids:
        base_pv = pv_sched_base[pid]
        pv_sched_cloud_base[pid] = [
            base_pv[k] * cloud_factor if cloud_mask[k] else base_pv[k] for k in range(n_steps)
        ]

    ts_cb, bus_cb, line_cb, trafo_cb, fail_cb = engine.run_case_simulation(
        scenario_name="CLOUD_EVENT",
        case_name="CASE_A_BASELINE_CLOUD",
        timesteps=timesteps,
        base_load_series=base_load_series,
        pv_schedules=pv_sched_cloud_base,
        ev_schedules=ev_sched_base,
        fl_schedules=fl_sched_base,
        bess_schedule=bess_sched_base,
    )
    all_ts.append(ts_cb)
    all_bus.append(bus_cb)
    all_line.append(line_cb)
    all_trafo.append(trafo_cb)
    all_failures.extend(fail_cb)
    flex_metrics_map[("CLOUD_EVENT", "CASE_A_BASELINE_CLOUD")] = {
        "total_pv_curtailment_kwh": 0.0,
        "battery_discharge_kwh": 0.0,
        "ev_shifted_energy_kwh": 0.0,
        "unserved_flexibility_kwh": 0.0,
    }

    print(" [Phase 7] Executing CLOUD_EVENT: Case B (GridFlex Cloud)...")
    pv_sched_cloud_opt = {}
    for pid in pv_ids:
        opt_pv = pv_sched_opt[pid]
        pv_sched_cloud_opt[pid] = [
            opt_pv[k] * cloud_factor if cloud_mask[k] else opt_pv[k] for k in range(n_steps)
        ]

    ts_cg, bus_cg, line_cg, trafo_cg, fail_cg = engine.run_case_simulation(
        scenario_name="CLOUD_EVENT",
        case_name="CASE_B_GRIDFLEX_CLOUD",
        timesteps=timesteps,
        base_load_series=base_load_series,
        pv_schedules=pv_sched_cloud_opt,
        ev_schedules=ev_sched_opt,
        fl_schedules=fl_sched_opt,
        bess_schedule=bess_sched_opt,
    )
    all_ts.append(ts_cg)
    all_bus.append(bus_cg)
    all_line.append(line_cg)
    all_trafo.append(trafo_cg)
    all_failures.extend(fail_cg)
    flex_metrics_map[("CLOUD_EVENT", "CASE_B_GRIDFLEX_CLOUD")] = {
        "total_pv_curtailment_kwh": pv_curt_kwh,
        "battery_discharge_kwh": bess_disch_kwh,
        "ev_shifted_energy_kwh": ev_shifted_kwh,
        "unserved_flexibility_kwh": 0.0,
    }

    # Concatenate results
    df_timeseries = pd.concat(all_ts, ignore_index=True)
    df_bus = pd.concat(all_bus, ignore_index=True)
    df_line = pd.concat(all_line, ignore_index=True)
    df_trafo = pd.concat(all_trafo, ignore_index=True)
    df_failures = (
        pd.DataFrame(all_failures)
        if all_failures
        else pd.DataFrame(columns=["timestamp", "scenario", "case", "convergence_status", "error_message"])
    )

    # Compute Summary Scorecard
    df_summary = compute_electrical_scorecard(df_timeseries, flex_metrics_map=flex_metrics_map)

    # Compute Causal Integrity
    df_integrity = verify_causal_integrity()

    return {
        "powerflow_timeseries": df_timeseries,
        "phase7_bus_results": df_bus,
        "phase7_line_results": df_line,
        "phase7_transformer_results": df_trafo,
        "gridflex_validation_summary": df_summary,
        "comparison_integrity_check": df_integrity,
        "powerflow_failures": df_failures,
    }
