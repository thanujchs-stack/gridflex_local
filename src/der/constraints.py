"""Physical and Owner Constraints for Distributed Energy Resources.

Implements real-world participation constraints:
- Deterministic owner participation assignment (separating technical vs participating flexibility)
- Battery state-of-charge reserve margins
- EV departure deadline and energy delivery constraints
- Operating window and duration bounds for flexible loads
"""

from typing import Any, Dict, List, Optional
import numpy as np


class DERConstraintManager:
    """Manages physical and socio-economic owner constraints on DER flexibility."""

    def __init__(self, config: Dict[str, Any], seed: int = 42) -> None:
        self.config = config
        self.seed = seed
        self.flex_cfg = config.get("flexibility", {})

    def assign_participation(
        self,
        der_ids: List[str],
        der_types: Dict[str, str],
        participation_rate: Optional[float] = None
    ) -> Dict[str, bool]:
        """Deterministically assign owner participation status to each DER.

        Ensures reproducibility across repeated runs.
        Community assets (e.g. Community BESS) always participate (100%).
        """
        if participation_rate is None:
            participation_rate = float(self.flex_cfg.get("default_participation_rate", 0.70))

        rng = np.random.default_rng(self.seed + 1000)
        participation = {}

        for der_id in sorted(der_ids):
            dtype = der_types.get(der_id, "")
            if dtype == "BESS":
                # Community-owned shared battery is operated for neighbourhood benefit
                participation[der_id] = bool(self.flex_cfg.get("battery", {}).get("participating", True))
            else:
                # Private residential / commercial assets participate based on configured rate
                is_opted_in = bool(rng.uniform(0.0, 1.0) < participation_rate)
                participation[der_id] = is_opted_in

        return participation

    def get_battery_effective_limits(
        self,
        energy_capacity_kwh: float,
        min_soc: float,
        max_soc: float
    ) -> Dict[str, float]:
        """Calculate effective SOC boundaries accounting for emergency reserve margin."""
        bess_flex_cfg = self.flex_cfg.get("battery", {})
        reserve_soc = float(bess_flex_cfg.get("reserve_soc", 0.10))

        # Effective minimum SOC including emergency reserve
        effective_min_soc = round(min(max_soc, min_soc + reserve_soc), 4)
        reserve_kwh = round(reserve_soc * energy_capacity_kwh, 4)
        usable_min_kwh = round(effective_min_soc * energy_capacity_kwh, 4)
        max_kwh = round(max_soc * energy_capacity_kwh, 4)

        return {
            "min_soc": min_soc,
            "max_soc": max_soc,
            "reserve_soc": reserve_soc,
            "reserve_kwh": reserve_kwh,
            "effective_min_soc": effective_min_soc,
            "usable_min_kwh": usable_min_kwh,
            "max_kwh": max_kwh
        }

    def check_ev_shiftable_feasibility(
        self,
        current_time_hr: float,
        departure_time_hr: float,
        remaining_energy_kwh: float,
        max_charge_kw: float
    ) -> float:
        """Compute the maximum power that can be deferred without missing departure deadline.

        If remaining time until departure (minus safety buffer) is just enough to deliver
        the required energy at maximum power, flexibility to throttle is restricted.
        """
        ev_cfg = self.flex_cfg.get("ev", {})
        safety_buffer_hr = float(ev_cfg.get("departure_buffer_hours", 1.0))

        # Hours until departure
        if departure_time_hr > current_time_hr:
            available_time_hr = departure_time_hr - current_time_hr
        else:
            # Over-midnight departure (e.g. arrival 19:00, departure 07:30 next morning)
            available_time_hr = (departure_time_hr + 24.0) - current_time_hr

        usable_time_hr = max(0.0, available_time_hr - safety_buffer_hr)
        min_continuous_hours_needed = remaining_energy_kwh / max_charge_kw if max_charge_kw > 0 else 0.0

        if usable_time_hr <= min_continuous_hours_needed:
            # Vehicle must charge continuously to meet departure deadline; zero deferral allowed
            slack_power_kw = 0.0
        else:
            # Vehicle can be completely curtailed/deferred during this timestep
            slack_power_kw = max_charge_kw

        return slack_power_kw
