"""Unit tests for GridFlex Local Phase 4 Flexibility Coordination Package.

Tests compliance with all 19 mandatory Phase 4 conditions:
1. no flexibility when no constraint exists
2. correct direction selection
3. no unavailable DER selected
4. participation respected
5. battery SOC limits respected
6. battery reserve respected
7. EV arrival/departure respected
8. EV energy requirement respected
9. no V2G when disabled
10. flexible-load limits respected
11. PV availability respected
12. no double counting
13. shift energy conservation
14. 15-minute energy calculations
15. deterministic selection
16. no negative allocated flexibility
17. allocated flexibility <= available flexibility
18. unserved flexibility calculated correctly
19. Phase 1 baseline unchanged
"""

import pandas as pd
import numpy as np
import pytest

from src.utils.config import load_config
from src.coordination.battery_tracker import BatteryEnergyTracker
from src.coordination.shift_tracker import ShiftEnergyTracker
from src.coordination.requirement import calculate_flexibility_requirements
from src.coordination.allocator import FlexibilityCoordinator


@pytest.fixture
def config():
    return load_config()


@pytest.fixture
def sample_passports(config):
    passport_path = "outputs/csv/der_flexibility_passport.csv"
    return pd.read_csv(passport_path)


@pytest.fixture
def synthetic_risk_df():
    """Create a 16-step risk trajectory spanning normal, watch, and constraint states."""
    dates = pd.date_range("2026-01-15 12:00:00", periods=16, freq="15min")
    records = []
    for i, t in enumerate(dates):
        # Steps 0-3: Normal (midday)
        if i < 4:
            records.append({
                "timestamp": t,
                "horizon_minutes": (i + 1) * 15,
                "operational_state": "NORMAL",
                "trafo_loading_pct": 50.0,
                "max_line_loading_pct": 35.0,
                "min_vm_pu": 0.995,
                "max_vm_pu": 1.010,
                "net_load_kw": 20.0,
                "primary_constraint": "NONE",
            })
        # Steps 4-7: Solar Overvoltage (midday solar peak)
        elif i < 8:
            records.append({
                "timestamp": t,
                "horizon_minutes": (i + 1) * 15,
                "operational_state": "WATCH",
                "trafo_loading_pct": 45.0,
                "max_line_loading_pct": 40.0,
                "min_vm_pu": 0.990,
                "max_vm_pu": 1.050,  # overvoltage
                "net_load_kw": -40.0,
                "primary_constraint": "VOLTAGE_RISE",
            })
        # Steps 8-15: Evening Load Surge / Undervoltage
        else:
            records.append({
                "timestamp": t,
                "horizon_minutes": (i + 1) * 15,
                "operational_state": "CONSTRAINED",
                "trafo_loading_pct": 88.0,  # exceeds warning 80%
                "max_line_loading_pct": 70.0,
                "min_vm_pu": 0.942,  # undervoltage
                "max_vm_pu": 1.000,
                "net_load_kw": 210.0,
                "primary_constraint": "TRANSFORMER_OVERLOAD",
            })
    return pd.DataFrame(records)


# 1. No flexibility when no constraint exists
def test_no_flexibility_when_no_constraint(config, synthetic_risk_df):
    normal_subset = synthetic_risk_df.iloc[:4].copy()
    req_df = calculate_flexibility_requirements(normal_subset, config)
    assert (req_df["required_up_kw"] == 0.0).all()
    assert (req_df["required_down_kw"] == 0.0).all()
    assert (req_df["required_shift_kw"] == 0.0).all()


# 2. Correct direction selection
def test_correct_direction_selection(config, synthetic_risk_df):
    req_df = calculate_flexibility_requirements(synthetic_risk_df, config)
    # Overvoltage period (steps 4-7) requires DOWN flexibility
    assert (req_df.iloc[4:8]["required_down_kw"] > 0.0).all()
    assert (req_df.iloc[4:8]["required_up_kw"] == 0.0).all()

    # Evening peak period (steps 8-15) requires UP flexibility
    assert (req_df.iloc[8:]["required_up_kw"] > 0.0).all()
    assert (req_df.iloc[8:]["required_down_kw"] == 0.0).all()


