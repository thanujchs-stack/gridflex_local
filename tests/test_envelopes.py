"""Unit tests for Phase 5 Dynamic Operating Envelopes (DOEs).

Validates compliance with all 20 mandatory Phase 5 conditions:
1. normal envelope generation
2. constrained envelope generation
3. critical envelope generation
4. PV export limit
5. battery SOC
6. battery reserve
7. battery power limit
8. EV arrival/departure
9. EV energy requirement
10. V2G disabled
11. flexible-load bounds
12. owner participation
13. uncertainty margin
14. hysteresis
15. temporal consistency
16. no double counting
17. dynamic limit <= physical limit
18. dynamic limit >= physical minimum
19. power-flow convergence
20. Phase 1 baseline unchanged
"""

import pytest
import pandas as pd
import numpy as np

from src.utils.config import load_config
from src.envelopes.calculator import DynamicOperatingEnvelopeCalculator
from src.envelopes.hysteresis import HysteresisController
from src.envelopes.events import EnvelopeEventDetector
from src.envelopes.metrics import calculate_envelope_metrics


@pytest.fixture
def config():
    return load_config()


@pytest.fixture
def sample_passports():
    return pd.read_csv("outputs/csv/der_flexibility_passport.csv")


@pytest.fixture
def sample_registry():
    return pd.read_csv("outputs/csv/der_registry.csv")


@pytest.fixture
def sample_coordination_plan():
    return pd.read_csv("outputs/csv/coordination_plan.csv")


@pytest.fixture
def sample_selection():
    return pd.read_csv("outputs/csv/flexibility_selection.csv")


@pytest.fixture
def sample_risk():
    return pd.read_csv("outputs/csv/risk_forecast.csv")


@pytest.fixture
def sample_pv_fc():
    return pd.read_csv("outputs/csv/pv_forecast.csv")


@pytest.fixture
def sample_load_fc():
    return pd.read_csv("outputs/csv/load_forecast.csv")


@pytest.fixture
def generated_envelopes(config, sample_passports, sample_registry, sample_coordination_plan, sample_selection, sample_risk, sample_pv_fc, sample_load_fc):
    calc = DynamicOperatingEnvelopeCalculator(
        config=config,
        der_passports_df=sample_passports,
        der_registry_df=sample_registry,
        initial_bess_soc=0.50,
    )
    all_envs, pv_envs, bat_envs, ev_envs, fl_envs = calc.compute_envelopes(
        coordination_plan_df=sample_coordination_plan,
        flexibility_selection_df=sample_selection,
        risk_forecast_df=sample_risk,
        pv_forecast_df=sample_pv_fc,
        load_forecast_df=sample_load_fc,
    )
    return all_envs, pv_envs, bat_envs, ev_envs, fl_envs


# 1. Normal envelope generation
def test_normal_envelope_generation(generated_envelopes):
    all_envs, _, _, _, _ = generated_envelopes
    norm_envs = all_envs[all_envs["risk_state"] == "NORMAL"]
    assert not norm_envs.empty
    # Under normal conditions, dynamic bounds must equal normal bounds
    for _, row in norm_envs.iterrows():
        if row["der_type"] == "PV":
            assert np.isclose(row["dynamic_max_kw"], row["normal_max_kw"], atol=1e-3)


# 2. Constrained envelope generation
def test_constrained_envelope_generation(config, sample_passports, sample_registry, sample_coordination_plan, sample_selection, sample_risk, sample_pv_fc, sample_load_fc):
    # Force a constrained plan row with voltage rise
    plan = sample_coordination_plan.copy()
    plan["risk_state"] = "CONSTRAINED"
    plan["constraint_type"] = "VOLTAGE_RISE"
    plan["constraint_location"] = "Bus_Residential_3"

    calc = DynamicOperatingEnvelopeCalculator(config, sample_passports, sample_registry)
    all_envs, pv_envs, _, _, _ = calc.compute_envelopes(plan, sample_selection, sample_risk, sample_pv_fc, sample_load_fc)

    # Some participating PVs must experience export limit tightening
    tightened_pvs = pv_envs[pv_envs["dynamic_export_limit_kw"] < pv_envs["normal_export_limit_kw"]]
    assert not tightened_pvs.empty


