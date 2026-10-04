"""Data structures and models for Phase 5 Dynamic Operating Envelopes."""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
import pandas as pd


@dataclass
class DynamicOperatingEnvelopeRecord:
    """Represents a unified Dynamic Operating Envelope entry for a single DER at a single timestep."""
    timestamp: pd.Timestamp
    forecast_origin: pd.Timestamp
    der_id: str
    der_type: str
    risk_state: str
    constraint_type: str
    constraint_location: str
    normal_min_kw: float
    normal_max_kw: float
    dynamic_min_kw: float
    dynamic_max_kw: float
    requested_flex_kw: float
    allocated_flex_kw: float
    available_flex_kw: float
    uncertainty_margin_kw: float
    reason: str
    
    # Battery specific fields
    soc: Optional[float] = None
    soc_min: Optional[float] = None
    soc_max: Optional[float] = None
    reserve_soc: Optional[float] = None
    charge_limit_kw: Optional[float] = None
    discharge_limit_kw: Optional[float] = None
    
    # EV specific fields
    arrival_time: Optional[str] = None
    departure_time: Optional[str] = None
    required_energy_kwh: Optional[float] = None
    current_energy_kwh: Optional[float] = None
    v2g_enabled: Optional[bool] = None
    
    # PV specific fields
    available_pv_kw: Optional[float] = None
    normal_export_limit_kw: Optional[float] = None
    dynamic_export_limit_kw: Optional[float] = None
    curtailment_allowed: Optional[bool] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert record to a flat dictionary suitable for CSV export."""
        d = {
            "timestamp": self.timestamp,
            "forecast_origin": self.forecast_origin,
            "der_id": self.der_id,
            "der_type": self.der_type,
            "risk_state": self.risk_state,
            "constraint_type": self.constraint_type,
            "constraint_location": self.constraint_location,
            "normal_min_kw": round(self.normal_min_kw, 2),
            "normal_max_kw": round(self.normal_max_kw, 2),
            "dynamic_min_kw": round(self.dynamic_min_kw, 2),
            "dynamic_max_kw": round(self.dynamic_max_kw, 2),
            "requested_flex_kw": round(self.requested_flex_kw, 2),
            "allocated_flex_kw": round(self.allocated_flex_kw, 2),
            "available_flex_kw": round(self.available_flex_kw, 2),
            "uncertainty_margin_kw": round(self.uncertainty_margin_kw, 2),
            "reason": self.reason,
            "soc": round(self.soc, 4) if self.soc is not None else None,
            "soc_min": round(self.soc_min, 4) if self.soc_min is not None else None,
            "soc_max": round(self.soc_max, 4) if self.soc_max is not None else None,
            "reserve_soc": round(self.reserve_soc, 4) if self.reserve_soc is not None else None,
            "charge_limit_kw": round(self.charge_limit_kw, 2) if self.charge_limit_kw is not None else None,
            "discharge_limit_kw": round(self.discharge_limit_kw, 2) if self.discharge_limit_kw is not None else None,
            "arrival_time": self.arrival_time,
            "departure_time": self.departure_time,
            "required_energy_kwh": round(self.required_energy_kwh, 2) if self.required_energy_kwh is not None else None,
            "current_energy_kwh": round(self.current_energy_kwh, 2) if self.current_energy_kwh is not None else None,
            "v2g_enabled": self.v2g_enabled,
            "available_pv_kw": round(self.available_pv_kw, 2) if self.available_pv_kw is not None else None,
            "normal_export_limit_kw": round(self.normal_export_limit_kw, 2) if self.normal_export_limit_kw is not None else None,
            "dynamic_export_limit_kw": round(self.dynamic_export_limit_kw, 2) if self.dynamic_export_limit_kw is not None else None,
            "curtailment_allowed": self.curtailment_allowed,
        }
        return d


@dataclass
class EnvelopeEventRecord:
    """Records an envelope state transition event for tracking and dashboard display."""
    timestamp: pd.Timestamp
    der_id: str
    previous_state: str
    new_state: str
    previous_limit_kw: float
    new_limit_kw: float
    constraint: str
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "der_id": self.der_id,
            "previous_state": self.previous_state,
            "new_state": self.new_state,
            "previous_limit_kw": round(self.previous_limit_kw, 2),
            "new_limit_kw": round(self.new_limit_kw, 2),
            "constraint": self.constraint,
            "reason": self.reason,
        }
