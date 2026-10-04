"""Dynamic Operating Envelope Calculator for GridFlex Local.

Translates forecasts, local grid risk, flexibility coordination plans, and
feeder constraints into time-varying operating envelopes for all controllable DERs.
"""

from typing import Dict, List, Any, Tuple, Optional
import numpy as np
import pandas as pd

from src.envelopes.models import DynamicOperatingEnvelopeRecord
from src.envelopes.hysteresis import HysteresisController


class DynamicOperatingEnvelopeCalculator:
    """Calculates normal and dynamic operating envelopes across the forecast horizon."""

    def __init__(
        self,
        config: Dict[str, Any],
        der_passports_df: pd.DataFrame,
        der_registry_df: pd.DataFrame,
        initial_bess_soc: float = 0.50,
    ):
        self.config = config
        self.passports_df = der_passports_df.drop_duplicates(subset=["der_id"]).copy() if "der_id" in der_passports_df.columns else der_passports_df.copy()
        self.registry_df = der_registry_df.copy()
        self.bess_soc = initial_bess_soc

        # Join bus_name from registry if not in passports
        if "bus_name" not in self.passports_df.columns:
            bus_map = dict(zip(self.registry_df["der_id"], self.registry_df["bus_name"]))
            self.passports_df["bus_name"] = self.passports_df["der_id"].map(bus_map).fillna("Bus_Residential_1")

        # DOE config
        doe_cfg = config.get("doe", {})
        self.hysteresis = HysteresisController(config)
        self.unc_factor = float(doe_cfg.get("uncertainty_margin", {}).get("factor", 0.15))
        self.unc_enabled = bool(doe_cfg.get("uncertainty_margin", {}).get("enabled", True))

        # Battery parameters
        bat_cfg = config.get("battery", {})
        flex_bat = config.get("flexibility", {}).get("battery", {})
        self.bess_cap_kwh = float(bat_cfg.get("energy_capacity_kwh", 100.0))
        self.bess_max_charge_kw = float(bat_cfg.get("max_charge_kw", 25.0))
        self.bess_max_discharge_kw = float(bat_cfg.get("max_discharge_kw", 25.0))
        self.bess_min_soc = float(bat_cfg.get("min_soc", 0.20))
        self.bess_max_soc = float(bat_cfg.get("max_soc", 0.90))
        self.bess_reserve_soc = float(flex_bat.get("reserve_soc", 0.10))
        self.bess_soc_floor = self.bess_min_soc + self.bess_reserve_soc  # 0.30
        self.charge_eff = float(bat_cfg.get("charge_efficiency", 0.95))
        self.discharge_eff = float(bat_cfg.get("discharge_efficiency", 0.95))
        self.dt_h = 0.25

    def _get_electrical_sensitivity_weight(self, der_bus: str, constraint_type: str, constraint_location: str) -> float:
        """Calculate electrical impact factor (0.0 to 1.0) based on feeder topology and constraint."""
        if constraint_type in ["NONE", ""]:
            return 0.0

        # Substation transformer overload impacts all downstream DERs equally
        if constraint_type == "TRANSFORMER_OVERLOAD":
            return 1.0

        # Voltage drop / rise constraints have high local sensitivity
        if constraint_type in ["VOLTAGE_DROP", "VOLTAGE_RISE"]:
            if constraint_location == der_bus:
                return 1.0
            if "Residential" in str(constraint_location) and "Residential" in str(der_bus):
                # Coupling between residential buses along the same radial lateral
                b_target = str(constraint_location).split("_")[-1]
                b_der = str(der_bus).split("_")[-1]
                if b_target == "3":
                    return 0.70 if b_der == "2" else 0.40
                elif b_target == "2":
                    return 0.70 if b_der in ["1", "3"] else 0.50
                return 0.50
            if der_bus in ["Bus_Main_LV", "Bus_Commercial"]:
                return 0.60
            return 0.20

        # Line overload
        if "Line" in constraint_location or constraint_type == "LINE_OVERLOAD":
            return 0.80 if "Residential" in str(der_bus) else 0.30

        return 0.50

    def compute_envelopes(
        self,
        coordination_plan_df: pd.DataFrame,
        flexibility_selection_df: pd.DataFrame,
        risk_forecast_df: pd.DataFrame,
        pv_forecast_df: pd.DataFrame,
        load_forecast_df: pd.DataFrame,
    ) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """Compute complete dynamic operating envelopes for all DERs across the horizon.

        Returns:
            (all_envelopes_df, pv_envelopes_df, battery_envelopes_df, ev_envelopes_df, fl_envelopes_df)
        """
        all_records: List[DynamicOperatingEnvelopeRecord] = []
        pv_rows: List[Dict[str, Any]] = []
        battery_rows: List[Dict[str, Any]] = []
        ev_rows: List[Dict[str, Any]] = []
        fl_rows: List[Dict[str, Any]] = []

        coordination_plan_df = coordination_plan_df.copy()
        coordination_plan_df["timestamp"] = pd.to_datetime(coordination_plan_df["timestamp"])
        flexibility_selection_df = flexibility_selection_df.copy()
        flexibility_selection_df["timestamp"] = pd.to_datetime(flexibility_selection_df["timestamp"])
        risk_forecast_df = risk_forecast_df.copy()
        risk_forecast_df["timestamp"] = pd.to_datetime(risk_forecast_df["timestamp"])
        pv_forecast_df = pv_forecast_df.copy()
        pv_forecast_df["timestamp"] = pd.to_datetime(pv_forecast_df["timestamp"])
        load_forecast_df = load_forecast_df.copy()
        load_forecast_df["timestamp"] = pd.to_datetime(load_forecast_df["timestamp"])

        forecast_origin = pd.to_datetime(coordination_plan_df["forecast_origin"].iloc[0])
        current_soc = self.bess_soc

        for _, plan_row in coordination_plan_df.iterrows():
            t = plan_row["timestamp"]
            h_mins = int(plan_row["horizon_minutes"])

            # 1. Evaluate risk state through Hysteresis Controller
            raw_risk = str(plan_row["risk_state"])
            c_type = str(plan_row["constraint_type"])
            c_loc = str(plan_row["constraint_location"])

            # Find matching risk forecast row for electrical telemetry
            r_match = risk_forecast_df[risk_forecast_df["timestamp"] == t]
            trafo_pct = float(r_match["trafo_loading_pct"].iloc[0]) if not r_match.empty else 50.0
            min_vm = float(r_match["min_vm_pu"].iloc[0]) if not r_match.empty else 1.00
            max_vm = float(r_match["max_vm_pu"].iloc[0]) if not r_match.empty else 1.00

            hyst_res = self.hysteresis.evaluate_state(
                raw_risk_state=raw_risk,
                trafo_loading_pct=trafo_pct,
                min_vm_pu=min_vm,
                max_vm_pu=max_vm,
                primary_constraint=c_type,
            )
            eff_state = hyst_res["effective_state"]
            eff_constraint = hyst_res["primary_constraint"]

            # 2. Extract forecast uncertainties
            pv_m = pv_forecast_df[pv_forecast_df["timestamp"] == t]
            load_m = load_forecast_df[load_forecast_df["timestamp"] == t]

            pv_fc_val = float(pv_m["forecast"].iloc[0]) if not pv_m.empty else 0.0
            pv_unc_kw = float(pv_m["upper_bound"].iloc[0] - pv_m["lower_bound"].iloc[0]) if not pv_m.empty else 0.0
            load_unc_kw = float(load_m["upper_bound"].iloc[0] - load_m["lower_bound"].iloc[0]) if not load_m.empty else 0.0

            # Step-specific selections
            step_selections = flexibility_selection_df[flexibility_selection_df["timestamp"] == t]

            # 3. Calculate envelope for each registered DER
            for _, p_row in self.passports_df.iterrows():
                did = str(p_row["der_id"])
                dtype = str(p_row["der_type"])
                bus = str(p_row.get("bus_name", "Bus_Residential_1"))
                rated_kw = float(p_row.get("rated_power_kw", p_row.get("rated_capacity_kw", 3.0)))
                opt_in = bool(p_row.get("flexibility_enabled", p_row.get("owner_participation", True)))

                # Check if this specific DER was selected in Phase 4 coordination
                sel_match = step_selections[step_selections["der_id"] == did] if not step_selections.empty else pd.DataFrame()
                alloc_col = "allocated_kw" if "allocated_kw" in sel_match.columns else ("allocated_flex_kw" if "allocated_flex_kw" in sel_match.columns else None)
                alloc_kw = float(sel_match[alloc_col].iloc[0]) if (not sel_match.empty and alloc_col is not None) else 0.0

                req_col = "requested_kw" if "requested_kw" in sel_match.columns else ("required_kw" if "required_kw" in sel_match.columns else ("required_flex_kw" if "required_flex_kw" in sel_match.columns else None))
                req_kw = float(sel_match[req_col].iloc[0]) if (not sel_match.empty and req_col is not None) else 0.0

                sens_w = self._get_electrical_sensitivity_weight(bus, eff_constraint, c_loc)

                # ==============================================================
                # A. PV EXPORT OPERATING ENVELOPE
                # ==============================================================
                if dtype == "PV":
                    # Available solar generation for this panel at time t
                    # Scaled by aggregate PV forecast relative to nominal peak
                    pv_avail = min(rated_kw, rated_kw * (pv_fc_val / 90.0)) if pv_fc_val > 0.0 else 0.0
                    unc_margin_kw = (self.unc_factor * (pv_unc_kw / 60.0) * sens_w) if self.unc_enabled else 0.0

                    normal_min = 0.0
                    normal_max = rated_kw
                    curtailment_allowed = opt_in and ("curtailment" in str(p_row.get("owner_constraint", "")).lower() or opt_in)

                    # Dynamic export logic
                    if eff_state == "NORMAL":
                        dyn_export = normal_max
                        reason = "Normal feeder conditions: unconstrained solar export permitted"
                    elif eff_state == "WATCH":
                        # Modest precautionary monitoring; no curtailment unless voltage rise
                        if eff_constraint == "VOLTAGE_RISE" and curtailment_allowed:
                            dyn_export = max(0.0, normal_max - alloc_kw - unc_margin_kw)
                            reason = f"Precautionary export reduction against voltage rise at {c_loc}"
                        else:
                            dyn_export = normal_max
                            reason = "Watch state: unconstrained export with active monitoring"
                    else:  # CONSTRAINED or CRITICAL
                        if eff_constraint in ["VOLTAGE_RISE", "REVERSE_POWER"]:
                            if curtailment_allowed:
                                scale = 0.50 if eff_state == "CRITICAL" else 0.25
                                base_curt = max(alloc_kw, normal_max * scale * sens_w)
                                dyn_export = max(0.0, normal_max - base_curt - unc_margin_kw)
                                reason = f"Solar export curtailed to mitigate {eff_constraint} at {c_loc}"
                            else:
                                dyn_export = normal_max
                                reason = f"{eff_constraint} active but owner profile prohibits curtailment"
                        else:
                            # In peak load or undervoltage, solar generation helps the feeder
                            dyn_export = normal_max
                            reason = f"Solar export allowed without restriction to support feeder load during {eff_constraint}"

                    # Enforce strict physical bounds
                    dyn_export = min(normal_max, max(0.0, dyn_export))
                    dyn_min = 0.0
                    dyn_max = dyn_export

                    record = DynamicOperatingEnvelopeRecord(
                        timestamp=t,
                        forecast_origin=forecast_origin,
                        der_id=did,
                        der_type=dtype,
                        risk_state=eff_state,
                        constraint_type=eff_constraint,
                        constraint_location=c_loc,
                        normal_min_kw=normal_min,
                        normal_max_kw=normal_max,
                        dynamic_min_kw=dyn_min,
                        dynamic_max_kw=dyn_max,
                        requested_flex_kw=req_kw,
                        allocated_flex_kw=alloc_kw,
                        available_flex_kw=pv_avail,
                        uncertainty_margin_kw=unc_margin_kw,
                        reason=reason,
                        available_pv_kw=pv_avail,
                        normal_export_limit_kw=normal_max,
                        dynamic_export_limit_kw=dyn_export,
                        curtailment_allowed=curtailment_allowed,
                    )
                    all_records.append(record)
                    pv_rows.append({
                        "timestamp": t,
                        "der_id": did,
                        "available_pv_kw": round(pv_avail, 2),
                        "normal_export_limit_kw": round(normal_max, 2),
                        "dynamic_export_limit_kw": round(dyn_export, 2),
                        "minimum_export_limit_kw": 0.0,
                        "maximum_export_limit_kw": round(normal_max, 2),
                        "curtailment_allowed": curtailment_allowed,
                        "curtailment_applied_kw": round(max(0.0, pv_avail - dyn_export), 2),
                        "uncertainty_margin_kw": round(unc_margin_kw, 2),
                        "risk_state": eff_state,
                        "constraint_type": eff_constraint,
                        "reason": reason,
                    })

                # ==============================================================
                # B. BATTERY CHARGE/DISCHARGE OPERATING ENVELOPE
                # ==============================================================
                elif dtype == "BESS":
                    # Calculate available energy above 30% reserve floor
                    avail_dis_kwh = max(0.0, (current_soc - self.bess_soc_floor) * self.bess_cap_kwh * self.discharge_eff)
                    p_dis_avail = min(self.bess_max_discharge_kw, avail_dis_kwh / self.dt_h)

                    # Available headroom below 90% max SOC
                    avail_chg_kwh = max(0.0, (self.bess_max_soc - current_soc) * self.bess_cap_kwh / self.charge_eff)
                    p_chg_avail = min(self.bess_max_charge_kw, avail_chg_kwh / self.dt_h)

                    normal_min = -self.bess_max_charge_kw
                    normal_max = self.bess_max_discharge_kw

                    # Dynamic envelope logic
                    if eff_state == "NORMAL":
                        dyn_charge = p_chg_avail
                        dyn_discharge = p_dis_avail
                        reason = "Normal conditions: full battery operating capability available"
                    elif eff_constraint in ["TRANSFORMER_OVERLOAD", "VOLTAGE_DROP"]:
                        # Restrict charging to 0 to prevent worsening grid load; allow discharge up to rating
                        dyn_charge = 0.0
                        dyn_discharge = p_dis_avail
                        reason = f"Battery charging restricted and discharge permitted to relieve {eff_constraint}"
                    elif eff_constraint in ["VOLTAGE_RISE", "REVERSE_POWER"]:
                        # Restrict discharge to 0 to prevent worsening voltage rise; permit charging to absorb solar
                        dyn_charge = p_chg_avail
                        dyn_discharge = 0.0
                        reason = f"Battery discharge restricted and charging permitted to absorb surplus solar"
                    else:
                        dyn_charge = p_chg_avail
                        dyn_discharge = p_dis_avail
                        reason = "Watch state: operating within verified SOC limits"

                    dyn_min = -dyn_charge
                    dyn_max = dyn_discharge

                    record = DynamicOperatingEnvelopeRecord(
                        timestamp=t,
                        forecast_origin=forecast_origin,
                        der_id=did,
                        der_type=dtype,
                        risk_state=eff_state,
                        constraint_type=eff_constraint,
                        constraint_location=c_loc,
                        normal_min_kw=normal_min,
                        normal_max_kw=normal_max,
                        dynamic_min_kw=dyn_min,
                        dynamic_max_kw=dyn_max,
                        requested_flex_kw=req_kw,
                        allocated_flex_kw=alloc_kw,
                        available_flex_kw=p_dis_avail if "DROP" in eff_constraint or "OVERLOAD" in eff_constraint else p_chg_avail,
                        uncertainty_margin_kw=0.0,
                        reason=reason,
                        soc=current_soc,
                        soc_min=self.bess_min_soc,
                        soc_max=self.bess_max_soc,
                        reserve_soc=self.bess_reserve_soc,
                        charge_limit_kw=dyn_charge,
                        discharge_limit_kw=dyn_discharge,
                    )
                    all_records.append(record)
                    battery_rows.append({
                        "timestamp": t,
                        "der_id": did,
                        "max_charge_kw": round(self.bess_max_charge_kw, 2),
                        "dynamic_charge_limit_kw": round(dyn_charge, 2),
                        "max_discharge_kw": round(self.bess_max_discharge_kw, 2),
                        "dynamic_discharge_limit_kw": round(dyn_discharge, 2),
                        "soc": round(current_soc, 4),
                        "minimum_soc": round(self.bess_min_soc, 4),
                        "maximum_soc": round(self.bess_max_soc, 4),
                        "reserve_soc": round(self.bess_reserve_soc, 4),
                        "risk_state": eff_state,
                        "constraint_type": eff_constraint,
                        "reason": reason,
                    })

                    # Stateful SOC evolution for next timestep:
                    # If active discharge was coordinated, subtract energy
                    if alloc_kw > 0.0:
                        energy_drawn = (alloc_kw * self.dt_h) / self.discharge_eff
                        current_soc = max(self.bess_soc_floor, current_soc - (energy_drawn / self.bess_cap_kwh))

                # ==============================================================
                # C. EV CHARGING OPERATING ENVELOPE
                # ==============================================================
                elif dtype == "EV":
                    hour_float = t.hour + t.minute / 60.0
                    is_connected = (hour_float >= 18.0) or (hour_float <= 7.5)
                    normal_min = 0.0
                    normal_max = 7.4
                    unc_margin_kw = (self.unc_factor * (load_unc_kw / 20.0) * sens_w) if self.unc_enabled else 0.0

                    if not is_connected:
                        dyn_charge = 0.0
                        reason = "EV outside availability window (disconnected)"
                    elif eff_state == "NORMAL":
                        dyn_charge = normal_max
                        reason = "Normal conditions: full Level 2 charging permitted"
                    elif eff_constraint in ["TRANSFORMER_OVERLOAD", "VOLTAGE_DROP"]:
                        if opt_in and alloc_kw > 0.0:
                            dyn_charge = max(0.0, normal_max - alloc_kw - unc_margin_kw)
                            reason = f"EV charging rate throttled to mitigate {eff_constraint} at {c_loc}"
                        else:
                            dyn_charge = normal_max
                            reason = "EV charging permitted within charger rating"
                    else:
                        dyn_charge = normal_max
                        reason = "Charging permitted to support feeder demand"

                    dyn_min = 0.0
                    dyn_max = dyn_charge

                    record = DynamicOperatingEnvelopeRecord(
                        timestamp=t,
                        forecast_origin=forecast_origin,
                        der_id=did,
                        der_type=dtype,
                        risk_state=eff_state,
                        constraint_type=eff_constraint,
                        constraint_location=c_loc,
                        normal_min_kw=normal_min,
                        normal_max_kw=normal_max,
                        dynamic_min_kw=dyn_min,
                        dynamic_max_kw=dyn_max,
                        requested_flex_kw=req_kw,
                        allocated_flex_kw=alloc_kw,
                        available_flex_kw=max(alloc_kw, normal_max if is_connected else 0.0),
                        uncertainty_margin_kw=unc_margin_kw,
                        reason=reason,
                        arrival_time="18:00",
                        departure_time="07:30",
                        required_energy_kwh=15.0,
                        current_energy_kwh=round(dyn_charge * self.dt_h, 2),
                        charge_limit_kw=dyn_charge,
                        v2g_enabled=False,  # V2G strictly disabled
                    )
                    all_records.append(record)
                    ev_rows.append({
                        "timestamp": t,
                        "der_id": did,
                        "max_charge_kw": round(normal_max, 2),
                        "dynamic_charge_limit_kw": round(dyn_charge, 2),
                        "allowed_start_time": "18:00",
                        "allowed_end_time": "07:30",
                        "required_energy_kwh": 15.0,
                        "current_energy_kwh": round(dyn_charge * self.dt_h, 2),
                        "v2g_enabled": False,
                        "risk_state": eff_state,
                        "constraint_type": eff_constraint,
                        "reason": reason,
                    })

                # ==============================================================
                # D. FLEXIBLE LOAD OPERATING ENVELOPE
                # ==============================================================
                elif dtype == "FLEXIBLE_LOAD":
                    hour_float = t.hour + t.minute / 60.0
                    s_h = 9.0 if did == "FL002" else (11.0 if did == "FL003" else 5.5)
                    e_h = 17.5 if did == "FL002" else (14.5 if did == "FL003" else 8.0)
                    is_active_window = s_h <= hour_float < e_h

                    min_kw = 0.5  # Standby / minimum equipment draw (not 0 unless interruptible)
                    normal_min = min_kw if is_active_window else 0.0
                    normal_max = rated_kw if is_active_window else 0.0
                    unc_margin_kw = (self.unc_factor * (load_unc_kw / 3.0) * sens_w) if self.unc_enabled else 0.0

                    if not is_active_window:
                        dyn_min = 0.0
                        dyn_max = 0.0
                        reason = "Flexible load outside scheduled operating window"
                    elif eff_state == "NORMAL":
                        dyn_min = normal_min
                        dyn_max = normal_max
                        reason = "Normal conditions: full operating range available"
                    elif eff_constraint in ["TRANSFORMER_OVERLOAD", "VOLTAGE_DROP"]:
                        if opt_in and alloc_kw > 0.0:
                            dyn_max = max(min_kw, normal_max - alloc_kw - unc_margin_kw)
                            dyn_min = min_kw
                            reason = f"Flexible load throttled/shifted to mitigate {eff_constraint}"
                        else:
                            dyn_min = normal_min
                            dyn_max = normal_max
                            reason = "Flexible load operating within baseline window"
                    else:
                        dyn_min = normal_min
                        dyn_max = normal_max
                        reason = "Normal scheduled operation"

                    record = DynamicOperatingEnvelopeRecord(
                        timestamp=t,
                        forecast_origin=forecast_origin,
                        der_id=did,
                        der_type=dtype,
                        risk_state=eff_state,
                        constraint_type=eff_constraint,
                        constraint_location=c_loc,
                        normal_min_kw=normal_min,
                        normal_max_kw=normal_max,
                        dynamic_min_kw=dyn_min,
                        dynamic_max_kw=dyn_max,
                        requested_flex_kw=req_kw,
                        allocated_flex_kw=alloc_kw,
                        available_flex_kw=rated_kw if is_active_window else 0.0,
                        uncertainty_margin_kw=unc_margin_kw,
                        reason=reason,
                    )
                    all_records.append(record)
                    fl_rows.append({
                        "timestamp": t,
                        "der_id": did,
                        "baseline_kw": round(rated_kw, 2),
                        "minimum_kw": round(min_kw, 2),
                        "maximum_kw": round(normal_max, 2),
                        "dynamic_min_kw": round(dyn_min, 2),
                        "dynamic_max_kw": round(dyn_max, 2),
                        "availability_window": f"{int(s_h):02d}:00 - {int(e_h):02d}:30",
                        "risk_state": eff_state,
                        "constraint_type": eff_constraint,
                        "reason": reason,
                    })

        all_envelopes_df = pd.DataFrame([r.to_dict() for r in all_records])
        pv_envelopes_df = pd.DataFrame(pv_rows)
        battery_envelopes_df = pd.DataFrame(battery_rows)
        ev_envelopes_df = pd.DataFrame(ev_rows)
        fl_envelopes_df = pd.DataFrame(fl_rows)

        return all_envelopes_df, pv_envelopes_df, battery_envelopes_df, ev_envelopes_df, fl_envelopes_df
