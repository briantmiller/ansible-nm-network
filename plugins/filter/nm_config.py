# -*- coding: utf-8 -*-
# Copyright (c) 2026 brun064
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later
"""Parse and validate a NetworkManager network config for site.yml.

Filter: ``nm_parse``. Input is the config dict (see the config-format doc).
Output is a dict:

  connections: ordered list of {conn_name, ifname, type, state, params, props, order}
               params -> passed to community.general.nmcli
               props  -> raw NM properties set by library/nm_conn_props.py
  errors:      list of strings; the playbook fails if any exist
  warnings:    list of strings; shown, and fatal if nm_fail_on_warnings
"""

from __future__ import absolute_import, division, print_function

import difflib
import re

__metaclass__ = type

# --------------------------------------------------------------------------
# community.general.nmcli parameters (community.general main, Oct 2026)
# --------------------------------------------------------------------------

COMMON_PARAMS = {
    "autoconnect", "autoconnect_priority", "autoconnect_retries", "conn_reload",
    "master", "slave_type", "mtu", "mac", "zone", "dhcp_client_id", "sriov",
    "ip4", "gw4", "gw4_ignore_auto", "routes4", "routes4_extended",
    "route_metric4", "route_table4", "routing_rules4", "never_default4",
    "dns4", "dns4_search", "dns4_options", "dns4_ignore_auto", "method4",
    "may_fail4",
    "ip6", "gw6", "gw6_ignore_auto", "routes6", "routes6_extended",
    "route_metric6", "route_table6", "routing_rules6", "dns6", "dns6_search",
    "dns6_options", "dns6_ignore_auto", "method6", "ip_privacy6",
    "addr_gen_mode6", "ignore_unsupported_suboptions",
}

BRIDGE_PARAMS = {"stp", "priority", "forwarddelay", "hellotime", "maxage",
                 "ageingtime"}
BRIDGE_PORT_PARAMS = {"slavepriority", "path_cost", "hairpin"}
BOND_PARAMS = {"mode", "bond_mode_behavior", "miimon", "downdelay", "updelay",
               "arp_interval", "arp_ip_target", "primary", "xmit_hash_policy",
               "fail_over_mac"}
TEAM_PARAMS = {"runner", "runner_hwaddr_policy", "runner_fast_rate"}
VLAN_PARAMS = {"vlanid", "vlandev", "flags", "ingress", "egress"}
VXLAN_PARAMS = {"vxlan_id", "vxlan_remote", "vxlan_local", "vxlan_parent"}
TUNNEL_PARAMS = {"ip_tunnel_dev", "ip_tunnel_remote", "ip_tunnel_local",
                 "ip_tunnel_input_key", "ip_tunnel_output_key"}
INFINIBAND_PARAMS = {"transport_mode", "infiniband_mac"}
WIFI_PARAMS = {"ssid", "wifi", "wifi_sec"}

TYPE_PARAMS = {
    "bridge": BRIDGE_PARAMS,
    "bond": BOND_PARAMS,
    "team": TEAM_PARAMS,
    "vlan": VLAN_PARAMS,
    "vxlan": VXLAN_PARAMS,
    "gre": TUNNEL_PARAMS,
    "ipip": TUNNEL_PARAMS,
    "sit": TUNNEL_PARAMS,
    "infiniband": INFINIBAND_PARAMS,
    "wifi": WIFI_PARAMS,
    "gsm": {"gsm"},
    "macvlan": {"macvlan"},
    "wireguard": {"wireguard"},
    "vpn": {"vpn"},
    "vrf": {"table"},
    "ethernet": set(),
    "dummy": set(),
    "generic": set(),
    "loopback": set(),
    "ovs-bridge": set(),
    "ovs-port": set(),
    "ovs-interface": set(),
}

ALL_MODULE_PARAMS = set(COMMON_PARAMS) | BRIDGE_PORT_PARAMS
for _p in TYPE_PARAMS.values():
    ALL_MODULE_PARAMS |= _p

