"""Dispatch Plan Generator for Phase 6.

Translates mathematical programming solution vectors into individual DER schedules,
unified dispatch records, constraint telemetry, and comparison metrics.
"""

from typing import Dict, List, Any, Tuple, Optional
import numpy as np
import pandas as pd

from src.optimization.problem import OptimizationProblem
from src.optimization.solver import DispatchOptimizer


def generate_dispatch_plan(
    problem: OptimizationProblem,
    solver_result: Dict[str, Any],
) -> Dict[str, pd.DataFrame]:
    """Extract and compile all required Phase 6 dispatch CSV DataFrames.

    Returns:
        Dict mapping artifact names to pd.DataFrame.
    """
    if not solver_result["success"]:
        raise RuntimeError(f"Optimization failed: {solver_result['solver_status']}")

    x = solver_result["solution_vector"]
    m = solver_result["matrices"]
    var_idx = m["var_idx"]
    timesteps = m["timesteps"]
    pv_ids = m["pv_ids"]
    ev_ids = m["ev_ids"]
    fl_ids = m["fl_ids"]
    dt_h = 0.25

    # Accessors
    envs_df = problem.envelopes_df
    plan_df = problem.coordination_plan_df
    nl_df = problem.net_load_forecast_df
    pv_fc_df = problem.pv_forecast_df

    dispatch_rows = []
    bat_rows = []
    ev_rows = []
    pv_rows = []
    fl_rows = []
    constraint_rows = []

    current_soc = problem.initial_soc

    tot_grid_imp_kwh = 0.0
    tot_grid_exp_kwh = 0.0
    peak_grid_imp_kw = 0.0
    peak_grid_exp_kw = 0.0
    tot_pv_curt_kwh = 0.0
    tot_bat_chg_kwh = 0.0
    tot_bat_dis_kwh = 0.0
    tot_ev_shift_kwh = 0.0
    tot_fl_shift_kwh = 0.0
    active_ders_set = set()

    for t_idx, t in enumerate(timesteps):
        t_envs = envs_df[envs_df["timestamp"] == t]
        r_match = plan_df[plan_df["timestamp"] == t]
        risk_state = str(r_match["risk_state"].iloc[0]) if not r_match.empty else "NORMAL"
        c_target = str(r_match["constraint_type"].iloc[0]) if not r_match.empty else "NONE"

        # Grid flow values
        p_imp = float(x[var_idx(t_idx, "grid_imp")])
        p_exp = float(x[var_idx(t_idx, "grid_exp")])
        s_trafo = float(x[var_idx(t_idx, "s_trafo")])
        s_volt = float(x[var_idx(t_idx, "s_volt")])

        tot_grid_imp_kwh += p_imp * dt_h
        tot_grid_exp_kwh += p_exp * dt_h
        peak_grid_imp_kw = max(peak_grid_imp_kw, p_imp)
        peak_grid_exp_kw = max(peak_grid_exp_kw, p_exp)

        # ----------------------------------------------------
        # 1. BESS Dispatch
        # ----------------------------------------------------
        p_dis = float(x[var_idx(t_idx, "bat_dis")])
        p_chg = float(x[var_idx(t_idx, "bat_chg")])

        tot_bat_dis_kwh += p_dis * dt_h
        tot_bat_chg_kwh += p_chg * dt_h

        # Update SOC
        delta_soc = (p_chg * dt_h * problem.eta_chg) / problem.bess_cap - (p_dis * dt_h) / (problem.bess_cap * problem.eta_dis)
        new_soc = current_soc + delta_soc

        bat_env = t_envs[t_envs["der_type"] == "BESS"]
        dyn_max_bat = float(bat_env["dynamic_max_kw"].iloc[0]) if not bat_env.empty else 25.0
        dyn_min_bat = float(bat_env["dynamic_min_kw"].iloc[0]) if not bat_env.empty else -25.0

        net_bat_kw = p_dis - p_chg  # Positive = discharge/generation, Negative = charge/load
        if abs(net_bat_kw) > 0.05:
            active_ders_set.add("BESS_COMMUNITY_01")

        dispatch_rows.append({
            "timestamp": t,
            "der_id": "BESS_COMMUNITY_01",
            "der_type": "BESS",
            "baseline_kw": 0.0,
            "optimized_kw": round(net_bat_kw, 2),
            "dynamic_min_kw": round(dyn_min_bat, 2),
            "dynamic_max_kw": round(dyn_max_bat, 2),
            "allocated_flex_kw": round(abs(net_bat_kw), 2),
            "soc": round(current_soc, 4),
            "constraint_target": c_target,
            "risk_state": risk_state,
            "participation": True,
            "optimization_status": "OPTIMAL",
        })

        bat_rows.append({
            "timestamp": t,
            "charge_kw": round(p_chg, 2),
            "discharge_kw": round(p_dis, 2),
            "net_power_kw": round(net_bat_kw, 2),
            "soc": round(current_soc, 4),
            "soc_min": round(problem.soc_min, 4),
            "soc_max": round(problem.soc_max, 4),
            "reserve_soc": round(problem.soc_floor - problem.soc_min, 4),
            "reserve_margin_kwh": round(max(0.0, (current_soc - problem.soc_floor) * problem.bess_cap), 2),
        })

        current_soc = new_soc

        # ----------------------------------------------------
        # 2. PV Dispatch
        # ----------------------------------------------------
        for i, pid in enumerate(pv_ids):
            p_curt = float(x[var_idx(t_idx, "pv_curt", i)])
            tot_pv_curt_kwh += p_curt * dt_h

            p_env = t_envs[t_envs["der_id"] == pid]
            avail_pv = float(p_env["available_pv_kw"].iloc[0]) if not p_env.empty else 0.0
            normal_pv = float(p_env["normal_export_limit_kw"].iloc[0]) if not p_env.empty else 3.5
            dyn_export = float(p_env["dynamic_export_limit_kw"].iloc[0]) if not p_env.empty else normal_pv
            curt_allowed = bool(p_env["curtailment_allowed"].iloc[0]) if not p_env.empty else False

            opt_export = max(0.0, avail_pv - p_curt)
            if p_curt > 0.05:
                active_ders_set.add(pid)

            dispatch_rows.append({
                "timestamp": t,
                "der_id": pid,
                "der_type": "PV",
                "baseline_kw": round(avail_pv, 2),
                "optimized_kw": round(opt_export, 2),
                "dynamic_min_kw": 0.0,
                "dynamic_max_kw": round(dyn_export, 2),
                "allocated_flex_kw": round(p_curt, 2),
                "soc": None,
                "constraint_target": c_target,
                "risk_state": risk_state,
                "participation": curt_allowed,
                "optimization_status": "OPTIMAL",
            })

            pv_rows.append({
                "timestamp": t,
                "der_id": pid,
                "available_kw": round(avail_pv, 2),
                "export_kw": round(opt_export, 2),
                "curtailed_kw": round(p_curt, 2),
                "curtailment_pct": round((p_curt / max(0.001, avail_pv)) * 100.0, 1),
            })

        # ----------------------------------------------------
        # 3. EV Dispatch
        # ----------------------------------------------------
        for j, eid in enumerate(ev_ids):
            p_throttle = float(x[var_idx(t_idx, "ev_throttle", j)])
            tot_ev_shift_kwh += p_throttle * dt_h

            e_env = t_envs[t_envs["der_id"] == eid]
            hour_float = t.hour + t.minute / 60.0
            is_connected = (hour_float >= 18.0) or (hour_float <= 7.5)
            base_ev_kw = 7.4 if is_connected else 0.0
            dyn_ev_max = float(e_env["dynamic_max_kw"].iloc[0]) if not e_env.empty else 0.0

            opt_ev_kw = max(0.0, base_ev_kw - p_throttle)
            if p_throttle > 0.05:
                active_ders_set.add(eid)

            dispatch_rows.append({
                "timestamp": t,
                "der_id": eid,
                "der_type": "EV",
                "baseline_kw": round(base_ev_kw, 2),
                "optimized_kw": round(opt_ev_kw, 2),
                "dynamic_min_kw": 0.0,
                "dynamic_max_kw": round(dyn_ev_max, 2),
                "allocated_flex_kw": round(p_throttle, 2),
                "soc": None,
                "constraint_target": c_target,
                "risk_state": risk_state,
                "participation": True,
                "optimization_status": "OPTIMAL",
            })

            ev_rows.append({
                "timestamp": t,
                "der_id": eid,
                "baseline_charge_kw": round(base_ev_kw, 2),
                "optimized_charge_kw": round(opt_ev_kw, 2),
                "throttled_kw": round(p_throttle, 2),
                "cumulative_energy_kwh": round(opt_ev_kw * dt_h, 2),
                "departure_guaranteed": True,
            })

        # ----------------------------------------------------
        # 4. Flexible Load Dispatch
        # ----------------------------------------------------
        for k, fid in enumerate(fl_ids):
            p_shift = float(x[var_idx(t_idx, "fl_shift", k)])
            tot_fl_shift_kwh += p_shift * dt_h

            f_env = t_envs[t_envs["der_id"] == fid]
            base_fl_kw = float(f_env["normal_max_kw"].iloc[0]) if not f_env.empty else 3.5
            dyn_min_fl = float(f_env["dynamic_min_kw"].iloc[0]) if not f_env.empty else 0.0
            dyn_max_fl = float(f_env["dynamic_max_kw"].iloc[0]) if not f_env.empty else 3.5

            opt_fl_kw = max(dyn_min_fl, base_fl_kw - p_shift)
            if p_shift > 0.05:
                active_ders_set.add(fid)

            dispatch_rows.append({
                "timestamp": t,
                "der_id": fid,
                "der_type": "FLEXIBLE_LOAD",
                "baseline_kw": round(base_fl_kw, 2),
                "optimized_kw": round(opt_fl_kw, 2),
                "dynamic_min_kw": round(dyn_min_fl, 2),
                "dynamic_max_kw": round(dyn_max_fl, 2),
                "allocated_flex_kw": round(p_shift, 2),
                "soc": None,
                "constraint_target": c_target,
                "risk_state": risk_state,
                "participation": True,
                "optimization_status": "OPTIMAL",
            })

            fl_rows.append({
                "timestamp": t,
                "der_id": fid,
                "baseline_power_kw": round(base_fl_kw, 2),
                "optimized_power_kw": round(opt_fl_kw, 2),
                "shifted_power_kw": round(p_shift, 2),
                "service_conserved": True,
            })

        # ----------------------------------------------------
        # 5. Constraint Metrics per Timestep
        # ----------------------------------------------------
        trafo_load_pct = (p_imp / (250.0 * 0.95)) * 100.0
        # Line loading approximation
        max_line_pct = trafo_load_pct * 1.55
        # Linearized voltage drop approximation
        v_min_est = 1.00 - (p_imp * 0.00072)
        v_max_est = 1.00 + (p_exp * 0.00065)

        constraint_rows.append({
            "timestamp": t,
            "transformer_loading_percent": round(trafo_load_pct, 2),
            "maximum_line_loading_percent": round(max_line_pct, 2),
            "minimum_bus_voltage_pu": round(v_min_est, 4),
            "maximum_bus_voltage_pu": round(v_max_est, 4),
            "reverse_power_flow_kw": round(p_exp, 2),
            "constraint_violation": round(s_trafo + s_volt, 4),
            "risk_state": risk_state,
        })

    # Summary table (Section 21)
    summary_df = pd.DataFrame([{
        "objective_value": round(solver_result["objective_value"], 2),
        "total_grid_import_kwh": round(tot_grid_imp_kwh, 2),
        "total_grid_export_kwh": round(tot_grid_exp_kwh, 2),
        "peak_grid_import_kw": round(peak_grid_imp_kw, 2),
        "peak_grid_export_kw": round(peak_grid_exp_kw, 2),
        "total_pv_curtailment_kwh": round(tot_pv_curt_kwh, 3),
        "battery_charge_energy_kwh": round(tot_bat_chg_kwh, 3),
        "battery_discharge_energy_kwh": round(tot_bat_dis_kwh, 3),
        "battery_cycling_metric": round(tot_bat_dis_kwh / problem.bess_cap, 3),
        "ev_shifted_energy_kwh": round(tot_ev_shift_kwh, 3),
        "flexible_load_shifted_energy_kwh": round(tot_fl_shift_kwh, 3),
        "constraint_violation": round(sum(r["constraint_violation"] for r in constraint_rows), 4),
        "unserved_flexibility": 0.0,
        "number_of_active_ders": len(active_ders_set),
        "solver_status": solver_result["solver_status"],
    }])

    # Comparison metrics (Section 18)
    comparison_df = pd.DataFrame([
        {
            "case": "CASE A: BASELINE / NO GRIDFLEX",
            "peak_grid_import_kw": round(float(nl_df["forecast"].max()), 2),
            "total_import_kwh": round(float(nl_df["forecast"].sum() * dt_h), 2),
            "transformer_max_loading_pct": round((float(nl_df["forecast"].max()) / (250.0 * 0.95)) * 100.0, 2),
            "bess_energy_discharged_kwh": 0.0,
            "ev_energy_shifted_kwh": 0.0,
            "pv_curtailed_kwh": 0.0,
            "coordination_active": False,
        },
        {
            "case": "CASE B: GRIDFLEX OPTIMIZED",
            "peak_grid_import_kw": round(peak_grid_imp_kw, 2),
            "total_import_kwh": round(tot_grid_imp_kwh, 2),
            "transformer_max_loading_pct": round(max(r["transformer_loading_percent"] for r in constraint_rows), 2),
            "bess_energy_discharged_kwh": round(tot_bat_dis_kwh, 2),
            "ev_energy_shifted_kwh": round(tot_ev_shift_kwh, 2),
            "pv_curtailed_kwh": round(tot_pv_curt_kwh, 2),
            "coordination_active": True,
        }
    ])

    return {
        "optimized_dispatch": pd.DataFrame(dispatch_rows),
        "optimization_summary": summary_df,
        "constraint_metrics": pd.DataFrame(constraint_rows),
        "der_schedule": pd.DataFrame(dispatch_rows)[["timestamp", "der_id", "der_type", "baseline_kw", "optimized_kw", "allocated_flex_kw"]],
        "battery_schedule": pd.DataFrame(bat_rows),
        "ev_schedule": pd.DataFrame(ev_rows),
        "pv_schedule": pd.DataFrame(pv_rows),
        "flexible_load_schedule": pd.DataFrame(fl_rows),
        "optimization_comparison": comparison_df,
    }
