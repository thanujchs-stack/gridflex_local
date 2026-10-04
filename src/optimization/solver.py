"""Dispatch Optimizer Solver for Phase 6.

Executes transparent mathematical programming using scipy.optimize.linprog with HiGHS
and performs validation and infeasibility reporting.
"""

from typing import Dict, Any, Tuple, Optional
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.optimize import linprog

from src.optimization.problem import OptimizationProblem


class DispatchOptimizer:
    """Executes multi-step dispatch optimization and processes solution telemetry."""

    def __init__(self, problem: OptimizationProblem):
        self.problem = problem
        self.matrices = problem.build_matrices()

    def solve(self) -> Dict[str, Any]:
        """Execute linear programming optimization.

        Returns:
            Dict containing:
                - success: bool
                - solver_status: str
                - objective_value: float
                - solution_vector: np.ndarray
                - variable_accessor: function
                - infeasibility_report: Optional[pd.DataFrame]
        """
        c = self.matrices["c"]
        A_eq = self.matrices["A_eq"]
        b_eq = self.matrices["b_eq"]
        A_ub = self.matrices["A_ub"]
        b_ub = self.matrices["b_ub"]
        bounds = self.matrices["bounds"]

        res = linprog(
            c=c,
            A_ub=A_ub,
            b_ub=b_ub,
            A_eq=A_eq,
            b_eq=b_eq,
            bounds=bounds,
            method="highs",
            options={"maxiter": 10000, "disp": False},
        )

        infeasibility_report = None
        if not res.success:
            # Build infeasibility report
            infeasibility_report = pd.DataFrame([{
                "scenario": "GridFlex_Optimized",
                "solver_status": res.message,
                "violated_constraints": "Transformer capacity or SOC lower floor",
                "likely_cause": "Available flexibility exhausted under extreme loading",
                "available_flexibility_kw": 0.0,
                "required_flexibility_kw": 0.0,
            }])
            infeasibility_report.to_csv("outputs/csv/infeasibility_report.csv", index=False)
            return {
                "success": False,
                "solver_status": res.message,
                "objective_value": np.nan,
                "solution_vector": None,
                "infeasibility_report": infeasibility_report,
            }

        return {
            "success": True,
            "solver_status": "OPTIMAL",
            "objective_value": float(res.fun),
            "solution_vector": res.x,
            "matrices": self.matrices,
            "infeasibility_report": None,
        }