# Module rules: these pairs cannot be combined.
MUTUALLY_EXCLUSIVE = [("never_default4", "gw4"), ("routes4_extended", "routes4"),
                      ("routes6_extended", "routes6")]

# Keys the playbook understands in addition to module parameters.
ENTRY_EXTRAS = {"state", "conn_name", "ifname", "nm_properties"}
BRIDGE_EXTRAS = {"ports", "vlans", "vlan_filtering", "vlan_default_pvid"}
MASTER_EXTRAS = {"ports"}
PORT_KEYS = {"settings", "vlans", "nm_properties", "conn_name"}

# Config section -> connection type.
SECTIONS = {
    "bridges": "bridge", "bonds": "bond", "teams": "team", "vlans": "vlan",
    "ethernet": "ethernet", "vxlans": "vxlan", "macvlans": "macvlan",
    "vrfs": "vrf", "dummies": "dummy", "gre": "gre", "ipip": "ipip",
    "sit": "sit", "infiniband": "infiniband", "wireguard": "wireguard",
    "wifi": "wifi", "gsm": "gsm", "vpn": "vpn", "loopback": "loopback",
    "generic": "generic", "ovs_bridges": "ovs-bridge", "ovs_ports": "ovs-port",
    "ovs_interfaces": "ovs-interface",
}

# Masters whose ports get generated <type>-slave profiles.
SLAVE_TYPE_FOR_MASTER = {"bridge": "bridge-slave", "bond": "bond-slave",
                         "team": "team-slave"}
# slave_type value implied by a master of this type.
SLAVE_KIND = {"bridge": "bridge", "bond": "bond", "team": "team",
              "vrf": "vrf", "ovs-port": "ovs-port"}

# Creation order: masters before ports, parents before VLANs on them.
ORDER = {"vrf": 5, "ovs-bridge": 6, "ovs-port": 7, "bridge": 10, "team": 15,
         "bond": 20, "vlan": 40, "vxlan": 45, "macvlan": 45, "ovs-interface": 8,
         "bridge-slave": 60, "bond-slave": 55, "team-slave": 55}
DEFAULT_ORDER = 30

VLAN_ON = {"on", "yes", "true", "tagged"}
VLAN_OFF = {"off", "no", "false"}
VLAN_PRIVATE = {"private"}


def _suggest(key, choices):
    match = difflib.get_close_matches(str(key), sorted(choices), n=1, cutoff=0.75)
    return " (did you mean '%s'?)" % match[0] if match else ""


def _parse_vid(key):
    """Return (lo, hi) for 100 or '100-110', or None."""
    s = str(key).strip()
    m = re.match(r"^(\d+)(?:-(\d+))?$", s)
    if not m:
        return None
    lo = int(m.group(1))
    hi = int(m.group(2)) if m.group(2) else lo
    if not (1 <= lo <= hi <= 4094):
        return None
    return lo, hi


def _vlan_mode(value):
    """Map a vlans-dict value to 'tagged', 'off', 'private' or None (invalid)."""
    if value is True:
        return "tagged"
    if value is False:
        return "off"
    s = str(value).strip().lower()
    if s in VLAN_ON:
        return "tagged"
    if s in VLAN_OFF:
        return "off"
    if s in VLAN_PRIVATE:
        return "private"
    return None


def _nm_bool(value):
    return "yes" if value else "no"


