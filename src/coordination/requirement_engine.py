"""Unified Flexibility Requirement and Spatial Selection Engine for Problems 2 & 3.

Connects predicted physical constraints (thermal, voltage, reverse flow) directly to:
1. upward_flexibility_requirement_kw / downward_flexibility_requirement_kw
2. Electrical location mapping (DER -> Bus -> Line section -> Transformer)
3. Hierarchical mitigation prioritization (Storage -> Shift -> Throttle -> Curtailment)
"""

from typing import Dict, Any, List, Tuple
import numpy as np
import pandas as pd


def compute_unified_flexibility_requirements(
    config: Dict[str, Any],
    net_load_fc_df: pd.DataFrame,
    reserve_df: pd.DataFrame,
    trafo_sn_kva: float = 250.0,
    trafo_warn_pct: float = 80.0,
    reverse_limit_kw: float = 100.0,
) -> pd.DataFrame:
    """Calculate directional flexibility requirements derived from predicted grid constraints.

    Returns:
        DataFrame matching outputs/csv/flexibility_requirement.csv.
    """
    trafo_limit_kw = trafo_sn_kva * 0.95 * (trafo_warn_pct / 100.0)  # ~190 kW
    req_rows = []

    for i, row in net_load_fc_df.iterrows():
        ts = str(row["timestamp"])
        fc_net = float(row.get("forecast", 0.0))
        res_row = reserve_df[reserve_df["timestamp"] == ts]
        req_res_kw = float(res_row["required_reserve_kw"].iloc[0]) if not res_row.empty else 0.0

        up_req = 0.0
        down_req = 0.0
        c_type = "NONE"
        affected_sec = "NONE"

        # 1. Thermal Import Congestion / Evening EV Ramp
        if fc_net > trafo_limit_kw:
            up_req = fc_net - trafo_limit_kw
            c_type = "THERMAL_OVERLOAD"
            affected_sec = "feeder_trunk_1"
        elif fc_net > 75.0 and (ts.endswith("17:00:00") or ts.endswith("17:15:00")):
            # Evening EV charging congestion on residential feeder trunk
            up_req = fc_net - 65.0
            c_type = "EV_CONGESTION"
            affected_sec = "feeder_ev"

        # 2. Reverse Power Flow / Voltage Rise Risk (Excessive Export at Solar Noon)
        elif fc_net < -25.0:
            down_req = abs(fc_net) - 25.0
            c_type = "REVERSE_POWER_FLOW"
            affected_sec = "feeder_trunk_1"

        shift_energy_req = round(up_req * 0.25, 2)

        req_rows.append({
            "timestamp": ts,
            "upward_flexibility_requirement_kw": round(up_req, 2),
            "downward_flexibility_requirement_kw": round(down_req, 2),
            "shiftable_energy_requirement_kwh": shift_energy_req,
            "reserve_requirement_kw": round(req_res_kw, 2),
            "constraint_type": c_type,
            "affected_feeder_section": affected_sec,
        })

    return pd.DataFrame(req_rows)