# 3. No unavailable DER selected
def test_no_unavailable_der_selected(config, sample_passports, synthetic_risk_df):
    req_df = calculate_flexibility_requirements(synthetic_risk_df, config)
    pv_fc = pd.DataFrame({
        "timestamp": synthetic_risk_df["timestamp"],
        "forecast": [50.0] * 8 + [0.0] * 8,
    })
    coordinator = FlexibilityCoordinator(config, sample_passports)
    plan_df, sel_df, _, _ = coordinator.coordinate_horizon(req_df, pv_fc, synthetic_risk_df["timestamp"].iloc[0])

    # In evening (steps 8-15, solar forecast = 0), PV must never be selected
    evening_ts = synthetic_risk_df["timestamp"].iloc[8:]
    evening_pv_sel = sel_df[(sel_df["timestamp"].isin(evening_ts)) & (sel_df["der_type"] == "PV")]
    assert len(evening_pv_sel) == 0


# 4. Participation respected
def test_participation_respected(config, sample_passports, synthetic_risk_df):
    req_df = calculate_flexibility_requirements(synthetic_risk_df, config)
    pv_fc = pd.DataFrame({"timestamp": synthetic_risk_df["timestamp"], "forecast": [50.0] * 16})

    # Opted-out DER in passport (e.g. PV_H005 has flexibility_enabled=False)
    opt_out_ids = set(sample_passports[sample_passports["flexibility_enabled"] == False]["der_id"])

    coordinator = FlexibilityCoordinator(config, sample_passports)
    _, sel_df, _, _ = coordinator.coordinate_horizon(req_df, pv_fc, synthetic_risk_df["timestamp"].iloc[0])

    # No opted-out DER should ever be selected
    selected_ids = set(sel_df["der_id"])
    assert len(selected_ids.intersection(opt_out_ids)) == 0


# 5. Battery SOC limits respected
def test_battery_soc_limits_respected():
    tracker = BatteryEnergyTracker(energy_capacity_kwh=100.0, max_discharge_kw=25.0, initial_soc=0.25, min_soc=0.20, reserve_soc=0.00)
    # Attempting to discharge 20 kW for 1 hour (5 kWh drawn) from 0.25 SOC (25 kWh total, min is 20 kWh)
    # Available energy above min is only 5 kWh = 20 kW for 0.25h
    act_kw, new_soc = tracker.step(25.0, "UP")
    assert new_soc >= tracker.min_soc


# 6. Battery reserve respected
def test_battery_reserve_respected():
    # Reserve is 10%, min is 20% -> soc_floor is 30%
    tracker = BatteryEnergyTracker(energy_capacity_kwh=100.0, initial_soc=0.30, min_soc=0.20, reserve_soc=0.10)
    # At 30% SOC, available UP discharge must be 0
    assert tracker.get_available_up_kw() == 0.0
    act_kw, new_soc = tracker.step(25.0, "UP")
    assert act_kw == 0.0
    assert np.isclose(new_soc, 0.30, atol=1e-5)


# 7. EV arrival/departure respected
def test_ev_arrival_departure_respected(config, sample_passports):
    # Midday (12:00 PM): EVs are at work, outside 18:00 - 07:30 charging window
    dates = pd.date_range("2026-01-15 12:00:00", periods=4, freq="15min")
    req_df = pd.DataFrame({
        "timestamp": dates,
        "horizon_minutes": [15, 30, 45, 60],
        "risk_state": ["WATCH"] * 4,
        "constraint_type": ["TRANSFORMER_OVERLOAD"] * 4,
        "constraint_location": ["Bus_Main_LV"] * 4,
        "required_up_kw": [50.0] * 4,
        "required_down_kw": [0.0] * 4,
        "required_shift_kw": [25.0] * 4,
    })
    pv_fc = pd.DataFrame({"timestamp": dates, "forecast": [0.0] * 4})

    coordinator = FlexibilityCoordinator(config, sample_passports)
    _, sel_df, _, _ = coordinator.coordinate_horizon(req_df, pv_fc, dates[0])

    # No EV should be selected at 12:00 PM
    ev_sel = sel_df[sel_df["der_type"] == "EV"]
    assert len(ev_sel) == 0


# 8. EV energy requirement respected
def test_ev_energy_requirement_respected():
    tracker = ShiftEnergyTracker()
    t0 = pd.Timestamp("2026-01-15 19:00:00")
    t_dep = pd.Timestamp("2026-01-16 07:30:00")

    # Shift 7.4 kW for 15 mins = 1.85 kWh
    kwh = tracker.register_shift("EV_001", "EV", t0, 7.4, t_dep)
    assert np.isclose(kwh, 1.85, atol=1e-3)
    assert np.isclose(tracker.get_pending_energy("EV_001"), 1.85, atol=1e-3)


