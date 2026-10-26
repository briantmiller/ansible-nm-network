#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) 2026 brun064
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: nm_conn_props
short_description: Idempotently set raw NetworkManager connection properties
version_added: 1.0.0
author:
  - brun064 (@brun064)
description:
  - Fills gaps in community.general.nmcli, such as C(bridge.vlan-filtering),
    C(bridge.vlans), C(bridge-port.vlans) and bridge-port settings on ports that
    are not plain ethernet (for example a bond attached to a bridge).
  - Reads each property with C(nmcli -g), compares normalized values, and runs a
    single C(nmcli connection modify) for the ones that differ.
options:
  conn_name:
    description: Connection profile name.
    type: str
    required: true
  properties:
    description: Mapping of NetworkManager property name to value.
    type: dict
    required: true
notes:
  - Supports check mode. A profile that does not exist yet is reported as changed in check mode.
"""

EXAMPLES = r"""
- name: Turn on VLAN filtering on br0 and make VLAN 100 a member of the bridge itself
  local.nm_network.nm_conn_props:
    conn_name: br0
    properties:
      bridge.vlan-filtering: "yes"
      bridge.vlans: "100"

- name: Make a bond a trunk port of br0
  local.nm_network.nm_conn_props:
    conn_name: bond0
    properties:
      bridge-port.vlans: "100, 200, 300 pvid untagged"
"""

RETURN = r"""
conn_name:
  description: The connection profile that was checked.
  returned: always
  type: str
changes:
  description: Properties that differed and were (or in check mode would be) set, with their new values.
  returned: always
  type: dict
"""

import re

from ansible.module_utils.basic import AnsibleModule

TRUE = {"yes", "true", "on", "1"}
FALSE = {"no", "false", "off", "0"}


def _unescape(value):
    return re.sub(r"\\(.)", r"\1", value.strip())


def _norm_vlans(value):
    items = []
    for part in value.split(","):
        tokens = part.split()
        if not tokens:
            continue
        flags = sorted(t.lower() for t in tokens[1:])
        items.append(" ".join([tokens[0]] + flags))

    def key(item):
        first = item.split()[0]
        return int(first.split("-")[0]) if first.split("-")[0].isdigit() else 0

    return ", ".join(sorted(items, key=key))


def normalize(prop, value):
    value = _unescape(str(value))
    if prop.endswith(".vlans"):
        return _norm_vlans(value)
    low = value.lower()
    if low in TRUE:
        return "yes"
    if low in FALSE:
        return "no"
    if low in ("--", ""):
        return ""
    return value


def main():
    module = AnsibleModule(
        argument_spec=dict(
            conn_name=dict(type="str", required=True),
            properties=dict(type="dict", required=True),
        ),
        supports_check_mode=True,
    )
    module.run_command_environ_update = dict(LANG="C", LC_ALL="C", LC_MESSAGES="C")
    nmcli = module.get_bin_path("nmcli", required=True)
    name = module.params["conn_name"]
    props = module.params["properties"] or {}

    changes = {}
    before = {}
    for prop, wanted in props.items():
        rc, out, err = module.run_command([nmcli, "-g", prop, "connection", "show", name])
        if rc != 0:
            if module.check_mode and "no such connection" in err.lower():
                # Connection not created yet (check mode); report as a change.
                before[prop] = None
                changes[prop] = str(wanted)
                continue
            module.fail_json(msg="Cannot read %s from %s: %s" % (prop, name, err.strip()),
                             rc=rc)
        if normalize(prop, out) != normalize(prop, wanted):
            before[prop] = out.strip()
            changes[prop] = str(wanted)

    result = dict(changed=bool(changes), conn_name=name, changes=changes,
                  diff=dict(before=before, after=changes))
    if changes and not module.check_mode:
        cmd = [nmcli, "connection", "modify", name]
        for prop, value in changes.items():
            cmd += [prop, value]
        rc, out, err = module.run_command(cmd)
        if rc != 0:
            module.fail_json(msg="nmcli modify failed: %s" % err.strip(), rc=rc, cmd=cmd, **result)
    module.exit_json(**result)


if __name__ == "__main__":
    main()
