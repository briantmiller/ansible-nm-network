"""Parser tests. Run: python3 -m pytest tests/ (no NetworkManager needed)."""
import os
import sys

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "..", "plugins", "filter"))

from nm_config import nm_parse  # noqa: E402


def conns(result):
    return dict((c["conn_name"], c) for c in result["connections"])


def test_example_is_clean():
    with open(os.path.join(HERE, "..", "..", "..", "..", "examples", "network.yaml")) as f:
        r = nm_parse(yaml.safe_load(f))
    assert r["errors"] == [] and r["warnings"] == []
    c = conns(r)
    assert c["br0"]["props"]["bridge.vlan-filtering"] == "yes"
    assert c["br0"]["props"]["bridge.vlans"] == "100"
    assert c["bond0"]["params"]["master"] == "br0"           # inferred from bridge ports
    assert c["bond0"]["params"]["slave_type"] == "bridge"
    assert "bond0-eno3" in c and "br0-bond0" not in c         # no generic slave for bond0
    assert c["br0-eno1"]["props"]["bridge-port.vlans"] == "100, 200"   # 300: off excluded
    assert c["br0-eno2"]["props"]["bridge-port.vlans"] == "100 pvid untagged"
    order = [x["conn_name"] for x in r["connections"]]
    assert order.index("br0") < order.index("bond0") < order.index("br0.100") < order.index("br0-eno1")


def test_typo_suggests_fix():
    r = nm_parse({"vlans": {"v": {"vlandev": "eno1", "vlandid": 5}}})
    assert any("did you mean 'vlanid'" in e for e in r["errors"])


def test_setting_on_wrong_type():
    r = nm_parse({"bridges": {"br0": {"miimon": 100}}})
    assert any("'miimon' does not apply to type 'bridge'" in e for e in r["errors"])


def test_port_in_two_masters():
    r = nm_parse({"bridges": {"br0": {"ports": {"eno1": None}}},
                  "bonds": {"bond0": {"miimon": 100, "ports": ["eno1"]}}})
    assert any("already a port of" in e for e in r["errors"])


def test_master_conflict():
    r = nm_parse({"bridges": {"br0": {"ports": {"bond0": None}}, "br1": {}},
                  "bonds": {"bond0": {"miimon": 100, "master": "br1"}}})
    assert any("master is 'br1'" in e for e in r["errors"])


def test_master_without_ports_entry_gets_slave_type():
    r = nm_parse({"bridges": {"br0": {}}, "bonds": {"bond0": {"miimon": 100, "master": "br0"}}})
    assert conns(r)["bond0"]["params"]["slave_type"] == "bridge"


def test_typed_port_settings_become_properties():
    r = nm_parse({"bridges": {"br0": {"ports": {"bond0": {"settings": {"hairpin": True, "path_cost": 5}}}}},
                  "bonds": {"bond0": {"miimon": 100}}})
    p = conns(r)["bond0"]["props"]
    assert p["bridge-port.hairpin-mode"] == "yes" and p["bridge-port.path-cost"] == "5"


def test_typed_port_other_settings_rejected():
    r = nm_parse({"bridges": {"br0": {"ports": {"eno1": {"settings": {"mtu": 9000}}}}},
                  "ethernet": {"eno1": {}}})
    assert any("must be set in the interface's own section" in e for e in r["errors"])


def test_enslaved_ip_warns():
    r = nm_parse({"bridges": {"br0": {"ports": {"eno1": None}}},
                  "ethernet": {"eno1": {"ip4": "10.0.0.1/24"}}})
    assert any("ignores IP settings" in w for w in r["warnings"])


def test_vlan_on_port_parent_warns():
    r = nm_parse({"bridges": {"br0": {"ports": {"eno1": None}}},
                  "vlans": {"eno1.10": {"vlandev": "eno1", "vlanid": 10}}})
    assert any("is a port of 'br0'" in w for w in r["warnings"])


def test_self_vlan_not_carried_warns():
    r = nm_parse({"bridges": {"br0": {"vlans": {10: True}, "ports": {"eno1": {"vlans": {20: True}}}}}})
    assert any("no port carries it" in w for w in r["warnings"])


def test_bad_vlan_values():
    r = nm_parse({"bridges": {"br0": {"ports": {"eno1": {"vlans": {
        5000: True, 10: "maybe", 20: "private", 30: "private"}}}}}})
    errs = " ".join(r["errors"])
    assert "invalid VLAN ID '5000'" in errs and "invalid value 'maybe'" in errs
    assert "only one VLAN can be 'private'" in errs


def test_vlan_range():
    r = nm_parse({"bridges": {"br0": {"ports": {"eno1": {"vlans": {"100-110": "on", 5: "private"}}}}}})
    assert conns(r)["br0-eno1"]["props"]["bridge-port.vlans"] == "5 pvid untagged, 100-110"


def test_filtering_false_with_vlans():
    r = nm_parse({"bridges": {"br0": {"vlan_filtering": False, "ports": {"eno1": {"vlans": {5: True}}}}}})
    assert any("vlan_filtering is false" in e for e in r["errors"])


def test_unknown_section():
    r = nm_parse({"bridge": {}})
    assert any("did you mean 'bridges'" in e for e in r["errors"])


def test_absent_master_removes_generated_ports():
    r = nm_parse({"bonds": {"bond0": {"state": "absent", "miimon": 100, "ports": ["eno3"]}}})
    assert conns(r)["bond0-eno3"]["state"] == "absent"


def test_routes_mutually_exclusive():
    r = nm_parse({"ethernet": {"eno6": {"routes4": ["3.3.3.0/24 4.3.2.3"],
                                        "routes4_extended": [{"ip": "10.0.0.0/16"}]}}})
    assert any("cannot be used together" in e for e in r["errors"])