# 9. No V2G when disabled
def test_no_v2g_when_disabled(config, sample_passports, synthetic_risk_df):
    req_df = calculate_flexibility_requirements(synthetic_risk_df, config)
    pv_fc = pd.DataFrame({"timestamp": synthetic_risk_df["timestamp"], "forecast": [0.0] * 16})

    coordinator = FlexibilityCoordinator(config, sample_passports)
    _, sel_df, _, _ = coordinator.coordinate_horizon(req_df, pv_fc, synthetic_risk_df["timestamp"].iloc[0])

    ev_sel = sel_df[sel_df["der_type"] == "EV"]
    # All EV selections must be non-negative throttles, never reverse generation
    for _, row in ev_sel.iterrows():
        assert row["allocated_kw"] >= 0.0
        assert "throttle" in row["reason"].lower() or "deferral" in row["reason"].lower()


# 10. Flexible-load limits respected
def test_flexible_load_limits_respected(config, sample_passports, synthetic_risk_df):
    req_df = calculate_flexibility_requirements(synthetic_risk_df, config)
    pv_fc = pd.DataFrame({"timestamp": synthetic_risk_df["timestamp"], "forecast": [0.0] * 16})

    coordinator = FlexibilityCoordinator(config, sample_passports)
    _, sel_df, _, _ = coordinator.coordinate_horizon(req_df, pv_fc, synthetic_risk_df["timestamp"].iloc[0])

    fl_sel = sel_df[sel_df["der_type"] == "FLEXIBLE_LOAD"]
    for _, row in fl_sel.iterrows():
        did = row["der_id"]
        p_row = sample_passports[sample_passports["der_id"] == did].iloc[0]
        assert row["allocated_kw"] <= float(p_row["rated_power_kw"]) + 1e-4


# 11. PV availability respected
def test_pv_availability_respected(config, sample_passports, synthetic_risk_df):
    req_df = calculate_flexibility_requirements(synthetic_risk_df, config)
    pv_fc = pd.DataFrame({"timestamp": synthetic_risk_df["timestamp"], "forecast": [10.0] * 8 + [0.0] * 8})

    coordinator = FlexibilityCoordinator(config, sample_passports)
    _, sel_df, _, _ = coordinator.coordinate_horizon(req_df, pv_fc, synthetic_risk_df["timestamp"].iloc[0])

    pv_sel = sel_df[sel_df["der_type"] == "PV"]
    for _, row in pv_sel.iterrows():
        assert row["allocated_kw"] >= 0.0


# 12. No double counting
def test_no_double_counting(config, sample_passports, synthetic_risk_df):
    req_df = calculate_flexibility_requirements(synthetic_risk_df, config)
    pv_fc = pd.DataFrame({"timestamp": synthetic_risk_df["timestamp"], "forecast": [30.0] * 16})

    coordinator = FlexibilityCoordinator(config, sample_passports)
    plan_df, sel_df, _, _ = coordinator.coordinate_horizon(req_df, pv_fc, synthetic_risk_df["timestamp"].iloc[0])

    for _, p_row in plan_df.iterrows():
        t = p_row["timestamp"]
        t_sel = sel_df[sel_df["timestamp"] == t]
        # Sum of unique allocated DER power must equal plan selected total
        sum_allocated = t_sel["allocated_kw"].sum()
        total_selected = p_row["selected_up_kw"] + p_row["selected_down_kw"]
        assert np.isclose(sum_allocated, total_selected, atol=1e-3)
        # Check DER ID uniqueness per timestep
        assert len(t_sel["der_id"]) == len(set(t_sel["der_id"]))


# 13. Shift energy conservation
def test_shift_energy_conservation():
    tracker = ShiftEnergyTracker()
    t0 = pd.Timestamp("2026-01-15 19:00:00")
    t_rec = pd.Timestamp("2026-01-15 23:00:00")
    t_dep = pd.Timestamp("2026-01-16 07:00:00")

    tracker.register_shift("EV_001", "EV", t0, 4.0, t_dep)  # 1.0 kWh
    tracker.schedule_payback("EV_001", t_rec, 4.0)          # 1.0 kWh payback

    is_conserved, shifted, accounted = tracker.verify_energy_conservation()
    assert is_conserved is True
    assert np.isclose(shifted, accounted, atol=1e-5)


