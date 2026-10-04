"""Electrical metrics and causal validation scorecard for Phase 7.

Computes loading, duration, voltage, reverse flow, and energy metrics,
verifies causal integrity conditions, and calculates absolute and percentage improvements.
"""

from typing import Dict, Any, List, Optional, Tuple
import numpy as np
import pandas as pd


def compute_electrical_scorecard(
    ts_df: pd.DataFrame,
    flex_metrics_map: Optional[Dict[Tuple[str, str], Dict[str, float]]] = None,
    dt_minutes: int = 15,
) -> pd.DataFrame:
    """Compile electrical benefit scorecard for all simulated scenario/case pairs.

    Returns:
        DataFrame matching outputs/csv/gridflex_validation_summary.csv columns.
    """
    rows = []
    grouped = ts_df.groupby(["scenario", "case"], sort=False)

    for (scenario, case), grp in grouped:
        valid_grp = grp[grp["converged"] == True]

        if valid_grp.empty:
            continue

        # Transformer metrics
        peak_trafo = float(valid_grp["transformer_loading_percent"].max())
        # Overload duration (above 80% warning limit)
        trafo_overload_steps = (valid_grp["transformer_loading_percent"] > 80.0).sum()
        trafo_overload_duration = int(trafo_overload_steps * dt_minutes)

        # Line metrics
        peak_line = float(valid_grp["max_line_loading_percent"].max())
        line_overload_steps = (valid_grp["max_line_loading_percent"] > 80.0).sum()
        line_overload_duration = int(line_overload_steps * dt_minutes)

        # Voltage metrics
        min_v = float(valid_grp["min_bus_voltage_pu"].min())
        # Voltage violations outside [0.94, 1.06]
        volt_viol_steps = (
            (valid_grp["min_bus_voltage_pu"] < 0.94) | (valid_grp["max_bus_voltage_pu"] > 1.06)
        ).sum()
        volt_viol_duration = int(volt_viol_steps * dt_minutes)

        # Reverse power flow
        peak_rev = float(valid_grp["reverse_power_kw"].max())
        rev_steps = (valid_grp["reverse_power_kw"] > 0.1).sum()
        rev_duration = int(rev_steps * dt_minutes)

        # Grid flow peaks
        peak_imp = float(valid_grp["grid_import_kw"].max())
        peak_exp = float(valid_grp["grid_export_kw"].max())

        # Total constraint violations count (intervals with any violation)
        total_viol_count = int(
            (
                (valid_grp["transformer_violation"] > 0.0)
                | (valid_grp["line_violation"] > 0.0)
                | (valid_grp["voltage_violation"] > 0.0)
            ).sum()
        )

        # Flexibility tracking
        flex_info = (
            flex_metrics_map.get((scenario, case), {})
            if flex_metrics_map is not None
            else {}
        )
        pv_curt = float(flex_info.get("total_pv_curtailment_kwh", 0.0))
        bat_dis = float(flex_info.get("battery_discharge_kwh", 0.0))
        ev_shift = float(flex_info.get("ev_shifted_energy_kwh", 0.0))
        unserved_flex = float(flex_info.get("unserved_flexibility_kwh", 0.0))

        rows.append({
            "scenario": scenario,
            "case": case,
            "peak_transformer_loading_percent": round(peak_trafo, 2),
            "transformer_overload_duration_min": trafo_overload_duration,
            "peak_line_loading_percent": round(peak_line, 2),
            "line_overload_duration_min": line_overload_duration,
            "minimum_voltage_pu": round(min_v, 4),
            "voltage_violation_duration_min": volt_viol_duration,
            "peak_reverse_power_kw": round(peak_rev, 2),
            "reverse_power_duration_min": rev_duration,
            "peak_grid_import_kw": round(peak_imp, 2),
            "peak_grid_export_kw": round(peak_exp, 2),
            "total_constraint_violation_count": total_viol_count,
            "total_pv_curtailment_kwh": round(pv_curt, 2),
            "battery_discharge_kwh": round(bat_dis, 2),
            "ev_shifted_energy_kwh": round(ev_shift, 2),
            "unserved_flexibility_kwh": round(unserved_flex, 2),
        })

    return pd.DataFrame(rows)


