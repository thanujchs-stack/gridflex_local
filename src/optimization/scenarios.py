"""Participation and Scenario Sensitivity Evaluator for Phase 6.

Evaluates 100%, 70%, and 40% DER participation scenarios deterministically.
"""

from typing import Dict, Any, List
import pandas as pd
import numpy as np

from src.optimization.problem import OptimizationProblem
from src.optimization.solver import DispatchOptimizer
from src.optimization.dispatcher import generate_dispatch_plan


def run_participation_sensitivities(
    config: Dict[str, Any],
    opt_config: Dict[str, Any],
    envelopes_df: pd.DataFrame,
    coordination_plan_df: pd.DataFrame,
    net_load_forecast_df: pd.DataFrame,
    pv_forecast_df: pd.DataFrame,
    load_forecast_df: pd.DataFrame,
    rates: List[float] = [1.00, 0.70, 0.40],
) -> pd.DataFrame:
    """Run optimization under multiple participation rates.

    Returns:
        DataFrame summarizing scenario sensitivity results.
    """
    rows = []
    for rate in rates:
        prob = OptimizationProblem(
            config=config,
            opt_config=opt_config,
            envelopes_df=envelopes_df,
            coordination_plan_df=coordination_plan_df,
            net_load_forecast_df=net_load_forecast_df,
            pv_forecast_df=pv_forecast_df,
            load_forecast_df=load_forecast_df,
            participation_rate=rate,
        )
        solver = DispatchOptimizer(prob)
        res = solver.solve()

        if res["success"]:
            plan = generate_dispatch_plan(prob, res)
            summ = plan["optimization_summary"].iloc[0]
            rows.append({
                "participation_rate": f"{int(rate * 100)}%",
                "objective_value": summ["objective_value"],
                "peak_grid_import_kw": summ["peak_grid_import_kw"],
                "total_grid_import_kwh": summ["total_grid_import_kwh"],
                "battery_discharge_kwh": summ["battery_discharge_energy_kwh"],
                "ev_shifted_kwh": summ["ev_shifted_energy_kwh"],
                "pv_curtailed_kwh": summ["total_pv_curtailment_kwh"],
                "active_ders": summ["number_of_active_ders"],
                "solver_status": summ["solver_status"],
            })
        else:
            rows.append({
                "participation_rate": f"{int(rate * 100)}%",
                "objective_value": np.nan,
                "peak_grid_import_kw": np.nan,
                "total_grid_import_kwh": np.nan,
                "battery_discharge_kwh": np.nan,
                "ev_shifted_kwh": np.nan,
                "pv_curtailed_kwh": np.nan,
                "active_ders": 0,
                "solver_status": res["solver_status"],
            })

    return pd.DataFrame(rows)
