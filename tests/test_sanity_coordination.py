"""Pytest suite for Phase 4 Sanity Test.

Validates the 8 mandatory coordinator rules on a single constrained timestep:
1. Select eligible resources.
2. Never allocate more than each resource's available flexibility.
3. Never exceed 10 kW total required flexibility.
4. Report any remaining requirement correctly.
5. Respect battery SOC.
6. Respect EV availability.
7. Preserve shifted energy.
8. Never double-count resources.
Repeated twice for exact determinism.
"""

import pytest
import pandas as pd
import numpy as np

from src.coordination.battery_tracker import BatteryEnergyTracker
from src.coordination.shift_tracker import ShiftEnergyTracker
from scripts.sanity_test_coordination import (
    run_single_timestep_coordination,
    run_omnidirectional_sanity_test,
)


def test_single_constrained_timestep_directional_rules():
    """Verify all 8 rules under strict directional grid coordination."""
    # Run 1
    r1 = run_single_timestep_coordination(required_kw=10.0)

    # 1. Select eligible resources
    assert r1["eligible_resources"] == ["BESS_01", "EV_01", "FL_01"]
    assert any(x[0] == "PV_01" for x in r1["ineligible_resources"])

    # 2. Never allocate more than available
    assert r1["allocations"]["BESS_01"] <= 4.0
    assert r1["allocations"]["EV_01"] <= 3.0
    assert r1["allocations"]["FL_01"] <= 2.0

    # 3. Never exceed 10 kW total required
    assert r1["total_allocated_kw"] <= 10.0
    assert r1["total_allocated_kw"] == 9.0

    # 4. Report remaining requirement correctly
    assert r1["unserved_kw"] == 1.0

    # 5. Respect battery SOC & reserve
    assert r1["battery_reserve_respected"] is True
    assert r1["battery_final_soc"] > 0.30

    # 6. Respect EV availability
    assert r1["allocations"]["EV_01"] > 0.0

    # 7. Preserve shifted energy
    assert r1["shifted_energy_conserved"] is True
    assert np.isclose(r1["shifted_kwh"], 1.25, atol=1e-4)

    # 8. Never double-count resources
    assert r1["selected_ders_count"] == 3

    # Repeat test twice -> identical results
    r2 = run_single_timestep_coordination(required_kw=10.0)
    assert r1 == r2


def test_single_constrained_timestep_omnidirectional_rules():
    """Verify capping at 10 kW when all 4 resources are available."""
    r1 = run_omnidirectional_sanity_test(required_kw=10.0)

    # 2. Never allocate more than available
    assert r1["allocations"]["BATTERY_01"] <= 4.0
    assert r1["allocations"]["PV_CURTAILMENT_01"] <= 5.0
    assert r1["allocations"]["EV_01"] <= 3.0
    assert r1["allocations"]["FLEX_LOAD_01"] <= 2.0

    # 3. Never exceed 10 kW total
    assert r1["total_allocated_kw"] == 10.0

    # 4. Report remaining requirement correctly
    assert r1["unserved_kw"] == 0.0

    # 8. Never double-count resources
    assert r1["unique_ders_count"] == 3  # Battery (4) + PV (5) + EV (1) = 10 kW

    # Repeat test twice -> identical results
    r2 = run_omnidirectional_sanity_test(required_kw=10.0)
    assert r1 == r2
