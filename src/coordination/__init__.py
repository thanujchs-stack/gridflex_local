"""GridFlex Local - Phase 4 Flexibility Coordination Package.

Provides transparent, deterministic flexibility coordination:
- Requirement calculation from forecast and risk states
- Physical DER selection and merit-order allocation
- Physical battery SOC accounting with reserve enforcement
- EV and flexible load energy shift accounting
- Participation sensitivity and fairness tracking
"""

from src.coordination.requirement import calculate_flexibility_requirements
from src.coordination.battery_tracker import BatteryEnergyTracker
from src.coordination.shift_tracker import ShiftEnergyTracker
from src.coordination.allocator import FlexibilityCoordinator
from src.coordination.sensitivity import run_participation_sensitivity

__all__ = [
    "calculate_flexibility_requirements",
    "BatteryEnergyTracker",
    "ShiftEnergyTracker",
    "FlexibilityCoordinator",
    "run_participation_sensitivity",
]
