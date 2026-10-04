"""Unit tests for pandapower LV distribution feeder topology."""

from pathlib import Path
import networkx as nx
import pandapower as pp
import pandapower.topology as pptop
import pytest
import yaml

from src.profiles.load_profiles import (
    generate_time_index,
    generate_residential_profiles,
    generate_commercial_profiles,
    generate_critical_profile,
    generate_flexible_load_profiles
)
from src.profiles.solar_profiles import generate_solar_profiles
from src.profiles.ev_profiles import generate_ev_profiles
from src.network.feeder import build_feeder_topology

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def test_setup():
    config_file = PROJECT_ROOT / "config" / "neighbourhood_config.yaml"
    with open(config_file, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    time_index = generate_time_index(start_date="2026-01-15", duration_days=1, timestep_minutes=15)
    df_res, res_meta = generate_residential_profiles(config, time_index)
    df_comm, comm_meta = generate_commercial_profiles(config, time_index)
    df_crit, crit_meta = generate_critical_profile(config, time_index)
    df_flex, flex_meta = generate_flexible_load_profiles(config, time_index)
    hids = list(res_meta.keys())
    df_solar, pv_meta = generate_solar_profiles(config, time_index, hids)
    df_ev, ev_meta = generate_ev_profiles(config, time_index)

    net, mappings = build_feeder_topology(
        config=config,
        household_ids=hids,
        pv_metadata=pv_meta,
        comm_ids=list(comm_meta.keys()),
        crit_id=crit_meta["facility_id"],
        ev_ids=list(ev_meta.keys()),
        flex_ids=list(flex_meta.keys())
    )
    return net, mappings, config


def test_feeder_builds_and_buses_exist(test_setup):
    net, mappings, config = test_setup
    assert isinstance(net, pp.pandapowerNet)

    expected_buses = [
        "Bus_MV_Grid",
        "Bus_Main_LV",
        "Bus_Residential_1",
        "Bus_Residential_2",
        "Bus_Residential_3",
        "Bus_Commercial",
        "Bus_Critical",
        "Bus_EV_Hub",
        "Bus_BESS"
    ]
    actual_buses = list(net.bus.name.values)
    for b in expected_buses:
        assert b in actual_buses, f"Missing expected bus: {b}"
    assert len(net.bus) == len(expected_buses)


def test_transformer_exists(test_setup):
    net, mappings, config = test_setup
    assert len(net.trafo) == 1
    trafo = net.trafo.iloc[0]
    assert trafo.sn_mva == 0.250
    assert trafo.vn_hv_kv == 11.0
    assert trafo.vn_lv_kv == 0.415


def test_lines_exist(test_setup):
    net, mappings, config = test_setup
    assert len(net.line) == 7
    expected_lines = [
        "Line_Trunk_1",
        "Line_Trunk_2",
        "Line_Trunk_3",
        "Line_Commercial",
        "Line_Critical",
        "Line_EV_Hub",
        "Line_BESS"
    ]
    actual_lines = list(net.line.name.values)
    for l in expected_lines:
        assert l in actual_lines


def test_network_is_connected(test_setup):
    net, mappings, config = test_setup
    # Create multigraph from pandapower net and check connectedness
    mg = pptop.create_nxgraph(net, include_trafos=True)
    unconnected_subgraphs = list(nx.connected_components(mg))
    # All buses belong to a single connected electrical component
    assert len(unconnected_subgraphs) == 1
    assert len(unconnected_subgraphs[0]) == len(net.bus)