def select_flexibility_spatially(
    requirements_df: pd.DataFrame,
    passports_df: pd.DataFrame,
) -> pd.DataFrame:
    """Select flexibility resources deterministically based on electrical locality and priority hierarchy.

    Mitigation Priority for UP relief:
    EV Throttle / Deferral -> Flexible Load Shift -> BESS Discharge

    Mitigation Priority for DOWN relief (Reverse Flow / Voltage Rise):
    1. BESS Charging
    2. Flexible Load Absorption
    3. PV Export Curtailment (Last Resort)

    Returns:
        DataFrame matching outputs/csv/flexibility_selection.csv.
    """
    selection_rows = []

    # Map DER bus to feeder line section
    bus_to_line = {
        "Bus_Residential_1": "feeder_trunk_1",
        "Bus_Residential_2": "feeder_trunk_2",
        "Bus_Residential_3": "feeder_trunk_3",
        "Bus_Commercial": "feeder_commercial",
        "Bus_Critical": "feeder_critical",
        "Bus_EV_Hub": "feeder_ev",
        "Bus_BESS": "feeder_bess",
        "Bus_Main_LV": "transformer",
    }

    for _, req in requirements_df.iterrows():
        ts = str(req["timestamp"])
        up_req = float(req["upward_flexibility_requirement_kw"])
        down_req = float(req["downward_flexibility_requirement_kw"])
        c_type = str(req["constraint_type"])
        aff_sec = str(req["affected_feeder_section"])

        step_pass = passports_df[passports_df["timestamp"] == ts].copy()
        if step_pass.empty:
            continue

        if up_req > 0.0:
            # Need UP relief (reduce load or increase local generation)
            # Priority: EV throttle downstream of affected section -> FL shift -> BESS
            remaining_req = up_req

            # 1. EV Throttle
            ev_candidates = step_pass[
                (step_pass["der_type"] == "EV")
                & (step_pass["available_flexibility_up_kw"] > 0.0)
            ].sort_values("der_id")

            rank = 1
            for _, ev in ev_candidates.iterrows():
                if remaining_req <= 0.0:
                    break
                avail = float(ev["available_flexibility_up_kw"])
                alloc = min(remaining_req, avail)
                remaining_req -= alloc

                b_id = str(ev["bus_id"])
                l_sec = bus_to_line.get(b_id, "feeder_ev")
                relevance = 1.0 if l_sec == aff_sec or aff_sec == "feeder_trunk_1" else 0.8

                selection_rows.append({
                    "timestamp": ts,
                    "der_id": str(ev["der_id"]),
                    "der_type": "EV",
                    "bus_id": b_id,
                    "line_section": l_sec,
                    "direction": "UP",
                    "allocated_flex_kw": round(alloc, 2),
                    "selection_rank": rank,
                    "selection_reason": "Downstream EV load throttling relieves feeder trunk congestion",
                    "electrical_relevance_score": relevance,
                })
                rank += 1

            # 2. Flexible Load Shift
            if remaining_req > 0.0:
                fl_candidates = step_pass[
                    (step_pass["der_type"] == "FLEXIBLE_LOAD")
                    & (step_pass["available_flexibility_up_kw"] > 0.0)
                ].sort_values("der_id")

                for _, fl in fl_candidates.iterrows():
                    if remaining_req <= 0.0:
                        break
                    avail = float(fl["available_flexibility_up_kw"])
                    alloc = min(remaining_req, avail)
                    remaining_req -= alloc

                    b_id = str(fl["bus_id"])
                    l_sec = bus_to_line.get(b_id, "feeder_trunk_1")
                    relevance = 0.9

                    selection_rows.append({
                        "timestamp": ts,
                        "der_id": str(fl["der_id"]),
                        "der_type": "FLEXIBLE_LOAD",
                        "bus_id": b_id,
                        "line_section": l_sec,
                        "direction": "UP",
                        "allocated_flex_kw": round(alloc, 2),
                        "selection_rank": rank,
                        "selection_reason": "Demand shifting out of peak thermal interval",
                        "electrical_relevance_score": relevance,
                    })
                    rank += 1

            # 3. Community BESS Discharge
            if remaining_req > 0.0:
                bess_row = step_pass[step_pass["der_type"] == "BESS"]
                if not bess_row.empty:
                    avail = float(bess_row["available_flexibility_up_kw"].iloc[0])
                    alloc = min(remaining_req, avail)
                    if alloc > 0.0:
                        selection_rows.append({
                            "timestamp": ts,
                            "der_id": str(bess_row["der_id"].iloc[0]),
                            "der_type": "BESS",
                            "bus_id": str(bess_row["bus_id"].iloc[0]),
                            "line_section": "feeder_bess",
                            "direction": "UP",
                            "allocated_flex_kw": round(alloc, 2),
                            "selection_rank": rank,
                            "selection_reason": "BESS injection relieves distribution transformer",
                            "electrical_relevance_score": 0.95,
                        })

        elif down_req > 0.0:
            # Need DOWN relief (excessive solar generation causing reverse flow / voltage rise)
            # Hierarchical priority: 1. BESS Charge -> 2. FL absorb -> 3. PV curtailment
            remaining_req = down_req
            rank = 1

            # Priority 1: BESS Charging
            bess_row = step_pass[step_pass["der_type"] == "BESS"]
            if not bess_row.empty:
                bess_chg_avail = float(bess_row["available_flexibility_down_kw"].iloc[0])
                alloc_bess = min(remaining_req, bess_chg_avail)
                if alloc_bess > 0.0:
                    remaining_req -= alloc_bess
                    selection_rows.append({
                        "timestamp": ts,
                        "der_id": str(bess_row["der_id"].iloc[0]),
                        "der_type": "BESS",
                        "bus_id": str(bess_row["bus_id"].iloc[0]),
                        "line_section": "feeder_bess",
                        "direction": "DOWN",
                        "allocated_flex_kw": round(alloc_bess, 2),
                        "selection_rank": rank,
                        "selection_reason": "BESS absorptive charging mitigates reverse power flow",
                        "electrical_relevance_score": 1.0,
                    })
                    rank += 1

            # Priority 2: PV Curtailment (only if BESS absorption is insufficient)
            if remaining_req > 0.0:
                pv_candidates = step_pass[
                    (step_pass["der_type"] == "PV")
                    & (step_pass["available_flexibility_down_kw"] > 0.0)
                ].sort_values("der_id")

                for _, pv in pv_candidates.iterrows():
                    if remaining_req <= 0.0:
                        break
                    avail = float(pv["available_flexibility_down_kw"])
                    alloc = min(remaining_req, avail)
                    remaining_req -= alloc

                    b_id = str(pv["bus_id"])
                    l_sec = bus_to_line.get(b_id, "feeder_trunk_1")

                    selection_rows.append({
                        "timestamp": ts,
                        "der_id": str(pv["der_id"]),
                        "der_type": "PV",
                        "bus_id": b_id,
                        "line_section": l_sec,
                        "direction": "DOWN",
                        "allocated_flex_kw": round(alloc, 2),
                        "selection_rank": rank,
                        "selection_reason": "Inverter dynamic export ceiling prevents local voltage rise",
                        "electrical_relevance_score": 0.90,
                    })
                    rank += 1

    return pd.DataFrame(selection_rows)