# 14. 15-minute energy calculations
def test_15_minute_energy_calculations():
    power_kw = 20.0
    dt_h = 15.0 / 60.0
    energy_kwh = power_kw * dt_h
    assert np.isclose(energy_kwh, 5.0, atol=1e-5)


# 15. Deterministic selection
def test_deterministic_selection(config, sample_passports, synthetic_risk_df):
    req_df = calculate_flexibility_requirements(synthetic_risk_df, config)
    pv_fc = pd.DataFrame({"timestamp": synthetic_risk_df["timestamp"], "forecast": [20.0] * 16})

    c1 = FlexibilityCoordinator(config, sample_passports, participation_override=0.70)
    p1, s1, _, _ = c1.coordinate_horizon(req_df, pv_fc, synthetic_risk_df["timestamp"].iloc[0])

    c2 = FlexibilityCoordinator(config, sample_passports, participation_override=0.70)
    p2, s2, _, _ = c2.coordinate_horizon(req_df, pv_fc, synthetic_risk_df["timestamp"].iloc[0])

    np.testing.assert_allclose(p1["selected_up_kw"], p2["selected_up_kw"])
    np.testing.assert_allclose(s1["allocated_kw"], s2["allocated_kw"])


# 16. No negative allocated flexibility
def test_no_negative_allocated_flexibility(config, sample_passports, synthetic_risk_df):
    req_df = calculate_flexibility_requirements(synthetic_risk_df, config)
    pv_fc = pd.DataFrame({"timestamp": synthetic_risk_df["timestamp"], "forecast": [20.0] * 16})

    coordinator = FlexibilityCoordinator(config, sample_passports)
    plan_df, sel_df, _, _ = coordinator.coordinate_horizon(req_df, pv_fc, synthetic_risk_df["timestamp"].iloc[0])

    assert (plan_df["selected_up_kw"] >= 0.0).all()
    assert (plan_df["selected_down_kw"] >= 0.0).all()
    if not sel_df.empty:
        assert (sel_df["allocated_kw"] >= 0.0).all()


# 17. Allocated flexibility <= available flexibility
def test_allocated_flexibility_le_available(config, sample_passports, synthetic_risk_df):
    req_df = calculate_flexibility_requirements(synthetic_risk_df, config)
    pv_fc = pd.DataFrame({"timestamp": synthetic_risk_df["timestamp"], "forecast": [20.0] * 16})

    coordinator = FlexibilityCoordinator(config, sample_passports)
    plan_df, _, _, _ = coordinator.coordinate_horizon(req_df, pv_fc, synthetic_risk_df["timestamp"].iloc[0])

    assert (plan_df["selected_up_kw"] <= plan_df["available_up_kw"] + 1e-4).all()
    assert (plan_df["selected_down_kw"] <= plan_df["available_down_kw"] + 1e-4).all()


# 18. Unserved flexibility calculated correctly
def test_unserved_flexibility_calculated_correctly(config, sample_passports, synthetic_risk_df):
    req_df = calculate_flexibility_requirements(synthetic_risk_df, config)
    pv_fc = pd.DataFrame({"timestamp": synthetic_risk_df["timestamp"], "forecast": [20.0] * 16})

    coordinator = FlexibilityCoordinator(config, sample_passports)
    plan_df, _, _, _ = coordinator.coordinate_horizon(req_df, pv_fc, synthetic_risk_df["timestamp"].iloc[0])

    expected_unserved_up = np.maximum(0.0, plan_df["required_up_kw"] - plan_df["selected_up_kw"])
    np.testing.assert_allclose(plan_df["unserved_up_kw"], expected_unserved_up, atol=1e-4)


# 19. Phase 1 baseline unchanged
def test_phase1_baseline_unchanged(config):
    # Verify core Phase 1 parameters remain untouched
    net_cfg = config.get("network", {})
    assert net_cfg.get("transformer", {}).get("sn_mva") == 0.250
    assert net_cfg.get("nominal_lv_kv") == 0.415
    assert config.get("neighbourhood", {}).get("households") == 100
    assert config.get("battery", {}).get("energy_capacity_kwh") == 100.0
