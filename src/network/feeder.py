"""Radial Low-Voltage (LV) Distribution Feeder Model.

Constructs an electrically valid, connected radial LV distribution network in pandapower
interfaced with an 11 kV medium-voltage external grid via a 250 kVA distribution transformer.
"""

from typing import Any, Dict, List, Tuple
import pandapower as pp
import numpy as np


def build_feeder_topology(
    config: Dict[str, Any],
    household_ids: List[str],
    pv_metadata: Dict[str, Dict[str, Any]],
    comm_ids: List[str],
    crit_id: str,
    ev_ids: List[str],
    flex_ids: List[str]
) -> Tuple[pp.pandapowerNet, Dict[str, Any]]:
    """Build the complete pandapower LV distribution network.

    Radial Topology:
    [MV Slack Bus (11 kV)]
          |
    [Transformer 11/0.415 kV, 250 kVA]
          |
    [Bus_Main_LV (0.415 kV)]
          +--- Line 1 ---> [Bus_Residential_1] (Households H001-H035, PVs, Water Pump)
          |                      +--- Line 2 ---> [Bus_Residential_2] (Households H036-H070, PVs, Appliance Block)
          |                      |                      +--- Line 3 ---> [Bus_Residential_3] (Households H071-H100, PVs)
          |                      +--- Line EV ---> [Bus_EV_Hub] (20 EV wallbox chargers)
          +--- Line Comm ---> [Bus_Commercial] (COM01-COM05, Commercial HVAC)
          +--- Line Crit ---> [Bus_Critical] (Primary Health Centre CRIT_001)
          +--- Line BESS ---> [Bus_BESS] (Community Battery BESS_COMMUNITY_01)
    """
    net_cfg = config.get("network", {})
    trafo_cfg = net_cfg.get("transformer", {})
    lines_cfg = net_cfg.get("lines", {})
    seg_lens = lines_cfg.get("segment_lengths_km", {})

    net = pp.create_empty_network(name=net_cfg.get("feeder_name", "GridFlex_LV_Feeder_01"))

    # 1. Medium Voltage (11 kV) External Grid Bus
    vn_hv = float(trafo_cfg.get("vn_hv_kv", 11.0))
    vn_lv = float(trafo_cfg.get("vn_lv_kv", 0.415))

    b_mv = pp.create_bus(net, vn_kv=vn_hv, name="Bus_MV_Grid", zone="MV")
    pp.create_ext_grid(net, bus=b_mv, vm_pu=1.00, va_degree=0.0, name="External_MV_Grid")

    # 2. Main Low Voltage Bus (0.415 kV)
    b_main_lv = pp.create_bus(net, vn_kv=vn_lv, name="Bus_Main_LV", zone="LV_Substation")

    # 3. Distribution Transformer (11 / 0.415 kV, 250 kVA)
    pp.create_transformer_from_parameters(
        net,
        hv_bus=b_mv,
        lv_bus=b_main_lv,
        sn_mva=float(trafo_cfg.get("sn_mva", 0.250)),
        vn_hv_kv=vn_hv,
        vn_lv_kv=vn_lv,
        vkr_percent=float(trafo_cfg.get("vkr_percent", 1.1)),
        vk_percent=float(trafo_cfg.get("vk_percent", 4.0)),
        pfe_kw=float(trafo_cfg.get("pfe_kw", 0.60)),
        i0_percent=float(trafo_cfg.get("i0_percent", 0.25)),
        name=trafo_cfg.get("name", "DT_11_0.415_250kVA")
    )

    # 4. Downstream Feeder Buses
    b_res1 = pp.create_bus(net, vn_kv=vn_lv, name="Bus_Residential_1", zone="Residential")
    b_res2 = pp.create_bus(net, vn_kv=vn_lv, name="Bus_Residential_2", zone="Residential")
    b_res3 = pp.create_bus(net, vn_kv=vn_lv, name="Bus_Residential_3", zone="Residential")
    b_comm = pp.create_bus(net, vn_kv=vn_lv, name="Bus_Commercial", zone="Commercial")
    b_crit = pp.create_bus(net, vn_kv=vn_lv, name="Bus_Critical", zone="Critical")
    b_ev = pp.create_bus(net, vn_kv=vn_lv, name="Bus_EV_Hub", zone="Mobility")
    b_bess = pp.create_bus(net, vn_kv=vn_lv, name="Bus_BESS", zone="Storage")

    bus_map = {
        "Bus_MV_Grid": b_mv,
        "Bus_Main_LV": b_main_lv,
        "Bus_Residential_1": b_res1,
        "Bus_Residential_2": b_res2,
        "Bus_Residential_3": b_res3,
        "Bus_Commercial": b_comm,
        "Bus_Critical": b_crit,
        "Bus_EV_Hub": b_ev,
        "Bus_BESS": b_bess
    }

    # 5. Radial Line Segments (XLPE Al Cable)
    r_km = float(lines_cfg.get("r_ohm_per_km", 0.384))
    x_km = float(lines_cfg.get("x_ohm_per_km", 0.082))
    c_km = float(lines_cfg.get("c_nf_per_km", 260.0))
    max_i = float(lines_cfg.get("max_i_ka", 0.220))

    line_specs = [
        ("Line_Trunk_1", b_main_lv, b_res1, float(seg_lens.get("feeder_trunk_1", 0.12))),
        ("Line_Trunk_2", b_res1, b_res2, float(seg_lens.get("feeder_trunk_2", 0.15))),
        ("Line_Trunk_3", b_res2, b_res3, float(seg_lens.get("feeder_trunk_3", 0.15))),
        ("Line_Commercial", b_main_lv, b_comm, float(seg_lens.get("feeder_commercial", 0.10))),
        ("Line_Critical", b_main_lv, b_crit, float(seg_lens.get("feeder_critical", 0.08))),
        ("Line_EV_Hub", b_res1, b_ev, float(seg_lens.get("feeder_ev", 0.10))),
        ("Line_BESS", b_main_lv, b_bess, float(seg_lens.get("feeder_bess", 0.05)))
    ]

    for line_name, from_b, to_b, length_km in line_specs:
        pp.create_line_from_parameters(
            net,
            from_bus=from_b,
            to_bus=to_b,
            length_km=length_km,
            r_ohm_per_km=r_km,
            x_ohm_per_km=x_km,
            c_nf_per_km=c_km,
            max_i_ka=max_i,
            name=line_name
        )

    # 6. Assign Households & DERs to Buses
    # H001-H035 -> Bus_Residential_1, H036-H070 -> Bus_Residential_2, H071-H100 -> Bus_Residential_3
    household_bus_map = {}
    load_index_map = {}
    sgen_index_map = {}

    for idx, hid in enumerate(household_ids):
        if idx < 35:
            b_target = b_res1
            b_name = "Bus_Residential_1"
        elif idx < 70:
            b_target = b_res2
            b_name = "Bus_Residential_2"
        else:
            b_target = b_res3
            b_name = "Bus_Residential_3"

        household_bus_map[hid] = b_name
        # Create pandapower load element for household (p_mw, q_mvar initialized to 0)
        l_idx = pp.create_load(net, bus=b_target, p_mw=0.0, q_mvar=0.0, name=f"Load_{hid}")
        load_index_map[hid] = l_idx

    # Rooftop Solar PV sgen elements
    for der_id, meta in pv_metadata.items():
        hid = meta["household_id"]
        b_name = household_bus_map[hid]
        b_target = bus_map[b_name]
        s_idx = pp.create_sgen(
            net,
            bus=b_target,
            p_mw=0.0,
            q_mvar=0.0,
            sn_mva=meta["capacity_kw"] / 1000.0,
            name=f"Sgen_{der_id}"
        )
        sgen_index_map[der_id] = s_idx

    # Commercial loads at Bus_Commercial
    for cid in comm_ids:
        l_idx = pp.create_load(net, bus=b_comm, p_mw=0.0, q_mvar=0.0, name=f"Load_{cid}")
        load_index_map[cid] = l_idx

    # Critical facility load at Bus_Critical
    l_crit_idx = pp.create_load(net, bus=b_crit, p_mw=0.0, q_mvar=0.0, name=f"Load_{crit_id}")
    load_index_map[crit_id] = l_crit_idx

    # EV charging loads aggregated at Bus_EV_Hub
    for evid in ev_ids:
        l_idx = pp.create_load(net, bus=b_ev, p_mw=0.0, q_mvar=0.0, name=f"Load_{evid}")
        load_index_map[evid] = l_idx

    # Flexible loads
    flex_bus_assignment = {
        "FL001": b_res1,
        "FL002": b_comm,
        "FL003": b_res2
    }
    for flid in flex_ids:
        b_fl = flex_bus_assignment.get(flid, b_res1)
        l_idx = pp.create_load(net, bus=b_fl, p_mw=0.0, q_mvar=0.0, name=f"Load_{flid}")
        load_index_map[flid] = l_idx

    # Community Battery at Bus_BESS (represented as sgen: positive p_mw = injection/discharge)
    bess_cfg = config.get("battery", {})
    bess_der_id = bess_cfg.get("der_id", "BESS_COMMUNITY_01")
    s_bess_idx = pp.create_sgen(
        net,
        bus=b_bess,
        p_mw=0.0,
        q_mvar=0.0,
        sn_mva=float(bess_cfg.get("max_discharge_kw", 25.0)) / 1000.0,
        name=f"Sgen_{bess_der_id}"
    )
    sgen_index_map[bess_der_id] = s_bess_idx

    mappings = {
        "bus_map": bus_map,
        "household_bus_map": household_bus_map,
        "load_index_map": load_index_map,
        "sgen_index_map": sgen_index_map,
        "bess_der_id": bess_der_id
    }

    return net, mappings