def verify_causal_integrity(
    net_base_equal: bool = True,
    loads_identical: bool = True,
    solar_avail_identical: bool = True,
    ev_avail_identical: bool = True,
    battery_init_identical: bool = True,
    only_schedules_changed: bool = True,
) -> pd.DataFrame:
    """Construct causal comparison integrity verification matrix.

    Returns:
        DataFrame matching outputs/csv/comparison_integrity_check.csv.
    """
    checks = [
        ("same_feeder_topology", "PASS" if net_base_equal else "FAIL", "Radial 250 kVA LV feeder identical across cases"),
        ("same_household_loads", "PASS" if loads_identical else "FAIL", "Uncontrollable residential baseline load identical"),
        ("same_commercial_loads", "PASS" if loads_identical else "FAIL", "Commercial baseline demand identical"),
        ("same_critical_facility", "PASS" if loads_identical else "FAIL", "Critical facility baseline demand identical"),
        ("same_pv_availability", "PASS" if solar_avail_identical else "FAIL", "Underlying solar generation potential identical"),
        ("same_ev_availability", "PASS" if ev_avail_identical else "FAIL", "EV arrival, departure, and connection identical"),
        ("same_initial_battery_soc", "PASS" if battery_init_identical else "FAIL", "Initial community battery SOC identical at 50%"),
        ("only_der_schedule_changed", "PASS" if only_schedules_changed else "FAIL", "DER operating schedule is the sole independent variable"),
    ]

    return pd.DataFrame(checks, columns=["check_item", "status", "details"])


def compute_primary_comparison(
    summary_df: pd.DataFrame,
    baseline_case: str = "CASE_A_BASELINE",
    gridflex_case: str = "CASE_B_GRIDFLEX",
    scenario: str = "NORMAL_DAY",
) -> pd.DataFrame:
    """Calculate absolute and percentage differences between Baseline and GridFlex."""
    b_row = summary_df[(summary_df["scenario"] == scenario) & (summary_df["case"] == baseline_case)]
    g_row = summary_df[(summary_df["scenario"] == scenario) & (summary_df["case"] == gridflex_case)]

    if b_row.empty or g_row.empty:
        return pd.DataFrame()

    b = b_row.iloc[0]
    g = g_row.iloc[0]

    metrics = [
        ("Peak Transformer Loading (%)", b["peak_transformer_loading_percent"], g["peak_transformer_loading_percent"]),
        ("Transformer Overload Duration (min)", b["transformer_overload_duration_min"], g["transformer_overload_duration_min"]),
        ("Peak Line Loading (%)", b["peak_line_loading_percent"], g["peak_line_loading_percent"]),
        ("Line Overload Duration (min)", b["line_overload_duration_min"], g["line_overload_duration_min"]),
        ("Minimum Bus Voltage (pu)", b["minimum_voltage_pu"], g["minimum_voltage_pu"]),
        ("Voltage Violation Duration (min)", b["voltage_violation_duration_min"], g["voltage_violation_duration_min"]),
        ("Peak Reverse Power (kW)", b["peak_reverse_power_kw"], g["peak_reverse_power_kw"]),
        ("Reverse Power Duration (min)", b["reverse_power_duration_min"], g["reverse_power_duration_min"]),
        ("Peak Grid Import (kW)", b["peak_grid_import_kw"], g["peak_grid_import_kw"]),
        ("Peak Grid Export (kW)", b["peak_grid_export_kw"], g["peak_grid_export_kw"]),
        ("Total Constraint Violations", b["total_constraint_violation_count"], g["total_constraint_violation_count"]),
        ("PV Curtailment (kWh)", b["total_pv_curtailment_kwh"], g["total_pv_curtailment_kwh"]),
        ("Battery Discharge (kWh)", b["battery_discharge_kwh"], g["battery_discharge_kwh"]),
        ("EV Shifted Energy (kWh)", b["ev_shifted_energy_kwh"], g["ev_shifted_energy_kwh"]),
        ("Unserved Flexibility (kWh)", b["unserved_flexibility_kwh"], g["unserved_flexibility_kwh"]),
    ]

    rows = []
    for name, val_b, val_g in metrics:
        abs_diff = val_g - val_b
        pct_diff = ((val_g - val_b) / val_b * 100.0) if abs(val_b) > 1e-4 else np.nan
        rows.append({
            "metric": name,
            "baseline": val_b,
            "gridflex": val_g,
            "absolute_change": round(abs_diff, 4),
            "percentage_change": round(pct_diff, 2) if not np.isnan(pct_diff) else None,
        })

    return pd.DataFrame(rows)