class _Parser(object):

    def __init__(self, config):
        self.config = config or {}
        self.errors = []
        self.warnings = []
        self.entries = {}       # ifname -> dict(type, section, data)
        self.port_of = {}       # port ifname -> (master ifname, master type, port spec)
        self.connections = []

    # -- helpers -----------------------------------------------------------

    def err(self, msg):
        self.errors.append(msg)

    def warn(self, msg):
        self.warnings.append(msg)

    def _parse_vlans(self, where, vlans):
        """Validate a vlans dict -> list of (lo, hi, mode). Errors recorded."""
        out = []
        if vlans is None:
            return out
        if not isinstance(vlans, dict):
            self.err("%s: 'vlans' must be a mapping of VLAN ID -> on/off/private" % where)
            return out
        for key, value in vlans.items():
            rng = _parse_vid(key)
            if rng is None:
                self.err("%s: invalid VLAN ID '%s' (use 1-4094 or a range like 100-110)" % (where, key))
                continue
            mode = _vlan_mode(value)
            if mode is None:
                self.err("%s: VLAN %s has invalid value '%s' (use on, off or private)" % (where, key, value))
                continue
            out.append((rng[0], rng[1], mode))
        pvids = [v for v in out if v[2] == "private"]
        if len(pvids) > 1:
            self.err("%s: only one VLAN can be 'private' (native/untagged), found %s"
                     % (where, ", ".join(str(v[0]) for v in pvids)))
        for v in pvids:
            if v[0] != v[1]:
                self.err("%s: 'private' must be a single VLAN ID, not a range" % where)
        return out

    @staticmethod
    def _vlans_to_nm(parsed):
        items = []
        for lo, hi, mode in sorted(parsed):
            if mode == "off":
                continue
            vid = str(lo) if lo == hi else "%d-%d" % (lo, hi)
            items.append(vid + (" pvid untagged" if mode == "private" else ""))
        return ", ".join(items)

    @staticmethod
    def _member_vids(parsed):
        vids = set()
        for lo, hi, mode in parsed:
            if mode != "off":
                vids.update(range(lo, hi + 1))
        return vids

    def _check_keys(self, where, ctype, data, extras):
        allowed = COMMON_PARAMS | TYPE_PARAMS.get(ctype, set()) | ENTRY_EXTRAS | extras
        for key in data:
            if key in allowed:
                continue
            if key in ALL_MODULE_PARAMS:
                if key in BRIDGE_PORT_PARAMS:
                    self.err("%s: '%s' is a bridge-port setting; put it under the bridge's "
                             "ports.<name>.settings" % (where, key))
                else:
                    self.err("%s: '%s' does not apply to type '%s'" % (where, key, ctype))
            else:
                self.err("%s: unknown setting '%s'%s" % (where, key, _suggest(key, allowed)))

    # -- pass 1: collect entries --------------------------------------------

    def collect(self):
        if not isinstance(self.config, dict):
            self.err("config must be a mapping of sections (bridges, bonds, vlans, ...)")
            return
        for section, items in self.config.items():
            if section not in SECTIONS:
                self.err("unknown section '%s'%s" % (section, _suggest(section, SECTIONS)))
                continue
            if items is None:
                continue
            if not isinstance(items, dict):
                self.err("section '%s' must be a mapping of interface name -> settings" % section)
                continue
            ctype = SECTIONS[section]
            for name, data in items.items():
                name = str(name)
                data = data or {}
                where = "%s.%s" % (section, name)
                if not isinstance(data, dict):
                    self.err("%s: settings must be a mapping" % where)
                    continue
                if name in self.entries:
                    self.err("%s: '%s' is already defined in section '%s'"
                             % (where, name, self.entries[name]["section"]))
                    continue
                extras = BRIDGE_EXTRAS if ctype == "bridge" else (
                    MASTER_EXTRAS if ctype in ("bond", "team") else set())
                self._check_keys(where, ctype, data, extras)
                self.entries[name] = {"type": ctype, "section": section, "data": data,
                                      "where": where}

    # -- pass 2: ports -------------------------------------------------------

    def collect_ports(self):
        for name, ent in self.entries.items():
            if ent["type"] not in SLAVE_TYPE_FOR_MASTER:
                continue
            ports = ent["data"].get("ports")
            if ports is None:
                continue
            where = "%s.ports" % ent["where"]
            if isinstance(ports, list):
                ports = dict((str(p), None) for p in ports)
            if not isinstance(ports, dict):
                self.err("%s: must be a list of names or a mapping" % where)
                continue
            for pname, spec in ports.items():
                pname = str(pname)
                spec = spec or {}
                pwhere = "%s.%s" % (where, pname)
                if not isinstance(spec, dict):
                    self.err("%s: port settings must be a mapping" % pwhere)
                    continue
                for k in spec:
                    if k not in PORT_KEYS:
                        self.err("%s: unknown port key '%s'%s (port options go under 'settings')"
                                 % (pwhere, k, _suggest(k, PORT_KEYS)))
                if ent["type"] != "bridge" and spec.get("vlans"):
                    self.err("%s: port VLANs are only supported on bridge ports" % pwhere)
                if pname == name:
                    self.err("%s: an interface cannot be a port of itself" % pwhere)
                    continue
                if pname in self.port_of:
                    self.err("%s: '%s' is already a port of '%s'"
                             % (pwhere, pname, self.port_of[pname][0]))
                    continue
                self.port_of[pname] = (name, ent["type"], spec, pwhere)

    # -- pass 3: build connections -------------------------------------------

    def _bridge_filtering(self, name, ent):
        """Return (enabled, self_vlans_parsed, any_port_vlans)."""
        data = ent["data"]
        self_vlans = self._parse_vlans("%s.vlans" % ent["where"], data.get("vlans"))
        port_vlans = any(spec.get("vlans") for (m, _t, spec, _w) in self.port_of.values()
                         if m == name)
        explicit = data.get("vlan_filtering")
        if explicit is False and (self_vlans or port_vlans):
            self.err("%s: vlan_filtering is false but the bridge or its ports define vlans"
                     % ent["where"])
        enabled = bool(explicit) or (explicit is None and (bool(self_vlans) or port_vlans))
        return enabled, self_vlans

    def build(self):
        for name, ent in self.entries.items():
            data = dict(ent["data"])
            ctype = ent["type"]
            where = ent["where"]
            conn = {
                "conn_name": str(data.pop("conn_name", name)),
                "ifname": str(data.pop("ifname", name)),
                "type": ctype,
                "state": data.pop("state", "present"),
                "order": ORDER.get(ctype, DEFAULT_ORDER),
                "props": {},
            }
            if conn["state"] not in ("present", "absent"):
                self.err("%s: state must be present or absent" % where)
            extra_props = data.pop("nm_properties", None) or {}
            ports = data.pop("ports", None)  # noqa: F841 (handled in collect_ports)

            if ctype == "bridge":
                vlan_filtering_key = "vlan_filtering" in data
                data.pop("vlan_filtering", None)
                pvid = data.pop("vlan_default_pvid", None)
                data.pop("vlans", None)
                enabled, self_vlans = self._bridge_filtering(name, ent)
                if enabled or vlan_filtering_key:
                    conn["props"]["bridge.vlan-filtering"] = _nm_bool(enabled)
                if pvid is not None:
                    conn["props"]["bridge.vlan-default-pvid"] = str(pvid)
                if self_vlans:
                    conn["props"]["bridge.vlans"] = self._vlans_to_nm(self_vlans)
                ent["vlan_filtering"] = enabled
                ent["self_vids"] = self._member_vids(self_vlans)
                self._check_stp(where, data)

            for a, b in MUTUALLY_EXCLUSIVE:
                if a in data and b in data:
                    self.err("%s: '%s' and '%s' cannot be used together (the nmcli module rejects "
                             "it); move the %s entries into %s" % (where, a, b, b, a))
            if ctype == "wifi" and "ssid" not in data:
                self.err("%s: 'ssid' is required for wifi" % where)

            if ctype == "vlan":
                for req in ("vlanid", "vlandev"):
                    if req not in data:
                        self.err("%s: '%s' is required for a VLAN" % (where, req))
                vid = data.get("vlanid")
                if vid is not None and _parse_vid(vid) is None:
                    self.err("%s: vlanid %s is out of range 1-4094" % (where, vid))

            if ctype == "bond" and "miimon" not in data and "arp_interval" not in data:
                self.warn("%s: no miimon or arp_interval set; the module default (miimon 100) "
                          "applies" % where)

            # Is this interface a port of a bridge/bond/team in the config?
            if name in self.port_of:
                mname, mtype, spec, pwhere = self.port_of[name]
                declared = data.get("master")
                if declared is not None and str(declared) != mname:
                    self.err("%s: master is '%s' but it is listed as a port of '%s' (%s)"
                             % (where, declared, mname, pwhere))
                data["master"] = mname
                kind = SLAVE_KIND[mtype]
                if data.get("slave_type") not in (None, kind):
                    self.err("%s: slave_type '%s' conflicts with master '%s' (a %s)"
                             % (where, data["slave_type"], mname, mtype))
                data["slave_type"] = kind
                self._apply_port_spec(conn, spec, pwhere, mtype, typed=True, pname=name)
            elif data.get("master") is not None:
                self._infer_slave_type(where, data)

            if data.get("master") is not None:
                self._check_enslaved_ip(where, data)

            conn["props"].update(self._stringify(extra_props))
            conn["params"] = data
            self.connections.append(conn)

        # Generated slave profiles for ports not defined elsewhere.
        for pname, (mname, mtype, spec, pwhere) in self.port_of.items():
            if pname in self.entries:
                continue
            master = self.entries[mname]
            # Same as the module's <type>-slave types, without their deprecation-style
            # warning on every run; bridge-port settings are applied as properties.
            conn = {
                "conn_name": str(spec.get("conn_name", "%s-%s" % (mname, pname))),
                "ifname": pname,
                "type": "ethernet",
                "state": master["data"].get("state", "present"),
                "order": ORDER[SLAVE_TYPE_FOR_MASTER[mtype]],
                "props": {},
                "params": {"master": mname, "slave_type": SLAVE_KIND[mtype]},
            }
            self._apply_port_spec(conn, spec, pwhere, mtype, typed=False, pname=pname)
            if conn["params"].get("master") is not None:
                self._check_enslaved_ip(pwhere, conn["params"])
            self.connections.append(conn)

    def _infer_slave_type(self, where, data):
        mname = str(data["master"])
        if mname in self.entries:
            mtype = self.entries[mname]["type"]
            kind = SLAVE_KIND.get(mtype)
            if kind is None:
                self.err("%s: master '%s' is a %s, which cannot have ports" % (where, mname, mtype))
            elif data.get("slave_type") not in (None, kind):
                self.err("%s: slave_type '%s' conflicts with master '%s' (a %s)"
                         % (where, data["slave_type"], mname, mtype))
            else:
                data["slave_type"] = kind
        elif data.get("slave_type") is None:
            self.err("%s: master '%s' is not defined in this config, so slave_type must be set"
                     % (where, mname))

    def _apply_port_spec(self, conn, spec, pwhere, mtype, typed, pname):
        settings = dict(spec.get("settings") or {})
        if not isinstance(settings, dict):
            self.err("%s.settings: must be a mapping" % pwhere)
            settings = {}
        port_settings = dict((k, settings.pop(k)) for k in list(settings)
                             if k in BRIDGE_PORT_PARAMS)
        if port_settings and mtype != "bridge":
            self.err("%s.settings: %s only apply to bridge ports"
                     % (pwhere, ", ".join(sorted(port_settings))))
            port_settings = {}
        prop_map = {"hairpin": ("bridge-port.hairpin-mode", _nm_bool),
                    "path_cost": ("bridge-port.path-cost", str),
                    "slavepriority": ("bridge-port.priority", str)}
        for k, v in port_settings.items():
            prop, conv = prop_map[k]
            conn["props"][prop] = conv(v)
        if typed:
            # The interface has its own section; other settings belong there.
            if settings:
                self.err("%s.settings: %s must be set in the interface's own section"
                         % (pwhere, ", ".join(sorted(settings))))
        else:
            allowed = set(COMMON_PARAMS)
            for k in settings:
                if k not in allowed:
                    self.err("%s.settings: '%s' is not valid for a port%s"
                             % (pwhere, k, _suggest(k, allowed | BRIDGE_PORT_PARAMS)))
            if "master" in settings or "slave_type" in settings:
                self.err("%s.settings: master/slave_type are set from the bridge or bond" % pwhere)
            conn["params"].update(settings)
        vlans = self._parse_vlans("%s.vlans" % pwhere, spec.get("vlans"))
        if vlans or (mtype == "bridge" and spec.get("vlans") is not None):
            conn["props"]["bridge-port.vlans"] = self._vlans_to_nm(vlans)
        conn["port_vids"] = self._member_vids(vlans)
        conn["port_of"] = self.port_of[pname][0]
        conn["props"].update(self._stringify(spec.get("nm_properties") or {}))

    def _check_enslaved_ip(self, where, data):
        ipkeys = [k for k in ("ip4", "ip6", "gw4", "gw6", "dns4", "dns6", "routes4",
                              "routes6", "routes4_extended", "routes6_extended")
                  if data.get(k)]
        if ipkeys and data.get("slave_type") != "vrf":
            self.warn("%s: has %s but is enslaved to '%s'; NetworkManager ignores IP settings on "
                      "ports. Put the addresses on the master instead."
                      % (where, ", ".join(ipkeys), data["master"]))

    def _check_stp(self, where, data):
        if data.get("stp") is False:
            return
        fd = data.get("forwarddelay", 15)
        ht = data.get("hellotime", 2)
        ma = data.get("maxage", 20)
        try:
            fd, ht, ma = int(fd), int(ht), int(ma)
        except (TypeError, ValueError):
            return
        if not (2 * (fd - 1) >= ma >= 2 * (ht + 1)):
            self.warn("%s: STP timers break the 802.1D rule 2*(forwarddelay-1) >= maxage >= "
                      "2*(hellotime+1) (forwarddelay=%d, maxage=%d, hellotime=%d)"
                      % (where, fd, ma, ht))

    @staticmethod
    def _stringify(props):
        out = {}
        for k, v in props.items():
            if isinstance(v, bool):
                v = _nm_bool(v)
            elif isinstance(v, (list, tuple)):
                v = ",".join(str(i) for i in v)
            out[str(k)] = str(v)
        return out

    # -- pass 4: cross checks -------------------------------------------------

    def cross_check(self):
        for name, ent in self.entries.items():
            if ent["type"] != "vlan":
                continue
            data = ent["data"]
            parent = str(data.get("vlandev", ""))
            vid = data.get("vlanid")
            pent = self.entries.get(parent)
            if pent and pent["type"] == "bridge" and pent.get("vlan_filtering"):
                try:
                    vid = int(vid)
                except (TypeError, ValueError):
                    continue
                if vid not in pent["self_vids"]:
                    self.warn("%s: VLAN %d is on bridge '%s', which filters VLANs, but VLAN %d is "
                              "not in %s.vlans; the bridge will drop its traffic. Add "
                              "'%d: on' under bridges.%s.vlans."
                              % (ent["where"], vid, parent, vid, pent["where"], vid, parent))
            if parent in self.port_of:
                self.warn("%s: parent '%s' is a port of '%s'; tagged frames are taken by the "
                          "%s before this VLAN sees them. Use a VLAN on '%s' instead."
                          % (ent["where"], parent, self.port_of[parent][0],
                             self.port_of[parent][1], self.port_of[parent][0]))

        # Bridge self VLANs that no port carries.
        for name, ent in self.entries.items():
            if ent["type"] != "bridge" or not ent.get("self_vids"):
                continue
            carried = set()
            for c in self.connections:
                if c.get("port_of") == name:
                    carried |= c.get("port_vids", set())
            for vid in sorted(ent["self_vids"] - carried):
                self.warn("%s.vlans: VLAN %d is on the bridge itself but no port carries it, so it "
                          "only reaches local VLAN interfaces" % (ent["where"], vid))

    def result(self):
        self.collect()
        if isinstance(self.config, dict):
            self.collect_ports()
            self.build()
            self.cross_check()
        conns = sorted(self.connections, key=lambda c: (c["order"], c["conn_name"]))
        for c in conns:
            c.pop("port_vids", None)
            c.pop("port_of", None)
        return {"connections": conns, "errors": self.errors, "warnings": self.warnings}


def nm_parse(config):
    return _Parser(config).result()


class FilterModule(object):
    def filters(self):
        return {"nm_parse": nm_parse}