# 3. Critical envelope generation
def test_critical_envelope_generation(config, sample_passports, sample_registry, sample_coordination_plan, sample_selection, sample_risk, sample_pv_fc, sample_load_fc):
    plan = sample_coordination_plan.copy()
    plan["risk_state"] = "CRITICAL"
    plan["constraint_type"] = "TRANSFORMER_OVERLOAD"
    plan["constraint_location"] = "Transformer"

    calc = DynamicOperatingEnvelopeCalculator(config, sample_passports, sample_registry)
    all_envs, _, bat_envs, _, _ = calc.compute_envelopes(plan, sample_selection, sample_risk, sample_pv_fc, sample_load_fc)

    # In critical transformer overload, battery charging must be restricted to 0
    assert (bat_envs["dynamic_charge_limit_kw"] == 0.0).all()


# 4. PV export limit
def test_pv_export_limit(generated_envelopes):
    _, pv_envs, _, _, _ = generated_envelopes
    for _, row in pv_envs.iterrows():
        assert row["dynamic_export_limit_kw"] <= row["normal_export_limit_kw"] + 1e-4
        assert row["dynamic_export_limit_kw"] >= 0.0


# 5. Battery SOC limits
def test_battery_soc_limits(generated_envelopes):
    _, _, bat_envs, _, _ = generated_envelopes
    for _, row in bat_envs.iterrows():
        assert row["soc"] >= row["minimum_soc"] - 1e-4
        assert row["soc"] <= row["maximum_soc"] + 1e-4


# 6. Battery reserve respected
def test_battery_reserve_respected(generated_envelopes):
    _, _, bat_envs, _, _ = generated_envelopes
    for _, row in bat_envs.iterrows():
        assert row["soc"] >= (row["minimum_soc"] + row["reserve_soc"]) - 1e-4


# 7. Battery power limits
def test_battery_power_limit(generated_envelopes):
    _, _, bat_envs, _, _ = generated_envelopes
    for _, row in bat_envs.iterrows():
        assert row["dynamic_charge_limit_kw"] <= row["max_charge_kw"] + 1e-4
        assert row["dynamic_discharge_limit_kw"] <= row["max_discharge_kw"] + 1e-4


# 8. EV arrival/departure
def test_ev_arrival_departure(generated_envelopes):
    _, _, _, ev_envs, _ = generated_envelopes
    for _, row in ev_envs.iterrows():
        t = pd.to_datetime(row["timestamp"])
        hour = t.hour + t.minute / 60.0
        # If daytime outside 18:00 - 07:30, charge limit must be 0
        if 7.5 < hour < 18.0:
            assert np.isclose(row["dynamic_charge_limit_kw"], 0.0, atol=1e-3)


# 9. EV energy requirement
def test_ev_energy_requirement(generated_envelopes):
    _, _, _, ev_envs, _ = generated_envelopes
    assert (ev_envs["required_energy_kwh"] > 0.0).all()


# 10. V2G disabled
def test_v2g_disabled(generated_envelopes):
    _, _, _, ev_envs, _ = generated_envelopes
    assert (ev_envs["v2g_enabled"] == False).all()


# 11. Flexible-load bounds
def test_flexible_load_bounds(generated_envelopes):
    _, _, _, _, fl_envs = generated_envelopes
    for _, row in fl_envs.iterrows():
        if row["dynamic_max_kw"] > 0.0:
            assert row["dynamic_min_kw"] >= row["minimum_kw"] - 1e-4
            assert row["dynamic_max_kw"] <= row["maximum_kw"] + 1e-4


# 12. Owner participation respected
def test_owner_participation(generated_envelopes, sample_passports):
    all_envs, pv_envs, _, _, _ = generated_envelopes
    col = "flexibility_enabled" if "flexibility_enabled" in sample_passports.columns else "owner_participation"
    no_curt_ids = set(sample_passports[sample_passports[col] == False]["der_id"])
    no_curt_pv = pv_envs[pv_envs["der_id"].isin(no_curt_ids)]
    for _, row in no_curt_pv.iterrows():
        assert row["curtailment_applied_kw"] == 0.0


