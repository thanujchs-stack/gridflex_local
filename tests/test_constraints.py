"""Unit tests for physical and owner constraints."""

from pathlib import Path
import pytest
import yaml

from src.der.constraints import DERConstraintManager

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def constraint_manager():
    config_file = PROJECT_ROOT / "config" / "neighbourhood_config.yaml"
    with open(config_file, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    return DERConstraintManager(config, seed=42)


def test_participation_determinism(constraint_manager):
    der_ids = [f"PV_{i:03d}" for i in range(1, 61)] + ["BESS_COMMUNITY_01"]
    der_types = {d: ("BESS" if "BESS" in d else "PV") for d in der_ids}

    # Run twice with same seed
    part1 = constraint_manager.assign_participation(der_ids, der_types, participation_rate=0.70)
    part2 = constraint_manager.assign_participation(der_ids, der_types, participation_rate=0.70)

    assert part1 == part2
    # BESS must always be True
    assert part1["BESS_COMMUNITY_01"] is True

    # Participation rate should be roughly 70%
    pv_optins = [v for k, v in part1.items() if k != "BESS_COMMUNITY_01"]
    rate = sum(pv_optins) / len(pv_optins)
    assert 0.55 <= rate <= 0.85


def test_battery_reserve_effective_limits(constraint_manager):
    limits = constraint_manager.get_battery_effective_limits(
        energy_capacity_kwh=100.0,
        min_soc=0.20,
        max_soc=0.90
    )
    # Effective min SOC = 0.20 + 0.10 reserve = 0.30
    assert limits["effective_min_soc"] == 0.30
    assert limits["usable_min_kwh"] == 30.0
    assert limits["reserve_kwh"] == 10.0
    assert limits["max_kwh"] == 90.0


def test_ev_departure_slack_calculation(constraint_manager):
    # EV arrives at 19:00, departs at 07:00 next day (12 hrs total).
    # Currently 20:00 (11 hrs until departure). Needs 14.8 kWh at 7.4 kW (2.0 hrs).
    # Buffer is 1.0 hr -> usable time is 10.0 hrs > 2.0 hrs -> can throttle (slack = 7.4 kW)
    slack = constraint_manager.check_ev_shiftable_feasibility(
        current_time_hr=20.0,
        departure_time_hr=7.0,
        remaining_energy_kwh=14.8,
        max_charge_kw=7.4
    )
    assert slack == 7.4

    # Close to departure: currently 05:30 (1.5 hrs until 07:00 departure).
    # Usable time: 1.5 - 1.0 = 0.5 hr. But needs 7.4 kWh (1.0 hr needed > 0.5 hr).
    # Throttle disallowed -> slack = 0.0 kW
    slack_tight = constraint_manager.check_ev_shiftable_feasibility(
        current_time_hr=5.5,
        departure_time_hr=7.0,
        remaining_energy_kwh=7.4,
        max_charge_kw=7.4
    )
    assert slack_tight == 0.0
