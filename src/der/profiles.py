"""DER Digital Profiles and Flexibility Passport Generator.

Constructs comprehensive digital models for each DER asset, capturing technical
ratings, physical operating envelopes, availability intervals, and owner constraints.
"""

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional
import pandas as pd
import numpy as np


@dataclass
class DERFlexibilityPassport:
    der_id: str
    der_type: str
    owner_id: str
    rated_power_kw: float
    energy_capacity_kwh: Optional[float]
    current_power_kw: float
    current_soc_pct: Optional[float]
    min_soc_pct: Optional[float]
    max_soc_pct: Optional[float]
    availability_start: str
    availability_end: str
    response_time_minutes: int
    baseline_power_kw: float
    min_power_kw: float
    max_power_kw: float
    flexibility_enabled: bool
    owner_constraint: str
    reserve_requirement: Optional[str]
    control_mode: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def create_der_passports(
    config: Dict[str, Any],
    df_der_reg: pd.DataFrame,
    df_der_ts: pd.DataFrame,
    participation_map: Dict[str, bool]
) -> pd.DataFrame:
    """Generate the standardized DER Flexibility Passport table (one row per asset)."""
    flex_cfg = config.get("flexibility", {})
    pv_flex = flex_cfg.get("pv", {})
    bess_flex = flex_cfg.get("battery", {})
    ev_flex = flex_cfg.get("ev", {})
    fl_flex = flex_cfg.get("flexible_loads", {})

    passports: List[DERFlexibilityPassport] = []

    for _, row in df_der_reg.iterrows():
        der_id = str(row["der_id"])
        der_type = str(row["der_type"])
        owner_id = str(row["owner_id"])
        cap_kw = float(row["rated_capacity_kw"])
        cap_kwh = float(row["rated_energy_kwh"]) if pd.notna(row.get("rated_energy_kwh")) else None
        participates = participation_map.get(der_id, False)

        # Baseline peak power for reference
        ts_col = der_id if der_id in df_der_ts.columns else None
        baseline_peak_kw = float(df_der_ts[ts_col].max()) if ts_col else 0.0

        if der_type == "PV":
            passports.append(DERFlexibilityPassport(
                der_id=der_id,
                der_type="PV",
                owner_id=owner_id,
                rated_power_kw=cap_kw,
                energy_capacity_kwh=None,
                current_power_kw=baseline_peak_kw,
                current_soc_pct=None,
                min_soc_pct=None,
                max_soc_pct=None,
                availability_start="06:00",
                availability_end="18:15",
                response_time_minutes=int(pv_flex.get("response_time_minutes", 1)),
                baseline_power_kw=baseline_peak_kw,
                min_power_kw=0.0,
                max_power_kw=cap_kw,
                flexibility_enabled=participates,
                owner_constraint="Curtailment allowed" if participates else "No curtailment permitted",
                reserve_requirement=None,
                control_mode=str(pv_flex.get("control_mode", "curtailment"))
            ))

        elif der_type == "BESS":
            bess_cfg = config.get("battery", {})
            init_soc = float(bess_cfg.get("initial_soc", 0.50)) * 100.0
            min_soc = float(bess_cfg.get("min_soc", 0.20)) * 100.0
            max_soc = float(bess_cfg.get("max_soc", 0.90)) * 100.0
            reserve_pct = float(bess_flex.get("reserve_soc", 0.10)) * 100.0

            passports.append(DERFlexibilityPassport(
                der_id=der_id,
                der_type="BESS",
                owner_id=owner_id,
                rated_power_kw=cap_kw,
                energy_capacity_kwh=cap_kwh,
                current_power_kw=0.0,
                current_soc_pct=init_soc,
                min_soc_pct=min_soc,
                max_soc_pct=max_soc,
                availability_start="00:00",
                availability_end="23:45",
                response_time_minutes=int(bess_flex.get("response_time_minutes", 1)),
                baseline_power_kw=0.0,
                min_power_kw=-float(bess_cfg.get("max_charge_kw", 25.0)),
                max_power_kw=float(bess_cfg.get("max_discharge_kw", 25.0)),
                flexibility_enabled=participates,
                owner_constraint="Community-owned shared buffer; grid service eligible",
                reserve_requirement=f"{reserve_pct:.0f}% emergency reserve ({reserve_pct*cap_kwh/100:.1f} kWh)",
                control_mode=str(bess_flex.get("control_mode", "bidirectional"))
            ))

        elif der_type == "EV":
            passports.append(DERFlexibilityPassport(
                der_id=der_id,
                der_type="EV",
                owner_id=owner_id,
                rated_power_kw=cap_kw,
                energy_capacity_kwh=cap_kwh,
                current_power_kw=cap_kw,
                current_soc_pct=None,
                min_soc_pct=None,
                max_soc_pct=None,
                availability_start="18:00",
                availability_end="07:30",
                response_time_minutes=int(ev_flex.get("response_time_minutes", 5)),
                baseline_power_kw=cap_kw,
                min_power_kw=0.0,
                max_power_kw=cap_kw,
                flexibility_enabled=participates,
                owner_constraint="Smart charge throttle permitted" if participates else "Immediate full-speed charging required",
                reserve_requirement="Target kWh required before departure deadline",
                control_mode=str(ev_flex.get("control_mode", "unidirectional_throttle"))
            ))

        elif der_type == "FLEXIBLE_LOAD":
            passports.append(DERFlexibilityPassport(
                der_id=der_id,
                der_type="FLEXIBLE_LOAD",
                owner_id=owner_id,
                rated_power_kw=cap_kw,
                energy_capacity_kwh=None,
                current_power_kw=cap_kw,
                current_soc_pct=None,
                min_soc_pct=None,
                max_soc_pct=None,
                availability_start="06:00",
                availability_end="18:00",
                response_time_minutes=int(fl_flex.get("response_time_minutes", 15)),
                baseline_power_kw=cap_kw,
                min_power_kw=0.0,
                max_power_kw=cap_kw,
                flexibility_enabled=participates,
                owner_constraint="Demand response shed/shift eligible" if participates else "Fixed process schedule; no DR",
                reserve_requirement=None,
                control_mode=str(fl_flex.get("control_mode", "discrete_shed_or_shift"))
            ))

    records = [p.to_dict() for p in passports]
    return pd.DataFrame(records)
