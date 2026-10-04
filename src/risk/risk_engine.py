"""Transparent Rule-Based Local Risk Engine for GridFlex Local.

Evaluates multi-step forward physical grid operating risks based on
forecast net load, uncertainty intervals, transformer/line loading,
voltage margins, and available flexibility buffers.
"""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import numpy as np
import pandas as pd


@dataclass
class RiskAssessment:
    """Single-timestep forward risk assessment container."""
    timestamp: pd.Timestamp
    horizon_minutes: int
    operational_state: str  # NORMAL, WATCH, CONSTRAINED, CRITICAL
    risk_score: float       # 0.0 to 100.0
    primary_constraint: str # NONE, TRANSFORMER_OVERLOAD, LINE_OVERLOAD, VOLTAGE_DROP, VOLTAGE_RISE, HIGH_UNCERTAINTY
    trafo_loading_pct: float
    max_line_loading_pct: float
    min_vm_pu: float
    max_vm_pu: float
    net_load_kw: float
    uncertainty_width_kw: float
    available_flex_kw: float
    mitigable_by_flexibility: bool
    explanation: str


class LocalRiskEngine:
    """Rule-based physical risk evaluator adhering to distribution grid standards."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        val_cfg = config.get("validation", {})
        self.trafo_warn_pct = float(val_cfg.get("transformer_warning_pct", 80.0))
        self.trafo_crit_pct = float(val_cfg.get("transformer_critical_pct", 100.0))
        self.line_warn_pct = float(val_cfg.get("line_warning_pct", 80.0))
        self.line_crit_pct = float(val_cfg.get("line_critical_pct", 100.0))
        self.min_v_pu = float(val_cfg.get("min_voltage_pu", 0.94))
        self.max_v_pu = float(val_cfg.get("max_voltage_pu", 1.06))

    def assess_timestep(
        self,
        timestamp: pd.Timestamp,
        horizon_minutes: int,
        trafo_loading_pct: float,
        trafo_loading_upper_pct: float,
        max_line_loading_pct: float,
        min_vm_pu: float,
        max_vm_pu: float,
        net_load_kw: float,
        net_load_lb_kw: float,
        net_load_ub_kw: float,
        available_up_flex_kw: float,
        available_down_flex_kw: float,
    ) -> RiskAssessment:
        """Classify operational risk state and calculate transparent risk score."""
        uncertainty_width = max(0.0, net_load_ub_kw - net_load_lb_kw)

        # Baseline score components
        # Loading factor: 0-60 points
        loading_factor = min(60.0, (trafo_loading_pct / self.trafo_crit_pct) * 50.0)

        # Voltage factor: 0-25 points
        v_dev_lower = max(0.0, (0.98 - min_vm_pu) / (0.98 - self.min_v_pu))
        v_dev_upper = max(0.0, (max_vm_pu - 1.02) / (self.max_v_pu - 1.02))
        voltage_factor = min(25.0, max(v_dev_lower, v_dev_upper) * 25.0)

        # Uncertainty factor: 0-15 points (high relative uncertainty adds risk)
        rel_uncertainty = uncertainty_width / max(10.0, abs(net_load_kw))
        uncertainty_factor = min(15.0, rel_uncertainty * 10.0)

        raw_score = loading_factor + voltage_factor + uncertainty_factor

        # Determine Primary Constraint & State
        primary_constraint = "NONE"
        explanation_clauses = []

        is_critical = False
        is_constrained = False
        is_watch = False

        # 1. Critical Rules
        if trafo_loading_pct >= self.trafo_crit_pct or trafo_loading_upper_pct >= 115.0:
            is_critical = True
            primary_constraint = "TRANSFORMER_OVERLOAD"
            explanation_clauses.append(f"Transformer loading {trafo_loading_pct:.1f}% exceeds rated capacity")
        elif min_vm_pu <= (self.min_v_pu - 0.01) or max_vm_pu >= (self.max_v_pu + 0.01):
            is_critical = True
            primary_constraint = "VOLTAGE_DROP" if min_vm_pu <= (self.min_v_pu - 0.01) else "VOLTAGE_RISE"
            explanation_clauses.append(f"Severe voltage violation (min {min_vm_pu:.3f} p.u.)")
        elif max_line_loading_pct >= self.line_crit_pct:
            is_critical = True
            primary_constraint = "LINE_OVERLOAD"
            explanation_clauses.append(f"Feeder line loading {max_line_loading_pct:.1f}% exceeds thermal limit")

        # 2. Constrained Rules
        elif trafo_loading_pct >= 95.0 or trafo_loading_upper_pct >= 105.0:
            is_constrained = True
            primary_constraint = "TRANSFORMER_OVERLOAD"
            explanation_clauses.append(f"Transformer loading {trafo_loading_pct:.1f}% near threshold")
        elif min_vm_pu <= self.min_v_pu or max_vm_pu >= self.max_v_pu:
            is_constrained = True
            primary_constraint = "VOLTAGE_DROP" if min_vm_pu <= self.min_v_pu else "VOLTAGE_RISE"
            explanation_clauses.append(f"Bus voltage {min_vm_pu:.3f} p.u. breaches statutory envelope")
        elif max_line_loading_pct >= 95.0:
            is_constrained = True
            primary_constraint = "LINE_OVERLOAD"
            explanation_clauses.append(f"Line loading {max_line_loading_pct:.1f}% approaching limit")

        # 3. Watch Rules
        elif trafo_loading_pct >= self.trafo_warn_pct or trafo_loading_upper_pct >= 95.0:
            is_watch = True
            primary_constraint = "TRANSFORMER_OVERLOAD"
            explanation_clauses.append(f"Elevated loading {trafo_loading_pct:.1f}% above warning margin")
        elif min_vm_pu <= 0.955 or max_vm_pu >= 1.045:
            is_watch = True
            primary_constraint = "VOLTAGE_DROP" if min_vm_pu <= 0.955 else "VOLTAGE_RISE"
            explanation_clauses.append(f"Voltage margin declining (min {min_vm_pu:.3f} p.u.)")
        elif uncertainty_width >= 50.0:
            is_watch = True
            primary_constraint = "HIGH_UNCERTAINTY"
            explanation_clauses.append(f"High forecast spread ({uncertainty_width:.1f} kW)")

        # Operational State Assignment
        if is_critical:
            operational_state = "CRITICAL"
            risk_score = max(75.0, min(100.0, raw_score))
        elif is_constrained:
            operational_state = "CONSTRAINED"
            risk_score = max(50.0, min(74.9, raw_score))
        elif is_watch:
            operational_state = "WATCH"
            risk_score = max(25.0, min(49.9, raw_score))
        else:
            operational_state = "NORMAL"
            risk_score = min(24.9, raw_score)
            explanation_clauses.append("Feeder operates well within physical bounds")

        # Check flexibility mitigation potential
        # If loading overload, we need upward generation (BESS discharge) or downward load reduction (shed/curtail)
        # Downward flexibility (shedding load or curtailing PV) or Upward flexibility (battery discharge to supply load)
        excess_kw = max(0.0, (trafo_loading_pct - self.trafo_warn_pct) / 100.0 * 250.0)
        mitigable = bool((available_up_flex_kw + available_down_flex_kw) >= excess_kw)

        if mitigable and operational_state in ["CONSTRAINED", "CRITICAL"]:
            explanation_clauses.append(f"Mitigable: Available flexibility ({available_up_flex_kw + available_down_flex_kw:.1f} kW) >= excess ({excess_kw:.1f} kW)")

        explanation = "; ".join(explanation_clauses)

        return RiskAssessment(
            timestamp=timestamp,
            horizon_minutes=horizon_minutes,
            operational_state=operational_state,
            risk_score=round(risk_score, 1),
            primary_constraint=primary_constraint,
            trafo_loading_pct=round(trafo_loading_pct, 1),
            max_line_loading_pct=round(max_line_loading_pct, 1),
            min_vm_pu=round(min_vm_pu, 4),
            max_vm_pu=round(max_vm_pu, 4),
            net_load_kw=round(net_load_kw, 2),
            uncertainty_width_kw=round(uncertainty_width, 2),
            available_flex_kw=round(available_up_flex_kw + available_down_flex_kw, 2),
            mitigable_by_flexibility=mitigable,
            explanation=explanation,
        )

    def evaluate_trajectory(
        self,
        powerflow_df: pd.DataFrame,
        net_load_forecast_df: pd.DataFrame,
        flexibility_df: pd.DataFrame,
    ) -> pd.DataFrame:
        """Evaluate complete 16-step forward risk trajectory."""
        records = []
        n = min(len(powerflow_df), len(net_load_forecast_df), len(flexibility_df))

        for i in range(n):
            pf_row = powerflow_df.iloc[i]
            nl_row = net_load_forecast_df.iloc[i]
            fl_row = flexibility_df.iloc[i]

            t = pd.to_datetime(pf_row["timestamp"])
            h_mins = int(pf_row.get("horizon_minutes", (i + 1) * 15))

            assessment = self.assess_timestep(
                timestamp=t,
                horizon_minutes=h_mins,
                trafo_loading_pct=float(pf_row["trafo_loading_pct"]),
                trafo_loading_upper_pct=float(pf_row.get("trafo_loading_upper_pct", pf_row["trafo_loading_pct"])),
                max_line_loading_pct=float(pf_row["max_line_loading_pct"]),
                min_vm_pu=float(pf_row["min_vm_pu"]),
                max_vm_pu=float(pf_row["max_vm_pu"]),
                net_load_kw=float(nl_row["forecast"]),
                net_load_lb_kw=float(nl_row.get("lower_bound", nl_row["forecast"])),
                net_load_ub_kw=float(nl_row.get("upper_bound", nl_row["forecast"])),
                available_up_flex_kw=float(fl_row.get("total_up_available_kw", 0.0)),
                available_down_flex_kw=float(fl_row.get("total_down_available_kw", 0.0)),
            )

            records.append({
                "timestamp": assessment.timestamp,
                "horizon_minutes": assessment.horizon_minutes,
                "operational_state": assessment.operational_state,
                "risk_score": assessment.risk_score,
                "primary_constraint": assessment.primary_constraint,
                "trafo_loading_pct": assessment.trafo_loading_pct,
                "max_line_loading_pct": assessment.max_line_loading_pct,
                "min_vm_pu": assessment.min_vm_pu,
                "max_vm_pu": assessment.max_vm_pu,
                "net_load_kw": assessment.net_load_kw,
                "uncertainty_width_kw": assessment.uncertainty_width_kw,
                "available_flex_kw": assessment.available_flex_kw,
                "mitigable_by_flexibility": assessment.mitigable_by_flexibility,
                "explanation": assessment.explanation,
            })

        return pd.DataFrame(records)