# 13. Uncertainty margin
def test_uncertainty_margin(generated_envelopes):
    all_envs, _, _, _, _ = generated_envelopes
    assert (all_envs["uncertainty_margin_kw"] >= 0.0).all()


# 14. Hysteresis chatter prevention
def test_hysteresis_controller(config):
    h = HysteresisController(config)
    # 1. Start NORMAL
    s1 = h.evaluate_state("NORMAL", trafo_loading_pct=60.0, min_vm_pu=0.99, max_vm_pu=1.01, primary_constraint="NONE")
    assert s1["effective_state"] == "NORMAL"

    # 2. Trigger constraint (trafo >= 80%)
    s2 = h.evaluate_state("CONSTRAINED", trafo_loading_pct=82.0, min_vm_pu=0.96, max_vm_pu=1.01, primary_constraint="TRANSFORMER_OVERLOAD")
    assert s2["effective_state"] == "CONSTRAINED"

    # 3. Small drop to 78% (above 75% release threshold) -> should remain CONSTRAINED due to deadband
    s3 = h.evaluate_state("NORMAL", trafo_loading_pct=78.0, min_vm_pu=0.96, max_vm_pu=1.01, primary_constraint="TRANSFORMER_OVERLOAD")
    assert s3["effective_state"] == "CONSTRAINED"
    assert s3["is_held_by_hysteresis"] is True

    # 4. Cleared below 75% -> releases to NORMAL
    s4 = h.evaluate_state("NORMAL", trafo_loading_pct=72.0, min_vm_pu=0.97, max_vm_pu=1.01, primary_constraint="NONE")
    assert s4["effective_state"] == "NORMAL"


# 15. Temporal consistency
def test_temporal_consistency(generated_envelopes):
    all_envs, _, _, _, _ = generated_envelopes
    origins = all_envs["forecast_origin"].drop_duplicates()
    assert len(origins) == 1
    # Check that timestamps strictly increase
    bess = all_envs[all_envs["der_id"] == "BESS_COMMUNITY_01"]
    diffs = bess["timestamp"].diff().dropna()
    assert (diffs == pd.Timedelta(minutes=15)).all()


# 16. No double counting
def test_no_double_counting(generated_envelopes):
    all_envs, _, _, _, _ = generated_envelopes
    for _, row in all_envs.iterrows():
        assert row["allocated_flex_kw"] <= row["available_flex_kw"] + 1e-4


# 17. Dynamic limit <= physical limit
def test_dynamic_le_physical(generated_envelopes):
    all_envs, _, _, _, _ = generated_envelopes
    for _, row in all_envs.iterrows():
        assert row["dynamic_max_kw"] <= row["normal_max_kw"] + 1e-4


# 18. Dynamic limit >= physical minimum
def test_dynamic_ge_physical_min(generated_envelopes):
    all_envs, _, _, _, _ = generated_envelopes
    for _, row in all_envs.iterrows():
        assert row["dynamic_min_kw"] >= row["normal_min_kw"] - 1e-4
        assert row["dynamic_min_kw"] <= row["dynamic_max_kw"] + 1e-4


# 19. Power-flow convergence
def test_powerflow_convergence():
    val_df = pd.read_csv("outputs/csv/envelope_validation.csv")
    assert val_df["powerflow_converged_baseline"].all()
    assert val_df["powerflow_converged_dynamic"].all()


# 20. Phase 1 baseline unchanged
def test_phase1_baseline_unchanged(config):
    net_cfg = config.get("network", {})
    assert net_cfg.get("transformer", {}).get("sn_mva") == 0.250
    assert net_cfg.get("nominal_lv_kv") == 0.415
    assert config.get("neighbourhood", {}).get("households") == 100
    assert config.get("battery", {}).get("energy_capacity_kwh") == 100.0
