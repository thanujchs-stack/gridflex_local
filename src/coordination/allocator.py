"""Deterministic Flexibility Coordinator for GridFlex Local.

Executes transparent merit-order allocation of available DER flexibility
in response to forecast grid constraints without issuing actual hardware dispatch.
"""

from typing import Dict, List, Any, Tuple, Optional
import numpy as np
import pandas as pd

from src.coordination.battery_tracker import BatteryEnergyTracker
from src.coordination.shift_tracker import ShiftEnergyTracker


class FlexibilityCoordinator:
    """Coordinates available DER flexibility against forecast local grid constraints."""

    def __init__(
        self,
        config: Dict[str, Any],
        der_passports_df: pd.DataFrame,
        participation_override: Optional[float] = None,
        initial_bess_soc: float = 0.50,
    ):
        self.config = config
        self.passports_df = der_passports_df.drop_duplicates(subset=["der_id"]).copy() if "der_id" in der_passports_df.columns else der_passports_df.copy()
        self.participation_rate = (
            participation_override
            if participation_override is not None
            else float(config.get("flexibility", {}).get("default_participation_rate", 0.70))
        )

        # Initialize physical trackers
        bat_cfg = config.get("battery", {})
        flex_cfg = config.get("flexibility", {})
        self.battery_tracker = BatteryEnergyTracker(
            energy_capacity_kwh=float(bat_cfg.get("energy_capacity_kwh", 100.0)),
            max_charge_kw=float(bat_cfg.get("max_charge_kw", 25.0)),
            max_discharge_kw=float(bat_cfg.get("max_discharge_kw", 25.0)),
            initial_soc=initial_bess_soc,
            min_soc=float(bat_cfg.get("min_soc", 0.20)),
            max_soc=float(bat_cfg.get("max_soc", 0.90)),
            reserve_soc=float(flex_cfg.get("battery", {}).get("reserve_soc", 0.10)),
            charge_efficiency=float(bat_cfg.get("charge_efficiency", 0.95)),
            discharge_efficiency=float(bat_cfg.get("discharge_efficiency", 0.95)),
            timestep_hours=0.25,
        )
        self.shift_tracker = ShiftEnergyTracker(timestep_hours=0.25)

        # Fairness & usage tracking: der_id -> dict
        self.der_stats: Dict[str, Dict[str, Any]] = {}
        for _, row in self.passports_df.iterrows():
            did = str(row["der_id"])
            self.der_stats[did] = {
                "der_id": did,
                "der_type": str(row["der_type"]),
                "activation_count": 0,
                "allocated_energy_kwh": 0.0,
                "allocated_power_kw": 0.0,
                "participation_count": 0,
            }

    def coordinate_horizon(
        self,
        requirements_df: pd.DataFrame,
        pv_forecast_df: pd.DataFrame,
        forecast_origin: pd.Timestamp,
    ) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """Execute multi-step coordination across the forecast horizon.

        Returns:
            (coordination_plan_df, flexibility_selection_df, unserved_flexibility_df, der_activation_summary_df)
        """
        coordination_rows = []
        selection_rows = []
        unserved_rows = []

        dt_h = 0.25

        for i, req_row in requirements_df.iterrows():
            t = pd.to_datetime(req_row["timestamp"])
            h_mins = int(req_row["horizon_minutes"])
            risk_state = str(req_row["risk_state"])
            c_type = str(req_row["constraint_type"])
            c_loc = str(req_row["constraint_location"])

            req_up = float(req_row["required_up_kw"])
            req_down = float(req_row["required_down_kw"])
            req_shift = float(req_row["required_shift_kw"])

            hour_float = t.hour + t.minute / 60.0

            # 1. Determine currently available flexibility by DER
            bess_up_avail = self.battery_tracker.get_available_up_kw()
            bess_down_avail = self.battery_tracker.get_available_down_kw()

            # PV forecast for this step
            pv_row = pv_forecast_df[pv_forecast_df["timestamp"] == t]
            fc_pv = float(pv_row["forecast"].iloc[0]) if not pv_row.empty else 0.0

            # Collect active DER candidate availability
            candidates = []

            # A. Community Battery
            candidates.append({
                "der_id": "BESS_COMMUNITY_01",
                "der_type": "BESS",
                "up_avail_kw": bess_up_avail,
                "down_avail_kw": bess_down_avail,
                "shift_avail_kw": 0.0,
                "response_time_minutes": 1,
                "participating": True,  # Community asset always participates
            })

            # B. Solar PV inverters (Down flex via curtailment)
            # Distribute forecast PV across participating PV systems
            pv_systems = self.passports_df[self.passports_df["der_type"] == "PV"]
            n_pvs = len(pv_systems)
            pv_per_der = (fc_pv / max(1, n_pvs)) if fc_pv > 0.0 else 0.0

            # Deterministic participation filter
            for _, p_row in pv_systems.iterrows():
                did = str(p_row["der_id"])
                # Evaluate participation rate against hash or passport setting
                opt_in = bool(p_row.get("flexibility_enabled", p_row.get("owner_participation", True)))
                # Scale by participation scenario
                is_active = opt_in and (hash(did) % 100 < self.participation_rate * 100)
                pv_avail = pv_per_der if (is_active and (6.0 <= hour_float <= 18.25)) else 0.0

                candidates.append({
                    "der_id": did,
                    "der_type": "PV",
                    "up_avail_kw": 0.0,
                    "down_avail_kw": pv_avail,
                    "shift_avail_kw": 0.0,
                    "response_time_minutes": 1,
                    "participating": is_active,
                })

            # C. EV Hub chargers (Shift flex via smart throttle)
            ev_systems = self.passports_df[self.passports_df["der_type"] == "EV"]
            is_ev_charging_window = (hour_float >= 18.0) or (hour_float <= 2.0)

            for _, e_row in ev_systems.iterrows():
                did = str(e_row["der_id"])
                opt_in = bool(e_row.get("flexibility_enabled", e_row.get("owner_participation", True)))
                is_active = opt_in and (hash(did) % 100 < self.participation_rate * 100)
                # Baseline 7.4 kW charging in active window
                ev_p = 7.4 if (is_active and is_ev_charging_window) else 0.0

                candidates.append({
                    "der_id": did,
                    "der_type": "EV",
                    "up_avail_kw": ev_p,  # Throttling charging reduces load, providing UP grid relief
                    "down_avail_kw": 0.0,
                    "shift_avail_kw": ev_p,
                    "response_time_minutes": 5,
                    "participating": is_active,
                })

            # D. Flexible Loads (Shift flex)
            fl_systems = self.passports_df[self.passports_df["der_type"] == "FLEXIBLE_LOAD"]
            for _, f_row in fl_systems.iterrows():
                did = str(f_row["der_id"])
                opt_in = bool(f_row.get("flexibility_enabled", f_row.get("owner_participation", True)))
                is_active = opt_in and (hash(did) % 100 < self.participation_rate * 100)
                # Check scheduled window
                s_h = 9.0 if did == "FL002" else (11.0 if did == "FL003" else 5.5)
                e_h = 17.5 if did == "FL002" else (14.5 if did == "FL003" else 8.0)
                r_kw = float(f_row.get("rated_power_kw", 3.5))
                fl_p = r_kw if (is_active and (s_h <= hour_float < e_h)) else 0.0

                candidates.append({
                    "der_id": did,
                    "der_type": "FLEXIBLE_LOAD",
                    "up_avail_kw": fl_p,  # Shedding/shifting demand provides UP grid relief
                    "down_avail_kw": 0.0,
                    "shift_avail_kw": fl_p,
                    "response_time_minutes": 15,
                    "participating": is_active,
                })

            # Calculate total available flexibility in each direction
            tot_avail_up = sum(c["up_avail_kw"] for c in candidates)
            tot_avail_down = sum(c["down_avail_kw"] for c in candidates)
            tot_avail_shift = sum(c["shift_avail_kw"] for c in candidates)

            # 2. Allocation Execution
            selected_up = 0.0
            selected_down = 0.0
            selected_shift = 0.0
            num_selected = 0

            # --- A. Allocate UP Flexibility if required ---
            rem_req_up = req_up
            if rem_req_up > 0.0:
                # Rank candidates for UP: fast response time first, then lower activation count (fairness rotation)
                up_candidates = [c for c in candidates if c["up_avail_kw"] > 0.0]
                up_candidates.sort(key=lambda c: (
                    c["response_time_minutes"],
                    self.der_stats[c["der_id"]]["activation_count"],
                    c["der_id"]
                ))

                for cand in up_candidates:
                    if rem_req_up <= 1e-4:
                        break

                    did = cand["der_id"]
                    alloc_kw = min(rem_req_up, cand["up_avail_kw"])
                    if alloc_kw > 0.0:
                        selected_up += alloc_kw
                        rem_req_up -= alloc_kw
                        num_selected += 1

                        energy_kwh = alloc_kw * dt_h
                        # Update trackers
                        if cand["der_type"] == "BESS":
                            self.battery_tracker.step(alloc_kw, direction="UP")
                            reason = "BESS active discharge to relieve substation load / voltage drop"
                        elif cand["der_type"] in ["EV", "FLEXIBLE_LOAD"]:
                            selected_shift += alloc_kw
                            # Register shift obligation
                            dep_t = t + pd.Timedelta(hours=4)
                            self.shift_tracker.register_shift(
                                der_id=did,
                                der_type=cand["der_type"],
                                timestamp=t,
                                shifted_kw=alloc_kw,
                                deadline_timestamp=dep_t,
                                reason=f"Load deferred from constrained interval {t.strftime('%H:%M')}"
                            )
                            reason = f"{cand['der_type']} smart charge throttle / demand deferral"

                        # Update fairness stats
                        st = self.der_stats[did]
                        st["activation_count"] += 1
                        st["allocated_power_kw"] += alloc_kw
                        st["allocated_energy_kwh"] += energy_kwh
                        st["participation_count"] += 1

                        selection_rows.append({
                            "timestamp": t,
                            "der_id": did,
                            "der_type": cand["der_type"],
                            "direction": "UP",
                            "requested_kw": round(req_up, 2),
                            "allocated_kw": round(alloc_kw, 2),
                            "duration_minutes": 15,
                            "energy_kwh": round(energy_kwh, 3),
                            "reason": reason,
                            "participation_status": "OPTED_IN",
                            "constraint_target": c_type,
                        })

            # --- B. Allocate DOWN Flexibility if required ---
            rem_req_down = req_down
            if rem_req_down > 0.0:
                down_candidates = [c for c in candidates if c["down_avail_kw"] > 0.0]
                down_candidates.sort(key=lambda c: (
                    c["response_time_minutes"],
                    self.der_stats[c["der_id"]]["activation_count"],
                    c["der_id"]
                ))

                for cand in down_candidates:
                    if rem_req_down <= 1e-4:
                        break

                    did = cand["der_id"]
                    alloc_kw = min(rem_req_down, cand["down_avail_kw"])
                    if alloc_kw > 0.0:
                        selected_down += alloc_kw
                        rem_req_down -= alloc_kw
                        num_selected += 1

                        energy_kwh = alloc_kw * dt_h
                        if cand["der_type"] == "BESS":
                            self.battery_tracker.step(alloc_kw, direction="DOWN")
                            reason = "BESS charging absorption of surplus generation"
                        elif cand["der_type"] == "PV":
                            reason = "Rooftop PV inverter export curtailment to prevent overvoltage"
                        else:
                            reason = "Demand advance / load increase"

                        st = self.der_stats[did]
                        st["activation_count"] += 1
                        st["allocated_power_kw"] += alloc_kw
                        st["allocated_energy_kwh"] += energy_kwh
                        st["participation_count"] += 1

                        selection_rows.append({
                            "timestamp": t,
                            "der_id": did,
                            "der_type": cand["der_type"],
                            "direction": "DOWN",
                            "requested_kw": round(req_down, 2),
                            "allocated_kw": round(alloc_kw, 2),
                            "duration_minutes": 15,
                            "energy_kwh": round(energy_kwh, 3),
                            "reason": reason,
                            "participation_status": "OPTED_IN",
                            "constraint_target": c_type,
                        })

            # Calculate unserved flexibility
            unserved_up = max(0.0, req_up - selected_up)
            unserved_down = max(0.0, req_down - selected_down)
            unserved_shift = max(0.0, req_shift - selected_shift)

            if unserved_up > 0.0 or unserved_down > 0.0:
                unserved_rows.append({
                    "timestamp": t,
                    "horizon_minutes": h_mins,
                    "risk_state": risk_state,
                    "constraint_type": c_type,
                    "unserved_up_kw": round(unserved_up, 2),
                    "unserved_down_kw": round(unserved_down, 2),
                    "unserved_shift_kw": round(unserved_shift, 2),
                    "cause": "Available flexibility exhausted or limited by participation rate",
                })

            coordination_rows.append({
                "timestamp": t,
                "horizon_minutes": h_mins,
                "forecast_origin": forecast_origin,
                "risk_state": risk_state,
                "constraint_type": c_type,
                "constraint_location": c_loc,
                "required_up_kw": round(req_up, 2),
                "required_down_kw": round(req_down, 2),
                "required_shift_kw": round(req_shift, 2),
                "available_up_kw": round(tot_avail_up, 2),
                "available_down_kw": round(tot_avail_down, 2),
                "available_shift_kw": round(tot_avail_shift, 2),
                "selected_up_kw": round(selected_up, 2),
                "selected_down_kw": round(selected_down, 2),
                "selected_shift_kw": round(selected_shift, 2),
                "unserved_up_kw": round(unserved_up, 2),
                "unserved_down_kw": round(unserved_down, 2),
                "unserved_shift_kw": round(unserved_shift, 2),
                "number_of_selected_ders": num_selected,
            })

        # Summary DataFrames
        plan_df = pd.DataFrame(coordination_rows)
        selection_df = pd.DataFrame(selection_rows)
        unserved_df = pd.DataFrame(unserved_rows) if unserved_rows else pd.DataFrame(columns=[
            "timestamp", "horizon_minutes", "risk_state", "constraint_type",
            "unserved_up_kw", "unserved_down_kw", "unserved_shift_kw", "cause"
        ])

        summary_rows = []
        for did, st in self.der_stats.items():
            summary_rows.append({
                "der_id": st["der_id"],
                "der_type": st["der_type"],
                "activation_count": st["activation_count"],
                "allocated_energy_kwh": round(st["allocated_energy_kwh"], 3),
                "allocated_power_kw": round(st["allocated_power_kw"], 2),
                "participation_count": st["participation_count"],
            })
        der_summary_df = pd.DataFrame(summary_rows)

        return plan_df, selection_df, unserved_df, der_summary_df
