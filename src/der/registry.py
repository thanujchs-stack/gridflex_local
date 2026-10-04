"""DER Registry and Asset Models for GridFlex Local.

Maintains an explicit registry of all neighbourhood-scale Distributed Energy Resources:
- Rooftop Solar PV systems
- Community Battery Energy Storage System (BESS)
- Electric Vehicle (EV) chargers
- Flexible and deferrable loads

Provides technical bounds, connection topology, and battery state transitions.
"""

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd


class DERType(str, Enum):
    PV = "PV"
    BESS = "BESS"
    EV = "EV"
    FLEXIBLE_LOAD = "FLEXIBLE_LOAD"


@dataclass
class DERAsset:
    der_id: str
    der_type: DERType
    owner_id: str
    bus_name: str
    rated_capacity_kw: float
    rated_energy_kwh: Optional[float] = None
    min_power_kw: float = 0.0
    max_power_kw: float = 0.0
    power_factor: float = 1.0
    initial_soc: Optional[float] = None
    min_soc: Optional[float] = None
    max_soc: Optional[float] = None
    efficiency_charge: float = 0.95
    efficiency_discharge: float = 0.95
    available: bool = True
    controllable_in_phase1: bool = False
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["der_type"] = self.der_type.value
        return d


class DERRegistry:
    """Central registry of all DER assets connected to the neighbourhood distribution feeder."""

    def __init__(self) -> None:
        self._assets: Dict[str, DERAsset] = {}

    def register(self, asset: DERAsset) -> None:
        if asset.der_id in self._assets:
            raise ValueError(f"Duplicate DER ID detected in registry: {asset.der_id}")
        self._assets[asset.der_id] = asset

    def get(self, der_id: str) -> DERAsset:
        if der_id not in self._assets:
            raise KeyError(f"DER ID not found: {der_id}")
        return self._assets[der_id]

    def list_all(self) -> List[DERAsset]:
        return list(self._assets.values())

    def filter_by_type(self, der_type: DERType) -> List[DERAsset]:
        return [a for a in self._assets.values() if a.der_type == der_type]

    def to_dataframe(self) -> pd.DataFrame:
        records = [a.to_dict() for a in self._assets.values()]
        return pd.DataFrame(records)

    def validate_unique_ids(self) -> bool:
        ids = [a.der_id for a in self._assets.values()]
        return len(ids) == len(set(ids))


