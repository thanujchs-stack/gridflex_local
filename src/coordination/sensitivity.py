"""Participation rate sensitivity analysis for GridFlex Local.

Evaluates flexibility coordination under 100%, 70%, and 40% owner participation scenarios.
"""

from typing import Dict, List, Any, Tuple
import pandas as pd
import numpy as np

from src.coordination.allocator import FlexibilityCoordinator


def run_participation_sensitivity(
    config: Dict[str, Any],
    der_passports_df: pd.DataFrame,
    requirements_df: pd.DataFrame,
    pv_forecast_df: pd.DataFrame,
    forecast_origin: pd.Timestamp,
    rates: List[float] = [1.00, 0.70, 0.40],
) -> pd.DataFrame:
    """Execute coordination under multiple participation scenarios and return comparison table."""
    records = []

    for rate in rates:
        coordinator = FlexibilityCoordinator(
            config=config,
            der_passports_df=der_passports_df,
            participation_override=rate,
        )
        plan_df, selection_df, unserved_df, der_summary = coordinator.coordinate_horizon(
            requirements_df=requirements_df,
            pv_forecast_df=pv_forecast_df,
            forecast_origin=forecast_origin,
        )

        tot_req = float(plan_df["required_up_kw"].sum() + plan_df["required_down_kw"].sum())
        tot_avail = float(plan_df["available_up_kw"].sum() + plan_df["available_down_kw"].sum())
        tot_selected = float(plan_df["selected_up_kw"].sum() + plan_df["selected_down_kw"].sum())
        tot_unserved = float(plan_df["unserved_up_kw"].sum() + plan_df["unserved_down_kw"].sum())

        participating_ders = int((der_summary["participation_count"] > 0).sum())
        # Constrained duration in minutes
        constrained_steps = int((plan_df["risk_state"].isin(["WATCH", "CONSTRAINED", "CRITICAL"])).sum())
        constraint_mins = constrained_steps * 15

        peak_req_kw = float(max(plan_df["required_up_kw"].max(), plan_df["required_down_kw"].max()))

        utilization = (tot_selected / tot_avail) if tot_avail > 0.0 else 0.0
        satisfaction = (tot_selected / tot_req) if tot_req > 0.0 else 1.0

        records.append({
            "scenario": f"{int(rate * 100)}% Participation",
            "participation_rate": rate,
            "total_available_kw": round(tot_avail, 2),
            "total_selected_kw": round(tot_selected, 2),
            "total_unserved_kw": round(tot_unserved, 2),
            "participating_der_count": participating_ders,
            "peak_required_kw": round(peak_req_kw, 2),
            "constraint_duration_minutes": constraint_mins,
            "flexibility_utilization_pct": round(utilization * 100.0, 2),
            "flexibility_satisfaction_pct": round(satisfaction * 100.0, 2),
        })

    return pd.DataFrame(records)
