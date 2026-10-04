"""Electrical metrics calculation, constraint checking, and grid performance evaluation.

Computes comprehensive timeseries metrics:
- Substation & Feeder power flows (Grid import/export, net load)
- Loading percentages (transformer, lines)
- Bus voltage bounds & violation detection
- Feeder active losses
- Reverse power flow indicator
"""

from typing import Any, Dict, List, Tuple
import numpy as np
import pandas as pd


def compute_feeder_summary_metrics(
    df_timeseries: pd.DataFrame,
    config: Dict[str, Any]
) -> Dict[str, Any]:
    """Compute high-level statistical summary of feeder simulation results."""
    val_cfg = config.get("validation", {})
    min_v_limit = float(val_cfg.get("min_voltage_pu", 0.94))
    max_v_limit = float(val_cfg.get("max_voltage_pu", 1.06))
    trafo_crit = float(val_cfg.get("transformer_critical_pct", 100.0))
    trafo_warn = float(val_cfg.get("transformer_warning_pct", 80.0))
    line_crit = float(val_cfg.get("line_critical_pct", 100.0))

    dt_h = 0.25  # 15 minutes = 0.25 hours

    # Energy totals (kWh)
    total_energy_consumed_kwh = float(df_timeseries["total_load_kw"].sum() * dt_h)
    total_pv_generated_kwh = float(df_timeseries["pv_generation_kw"].sum() * dt_h)
    total_grid_imported_kwh = float(df_timeseries["grid_import_kw"].sum() * dt_h)
    total_grid_exported_kwh = float(df_timeseries["grid_export_kw"].sum() * dt_h)
    total_losses_kwh = float(df_timeseries["network_losses_kw"].sum() * dt_h)

    # Peak values
    peak_demand_kw = float(df_timeseries["total_load_kw"].max())
    peak_pv_kw = float(df_timeseries["pv_generation_kw"].max())
    peak_import_kw = float(df_timeseries["grid_import_kw"].max())
    peak_export_kw = float(df_timeseries["grid_export_kw"].max())
    peak_trafo_loading = float(df_timeseries["transformer_loading_pct"].max())
    peak_line_loading = float(df_timeseries["max_line_loading_pct"].max())

    # Voltage bounds
    min_observed_v = float(df_timeseries["min_bus_voltage_pu"].min())
    max_observed_v = float(df_timeseries["max_bus_voltage_pu"].max())

    # Violation counts
    undervoltage_steps = int((df_timeseries["min_bus_voltage_pu"] < min_v_limit).sum())
    overvoltage_steps = int((df_timeseries["max_bus_voltage_pu"] > max_v_limit).sum())
    trafo_overload_steps = int((df_timeseries["transformer_loading_pct"] > trafo_crit).sum())
    trafo_warning_steps = int((df_timeseries["transformer_loading_pct"] > trafo_warn).sum())
    line_overload_steps = int((df_timeseries["max_line_loading_pct"] > line_crit).sum())
    reverse_flow_steps = int((df_timeseries["reverse_power_flow"]).sum())

    return {
        "total_energy_consumed_kwh": round(total_energy_consumed_kwh, 2),
        "total_pv_generated_kwh": round(total_pv_generated_kwh, 2),
        "total_grid_imported_kwh": round(total_grid_imported_kwh, 2),
        "total_grid_exported_kwh": round(total_grid_exported_kwh, 2),
        "total_losses_kwh": round(total_losses_kwh, 2),
        "loss_percentage": round(100.0 * total_losses_kwh / max(1.0, total_energy_consumed_kwh), 2),
        "peak_demand_kw": round(peak_demand_kw, 2),
        "peak_pv_kw": round(peak_pv_kw, 2),
        "peak_import_kw": round(peak_import_kw, 2),
        "peak_export_kw": round(peak_export_kw, 2),
        "peak_transformer_loading_pct": round(peak_trafo_loading, 2),
        "peak_line_loading_pct": round(peak_line_loading, 2),
        "min_bus_voltage_pu": round(min_observed_v, 4),
        "max_bus_voltage_pu": round(max_observed_v, 4),
        "undervoltage_timesteps": undervoltage_steps,
        "overvoltage_timesteps": overvoltage_steps,
        "transformer_overload_timesteps": trafo_overload_steps,
        "transformer_warning_timesteps": trafo_warning_steps,
        "line_overload_timesteps": line_overload_steps,
        "reverse_power_flow_timesteps": reverse_flow_steps,
        "energy_not_served_kwh": 0.0  # Phase 1: continuous grid connection, no unserved energy
    }