class CommunityBatteryModel:
    """State of Charge (SOC) tracking and electrical dynamics for Community BESS.

    Phase 1 Rule: Battery operates in a deterministic baseline mode (default: idle, 0 kW).
    Supports exact discrete-time energy integration:
        SOC(t+1) = SOC(t) + [P_ch(t) * eta_ch * dt - P_dis(t) / eta_dis * dt] / E_nom
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        bess_cfg = config.get("battery", {})
        self.der_id = bess_cfg.get("der_id", "BESS_COMMUNITY_01")
        self.energy_capacity_kwh = float(bess_cfg.get("energy_capacity_kwh", 100.0))
        self.max_charge_kw = float(bess_cfg.get("max_charge_kw", 25.0))
        self.max_discharge_kw = float(bess_cfg.get("max_discharge_kw", 25.0))
        self.initial_soc = float(bess_cfg.get("initial_soc", 0.50))
        self.min_soc = float(bess_cfg.get("min_soc", 0.20))
        self.max_soc = float(bess_cfg.get("max_soc", 0.90))
        self.eta_ch = float(bess_cfg.get("charge_efficiency", 0.95))
        self.eta_dis = float(bess_cfg.get("discharge_efficiency", 0.95))
        self.baseline_mode = bess_cfg.get("baseline_mode", "idle")

    def simulate_baseline_timeseries(
        self,
        time_index: pd.DatetimeIndex,
        scheduled_power_kw: Optional[np.ndarray] = None
    ) -> pd.DataFrame:
        """Simulate battery operation over time_index adhering to strict SOC boundaries.

        Sign convention:
            power_kw > 0 : Discharging (exporting power to feeder)
            power_kw < 0 : Charging (absorbing power from feeder)
            power_kw = 0 : Idle
        """
        n_steps = len(time_index)
        dt_hours = (time_index[1] - time_index[0]).total_seconds() / 3600.0 if n_steps > 1 else 0.25

        soc = np.zeros(n_steps, dtype=float)
        p_actual = np.zeros(n_steps, dtype=float)
        p_charge = np.zeros(n_steps, dtype=float)
        p_discharge = np.zeros(n_steps, dtype=float)

        current_soc = self.initial_soc

        for t in range(n_steps):
            desired_p = 0.0 if scheduled_power_kw is None else scheduled_power_kw[t]

            if desired_p > 0:  # Discharging
                avail_energy_kwh = max(0.0, (current_soc - self.min_soc) * self.energy_capacity_kwh)
                max_allowed_dis_kw = min(self.max_discharge_kw, (avail_energy_kwh * self.eta_dis) / dt_hours)
                actual_p = min(desired_p, max_allowed_dis_kw)
                delta_soc = -(actual_p / self.eta_dis) * dt_hours / self.energy_capacity_kwh
                p_dis = actual_p
                p_ch = 0.0
            elif desired_p < 0:  # Charging
                req_kw = abs(desired_p)
                headroom_kwh = max(0.0, (self.max_soc - current_soc) * self.energy_capacity_kwh)
                max_allowed_ch_kw = min(self.max_charge_kw, headroom_kwh / (self.eta_ch * dt_hours))
                actual_ch_kw = min(req_kw, max_allowed_ch_kw)
                actual_p = -actual_ch_kw
                delta_soc = (actual_ch_kw * self.eta_ch) * dt_hours / self.energy_capacity_kwh
                p_dis = 0.0
                p_ch = actual_ch_kw
            else:  # Idle
                actual_p = 0.0
                delta_soc = 0.0
                p_dis = 0.0
                p_ch = 0.0

            soc[t] = float(np.round(current_soc, 5))
            p_actual[t] = float(np.round(actual_p, 4))
            p_charge[t] = float(np.round(p_ch, 4))
            p_discharge[t] = float(np.round(p_dis, 4))

            current_soc = np.clip(current_soc + delta_soc, self.min_soc, self.max_soc)

        df_bess = pd.DataFrame({
            "timestamp": time_index.strftime("%Y-%m-%d %H:%M"),
            "soc": soc,
            "bess_power_kw": p_actual,
            "bess_charge_kw": p_charge,
            "bess_discharge_kw": p_discharge
        })
        return df_bess


def build_der_registry(
    config: Dict[str, Any],
    pv_metadata: Dict[str, Dict[str, Any]],
    ev_metadata: Dict[str, Dict[str, Any]],
    flex_metadata: Dict[str, Dict[str, Any]],
    household_bus_mapping: Dict[str, str]
) -> DERRegistry:
    """Build and validate the unified DER Registry."""
    reg = DERRegistry()

    # 1. Rooftop Solar PV Systems
    for der_id, meta in pv_metadata.items():
        hid = meta["household_id"]
        bus_name = household_bus_mapping.get(hid, "Bus_Residential_1")
        cap = meta["capacity_kw"]
        reg.register(DERAsset(
            der_id=der_id,
            der_type=DERType.PV,
            owner_id=hid,
            bus_name=bus_name,
            rated_capacity_kw=cap,
            min_power_kw=0.0,
            max_power_kw=cap,
            power_factor=meta.get("power_factor", 1.0),
            notes="Residential rooftop solar PV system"
        ))

    # 2. Community Battery Energy Storage System (BESS)
    bess_cfg = config.get("battery", {})
    reg.register(DERAsset(
        der_id=bess_cfg.get("der_id", "BESS_COMMUNITY_01"),
        der_type=DERType.BESS,
        owner_id="COMMUNITY",
        bus_name=bess_cfg.get("bus_id", "Bus_BESS"),
        rated_capacity_kw=float(bess_cfg.get("max_discharge_kw", 25.0)),
        rated_energy_kwh=float(bess_cfg.get("energy_capacity_kwh", 100.0)),
        min_power_kw=-float(bess_cfg.get("max_charge_kw", 25.0)),
        max_power_kw=float(bess_cfg.get("max_discharge_kw", 25.0)),
        power_factor=float(bess_cfg.get("power_factor", 1.0)),
        initial_soc=float(bess_cfg.get("initial_soc", 0.50)),
        min_soc=float(bess_cfg.get("min_soc", 0.20)),
        max_soc=float(bess_cfg.get("max_soc", 0.90)),
        efficiency_charge=float(bess_cfg.get("charge_efficiency", 0.95)),
        efficiency_discharge=float(bess_cfg.get("discharge_efficiency", 0.95)),
        controllable_in_phase1=False,
        notes="Neighbourhood shared BESS (idle baseline in Phase 1)"
    ))

    # 3. Electric Vehicles (EVs)
    for der_id, meta in ev_metadata.items():
        reg.register(DERAsset(
            der_id=der_id,
            der_type=DERType.EV,
            owner_id=f"EV_USER_{der_id}",
            bus_name="Bus_EV_Hub",
            rated_capacity_kw=meta["charger_rating_kw"],
            rated_energy_kwh=meta["required_energy_kwh"],
            min_power_kw=0.0,
            max_power_kw=meta["charger_rating_kw"],
            power_factor=meta.get("power_factor", 0.98),
            notes="Residential/commuter EV charging load (uncontrolled baseline)"
        ))

    # 4. Flexible / Deferrable Loads
    for lid, meta in flex_metadata.items():
        reg.register(DERAsset(
            der_id=lid,
            der_type=DERType.FLEXIBLE_LOAD,
            owner_id=f"OWNER_{lid}",
            bus_name=meta.get("bus_name", "Bus_Residential_1"),
            rated_capacity_kw=meta["rated_kw"],
            min_power_kw=0.0,
            max_power_kw=meta["rated_kw"],
            notes=f"Flexible load {meta.get('name', lid)} (baseline scheduled in Phase 1)"
        ))

    return reg
