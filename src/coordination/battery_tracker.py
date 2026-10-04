"""Battery energy and state of charge (SOC) tracking engine.

Enforces physical energy conservation, round-trip efficiency losses,
and reserve margins across 15-minute operational timesteps.
"""

from typing import Dict, Any, Tuple
import numpy as np


class BatteryEnergyTracker:
    """Stateful physical tracker for community BESS operating across 15-min intervals."""

    def __init__(
        self,
        energy_capacity_kwh: float = 100.0,
        max_charge_kw: float = 25.0,
        max_discharge_kw: float = 25.0,
        initial_soc: float = 0.50,
        min_soc: float = 0.20,
        max_soc: float = 0.90,
        reserve_soc: float = 0.10,
        charge_efficiency: float = 0.95,
        discharge_efficiency: float = 0.95,
        timestep_hours: float = 0.25,
    ):
        self.capacity_kwh = float(energy_capacity_kwh)
        self.max_charge_kw = float(max_charge_kw)
        self.max_discharge_kw = float(max_discharge_kw)
        self.min_soc = float(min_soc)
        self.max_soc = float(max_soc)
        self.reserve_soc = float(reserve_soc)
        self.soc_floor = float(min_soc + reserve_soc)  # Operational floor enforcing reserve (0.30)
        self.eta_ch = float(charge_efficiency)
        self.eta_dis = float(discharge_efficiency)
        self.dt_h = float(timestep_hours)

        self.current_soc: float = float(initial_soc)
        self.history = []

    def reset(self, initial_soc: float = 0.50):
        """Reset battery state to initial condition."""
        self.current_soc = float(initial_soc)
        self.history = []

    def get_available_up_kw(self) -> float:
        """Maximum active discharge power feasible in current interval respecting reserve floor."""
        energy_headroom_kwh = max(0.0, (self.current_soc - self.soc_floor) * self.capacity_kwh)
        # energy = power * dt / eta_dis  ==> power = energy * eta_dis / dt
        power_limit_kw = (energy_headroom_kwh * self.eta_dis) / self.dt_h
        return float(min(self.max_discharge_kw, max(0.0, power_limit_kw)))

    def get_available_down_kw(self) -> float:
        """Maximum active charging power feasible in current interval respecting max SOC."""
        energy_headroom_kwh = max(0.0, (self.max_soc - self.current_soc) * self.capacity_kwh)
        # energy = power * eta_ch * dt ==> power = (energy / eta_ch) / dt
        power_limit_kw = (energy_headroom_kwh / self.eta_ch) / self.dt_h
        return float(min(self.max_charge_kw, max(0.0, power_limit_kw)))

    def step(self, allocated_kw: float, direction: str) -> Tuple[float, float]:
        """Apply flexibility allocation to battery and return (actual_power_kw, new_soc).

        Args:
            allocated_kw: Non-negative requested power magnitude (kW).
            direction: 'UP' (discharge support to grid) or 'DOWN' (charge absorption).

        Returns:
            (actual_kw, new_soc)
        """
        allocated_kw = max(0.0, float(allocated_kw))

        if direction.upper() == "UP":
            # Discharging battery to inject into grid
            avail_up = self.get_available_up_kw()
            actual_kw = min(allocated_kw, avail_up)
            energy_drawn_kwh = (actual_kw * self.dt_h) / self.eta_dis
            delta_soc = energy_drawn_kwh / self.capacity_kwh
            self.current_soc = max(self.soc_floor, self.current_soc - delta_soc)
            energy_kwh = actual_kw * self.dt_h
        elif direction.upper() == "DOWN":
            # Charging battery to absorb surplus grid generation
            avail_down = self.get_available_down_kw()
            actual_kw = min(allocated_kw, avail_down)
            energy_stored_kwh = (actual_kw * self.dt_h) * self.eta_ch
            delta_soc = energy_stored_kwh / self.capacity_kwh
            self.current_soc = min(self.max_soc, self.current_soc + delta_soc)
            energy_kwh = actual_kw * self.dt_h
        else:
            actual_kw = 0.0
            energy_kwh = 0.0

        self.history.append({
            "soc": round(self.current_soc, 4),
            "allocated_kw": round(actual_kw, 3),
            "energy_kwh": round(energy_kwh, 3),
            "direction": direction.upper(),
        })

        return actual_kw, self.current_soc
