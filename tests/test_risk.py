"""Unit tests for GridFlex Local Phase 3 Local Risk Engine.

Tests:
- Risk classification states (NORMAL, WATCH, CONSTRAINED, CRITICAL)
- Voltage and loading rule thresholds
- Uncertainty impact on risk scoring
- Flexibility mitigation flagging
- Power-flow scenario evaluation
"""

import pandas as pd
import numpy as np
import pytest

from src.risk.risk_engine import LocalRiskEngine, RiskAssessment
from src.risk.powerflow_evaluator import evaluate_forecast_powerflow
from src.utils.config import load_config


@pytest.fixture
def risk_engine():
    cfg = load_config()
    return LocalRiskEngine(config=cfg)


def test_risk_classification_normal(risk_engine):
    """Verify normal grid state when loading is low and voltage is nominal."""
    t = pd.Timestamp("2026-01-15 12:00:00")
    assessment = risk_engine.assess_timestep(
        timestamp=t,
        horizon_minutes=15,
        trafo_loading_pct=45.0,
        trafo_loading_upper_pct=55.0,
        max_line_loading_pct=30.0,
        min_vm_pu=0.995,
        max_vm_pu=1.002,
        net_load_kw=80.0,
        net_load_lb_kw=70.0,
        net_load_ub_kw=90.0,
        available_up_flex_kw=25.0,
        available_down_flex_kw=35.0,
    )

    assert assessment.operational_state == "NORMAL"
    assert assessment.risk_score < 25.0
    assert assessment.primary_constraint == "NONE"


def test_risk_classification_watch(risk_engine):
    """Verify WATCH state when loading exceeds 80% or uncertainty is high."""
    t = pd.Timestamp("2026-01-15 18:00:00")
    assessment = risk_engine.assess_timestep(
        timestamp=t,
        horizon_minutes=60,
        trafo_loading_pct=82.0,  # exceeds warning threshold 80%
        trafo_loading_upper_pct=88.0,
        max_line_loading_pct=60.0,
        min_vm_pu=0.965,
        max_vm_pu=1.000,
        net_load_kw=190.0,
        net_load_lb_kw=170.0,
        net_load_ub_kw=210.0,
        available_up_flex_kw=25.0,
        available_down_flex_kw=20.0,
    )

    assert assessment.operational_state == "WATCH"
    assert 25.0 <= assessment.risk_score < 50.0
    assert assessment.primary_constraint == "TRANSFORMER_OVERLOAD"


def test_risk_classification_constrained(risk_engine):
    """Verify CONSTRAINED state when loading approaches limit (>=95%)."""
    t = pd.Timestamp("2026-01-15 19:00:00")
    assessment = risk_engine.assess_timestep(
        timestamp=t,
        horizon_minutes=90,
        trafo_loading_pct=96.0,
        trafo_loading_upper_pct=102.0,
        max_line_loading_pct=75.0,
        min_vm_pu=0.945,
        max_vm_pu=1.000,
        net_load_kw=225.0,
        net_load_lb_kw=205.0,
        net_load_ub_kw=245.0,
        available_up_flex_kw=25.0,
        available_down_flex_kw=20.0,
    )

    assert assessment.operational_state == "CONSTRAINED"
    assert 50.0 <= assessment.risk_score < 75.0


def test_risk_classification_critical(risk_engine):
    """Verify CRITICAL state when transformer is overloaded (>=100%) or voltage breaches limit."""
    t = pd.Timestamp("2026-01-15 19:30:00")
    assessment = risk_engine.assess_timestep(
        timestamp=t,
        horizon_minutes=120,
        trafo_loading_pct=105.0,
        trafo_loading_upper_pct=118.0,
        max_line_loading_pct=85.0,
        min_vm_pu=0.925,  # undervoltage violation < 0.94
        max_vm_pu=1.000,
        net_load_kw=260.0,
        net_load_lb_kw=240.0,
        net_load_ub_kw=280.0,
        available_up_flex_kw=25.0,
        available_down_flex_kw=10.0,
    )

    assert assessment.operational_state == "CRITICAL"
    assert assessment.risk_score >= 75.0


def test_risk_flexibility_mitigation(risk_engine):
    """Verify that available flexibility is evaluated against overload magnitude."""
    t = pd.Timestamp("2026-01-15 19:00:00")
    # Overload of 90% vs 80% warn = 10% * 250 kVA = 25 kW excess
    assessment_mitigable = risk_engine.assess_timestep(
        timestamp=t,
        horizon_minutes=60,
        trafo_loading_pct=90.0,
        trafo_loading_upper_pct=95.0,
        max_line_loading_pct=65.0,
        min_vm_pu=0.960,
        max_vm_pu=1.000,
        net_load_kw=210.0,
        net_load_lb_kw=190.0,
        net_load_ub_kw=230.0,
        available_up_flex_kw=25.0,
        available_down_flex_kw=15.0,  # total 40 kW >= 25 kW excess
    )
    assert assessment_mitigable.mitigable_by_flexibility is True

    # When available flex is minimal (e.g. 5 kW < 25 kW excess)
    assessment_unmitigable = risk_engine.assess_timestep(
        timestamp=t,
        horizon_minutes=60,
        trafo_loading_pct=90.0,
        trafo_loading_upper_pct=95.0,
        max_line_loading_pct=65.0,
        min_vm_pu=0.960,
        max_vm_pu=1.000,
        net_load_kw=210.0,
        net_load_lb_kw=190.0,
        net_load_ub_kw=230.0,
        available_up_flex_kw=2.0,
        available_down_flex_kw=3.0,
    )
    assert assessment_unmitigable.mitigable_by_flexibility is False


def test_powerflow_evaluation():
    """Verify AC power flow runs on 16-step forecast scenario and returns physical metrics."""
    dates = pd.date_range("2026-01-15 12:00:00", periods=16, freq="15min")
    fc_df = pd.DataFrame({
        "timestamp": dates,
        "horizon_minutes": [15 * i for i in range(1, 17)],
        "forecast": np.full(16, 95.0),
        "upper_bound": np.full(16, 120.0),
    })
    pv_df = pd.DataFrame({
        "timestamp": dates,
        "forecast": np.full(16, 40.0),
    })

    pf_res = evaluate_forecast_powerflow(fc_df, pv_df)
    assert len(pf_res) == 16
    assert (pf_res["converged"] == True).all()
    assert (pf_res["trafo_loading_pct"] > 0.0).all()
    assert (pf_res["min_vm_pu"] > 0.90).all()
    assert (pf_res["max_vm_pu"] <= 1.05).all()
