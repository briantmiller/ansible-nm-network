# NetworkManager Ansible Config Format

## Overview

One YAML file per host describes every NetworkManager connection. The `local.nm_network.configure` role validates it, then creates or updates each profile with `community.general.nmcli`, and fills the gaps the module lacks (bridge VLAN filtering, per-port VLANs, bridge-port settings on non-ethernet ports) with a small idempotent helper module.

| Collection content | Role |
| --- | --- |
| `roles/configure` | Load, validate, delete, create/update, set extra properties, optionally activate |
| `playbooks/site.yml` | Runs the role with `serial`; call it as `local.nm_network.site` |
| `plugins/filter/nm_config.py` | `nm_parse`: parses and validates the config into an ordered list of connections |
| `plugins/modules/nm_conn_props.py` | Sets raw NetworkManager properties idempotently (`nmcli connection modify`) |
| `examples/network.yaml` | The corrected example from the end of this doc |

Run it with:

```
ansible-playbook local.nm_network.site -i inventory -e nm_config_file=network.yaml
```

| Variable | Default | Effect |
| --- | --- | --- |
| `nm_config_file` | none | Path to the config file. Alternatively define `nm_config` directly in host_vars. |
| `nm_activate` | `false` | When `true`, runs `nmcli connection up` on every connection changed in this run, masters first. |
| `nm_fail_on_warnings` | `false` | Turns validation warnings into a failed run. |
| `nm_serial` | `1` | Hosts changed at a time (bundled playbook), so a bad config can't take down a whole group. |

Requires community.general 10.3 or later and NetworkManager on the target. Leaving `nm_activate` off writes profiles without disrupting live links; check the result, then rerun with it on.

## File structure

The file is a set of sections, one per connection type; each section maps an interface name to its settings, and any `community.general.nmcli` parameter that fits the type can be used as-is.

```
<section>:
  <interface name>:
    <nmcli module parameter>: <value>
    ...
```

| Section | NetworkManager type | Can have `ports` |
| --- | --- | --- |
| `bridges` | bridge | yes |
| `bonds` | bond | yes |
| `teams` | team | yes |
| `vlans` | vlan | no |
| `ethernet` | ethernet | no |
| `vxlans`, `macvlans`, `vrfs`, `dummies` | vxlan, macvlan, vrf, dummy | no |
| `gre`, `ipip`, `sit` | IP tunnels | no |
| `infiniband`, `wireguard`, `wifi`, `gsm`, `vpn`, `loopback`, `generic` | same name | no |
| `ovs_bridges`, `ovs_ports`, `ovs_interfaces` | ovs-bridge, ovs-port, ovs-interface | no (use `master`) |

Keys every entry accepts:

| Key | Meaning |
| --- | --- |
| IP and DNS | `ip4`, `gw4`, `dns4`, `routes4` or `routes4_extended`, `method4`, and the `6` equivalents, plus every other IP option the module has |
| `mtu`, `mac`, `zone`, `autoconnect`, `autoconnect_priority`, `dhcp_client_id`, `sriov` | Passed to the module |
| `master`, `slave_type` | Attach this interface to a master; usually inferred (see Port resolution) |
| `state` | `present` (default) or `absent` |
| `conn_name`, `ifname` | Override the profile name or device name; both default to the entry's key |
| `nm_properties` | Raw NetworkManager properties the module lacks, e.g. `bridge.multicast-snooping: false` |

Type-specific keys are listed with each type below. A key that doesn't belong to the entry's type is an error, and a misspelled key is reported with the closest valid name.

## Bridges

A bridge entry holds bridge settings, the bridge's own VLAN memberships, and its ports; each port can carry bridge-port settings and a VLAN list.

```yaml
bridges:
  br0:
    ip4: 1.2.3.4/24
    stp: true
    forwarddelay: 20
    hellotime: 5
    maxage: 12
    vlans:               # VLANs on the bridge device itself
      100: on
    ports:
      eno1:
        settings:
          hairpin: true
          path_cost: 100
        vlans:
          100: on
          200: on
          300: off
      eno2:
        vlans:
          100: private
      eno7:              # a port with no settings
```

| Bridge key | Module default | Notes |
| --- | --- | --- |
| `stp` | `true` | |
| `priority` | 128 | STP bridge priority |
| `forwarddelay` | 15 | Seconds |
| `hellotime` | 2 | Seconds |
| `maxage` | 20 | Seconds; must satisfy 2×(forwarddelay−1) ≥ maxage ≥ 2×(hellotime+1) |
| `ageingtime` | 300 | MAC ageing, seconds |
| `vlan_filtering` | on when any VLANs are listed | Set `false` only for a bridge with no VLANs |
| `vlan_default_pvid` | 1 (NetworkManager) | Untagged VLAN given to ports with no `private` VLAN; `0` disables it |
| `vlans` | none | The bridge's own memberships, same values as port VLANs |
| `ports` | none | Mapping of port name → port spec, or a plain list of names |

A port spec takes three optional keys:

- `settings`: `hairpin`, `path_cost`, `slavepriority` (the STP port priority), plus `mtu` and other common keys when the port has no section of its own.
- `vlans`: a mapping of VLAN ID (or a range such as `100-110`) to a value.
- `nm_properties`: raw `bridge-port.*` properties.

| VLAN value | Result on the port |
| --- | --- |
| `on` | Tagged member |
| `private` | Untagged native VLAN and PVID (an access port); at most one per port |
| `off` | Not a member; removed if it was there before |

The listed VLANs replace the port's whole VLAN set, so a VLAN missing from the list is removed just like one marked `off`. Unquoted `on` and `off` are read by YAML as true and false; both forms work.

With VLAN filtering on, NetworkManager also makes every port an untagged member of VLAN 1 unless that port has a `private` VLAN. Set `vlan_default_pvid: 0` if trunk ports should carry only the listed VLANs.

## Bonds

A bond entry holds bond settings and a plain list of port names; bond ports take no settings of their own.

```yaml
bonds:
  bond0:
    mode: 802.3ad
    miimon: 100
    downdelay: 10
    xmit_hash_policy: layer3+4
    ports:
      - eno3
      - eno4
```

| Bond key | Module default | Notes |
| --- | --- | --- |
| `mode` | balance-rr | 802.3ad, active-backup, balance-alb, balance-rr, balance-tlb, balance-xor, broadcast |
| `miimon` | none | Link check interval, ms; a warning is shown if neither this nor `arp_interval` is set |
| `updelay`, `downdelay` | none | ms |
| `arp_interval`, `arp_ip_target` | none | ARP monitoring instead of MII |
| `primary` | none | Preferred port for active-backup |
| `xmit_hash_policy` | none | layer2, layer2+3, layer3+4, encap2+3, encap3+4 |
| `fail_over_mac` | none | none, active, follow |
| `bond_mode_behavior` | none | preserve or reset (community.general 13.3+) |

Teams follow the same shape under `teams`, with `runner`, `runner_hwaddr_policy` and `runner_fast_rate`.

## VLANs, ethernet and other types

VLAN interfaces need `vlanid` (1–4094) and `vlandev` (the parent device); ethernet and the other types take only common keys plus their own module options.

```yaml
vlans:
  br0.100:
    vlandev: br0
    vlanid: 100
    method4: disabled    # no address; otherwise NetworkManager tries DHCP
  vlan50:
    vlandev: eno5
    vlanid: 50
    ip4: 5.6.7.8/24

ethernet:
  eno6:
    ip4: 4.3.2.1/24
    gw4: 4.3.2.2
    routes4_extended:
      - ip: 10.0.0.0/16
        next_hop: 4.3.2.3
        metric: 200
```

| Type | Its own keys |
| --- | --- |
| vlan | `vlanid`, `vlandev`, `flags`, `ingress`, `egress` |
| vxlan | `vxlan_id`, `vxlan_remote`, `vxlan_local`, `vxlan_parent` |
| gre, ipip, sit | `ip_tunnel_dev`, `ip_tunnel_remote`, `ip_tunnel_local`, `ip_tunnel_input_key`, `ip_tunnel_output_key` |
| vrf | `table` |
| infiniband | `transport_mode`, `infiniband_mac` |
| macvlan, wireguard, gsm, vpn | `macvlan`, `wireguard`, `gsm`, `vpn` (each a dict of that module suboption set) |
| wifi | `ssid` (required), `wifi`, `wifi_sec` |

Use either `routes4` or `routes4_extended` on one interface, not both; the module rejects the combination. The same applies to `routes6`/`routes6_extended` and to `gw4` with `never_default4`. Keep keys and passwords for wireguard, wifi and VPN in Ansible Vault.

## Port resolution

A port listed under a bridge, bond or team gets its own simple port profile only when it has no section of its own; if it does, that section's profile is attached to the master and nothing else is created.

For each name under `ports`:

1. **No section of its own** (eno1, eno3 in the example): the role creates an ethernet profile named `<master>-<port>` (`br0-eno1`, `bond0-eno3`) with `master` and `slave_type` set. This is exactly what the module's `bridge-slave` and `bond-slave` types produce, minus the warning those types print on every run.
2. **Has its own section** (bond0 in `bonds`): no extra profile. The bond's profile gets `master: br0` and `slave_type: bridge`, inferred from the bridge section. If the bond already says `master: br0`, that's fine; if it names a different master, that's an error.
3. The port's `settings` (hairpin, path_cost, slavepriority) and `vlans` are applied to whichever profile resulted, as `bridge-port.*` properties. When the port has its own section, any other setting must live in that section.

An interface that sets `master` but isn't listed under any `ports` is also accepted; `slave_type` is inferred from the master's section, or must be given when the master isn't in the file.

A port can belong to only one master. IP settings on a port are ignored by NetworkManager, so the role warns when it sees them.

Generated port profiles follow their master's `state`: set `state: absent` on a bond and its port profiles are removed too, ports first.

## Host VLAN interfaces on a VLAN-aware bridge

To give the host an address on a VLAN that the bridge also switches, put the VLAN interface on the bridge (`br0.100`) and list that VLAN in three places; leaving out the bridge's own membership is the usual mistake and silently drops the traffic.

| Where | Key | Why |
| --- | --- | --- |
| Ports that carry it | `bridges.br0.ports.<port>.vlans: {100: on}` | Frames for VLAN 100 enter and leave the bridge |
| The bridge itself | `bridges.br0.vlans: {100: on}` | The bridge passes VLAN 100 up to the host; without it the bridge drops those frames |
| The VLAN interface | `vlans.br0.100: {vlandev: br0, vlanid: 100}` | The host's interface on VLAN 100, where its address goes |

A VLAN interface on a bridge port (`vlandev: eno1` when eno1 is a port of br0) is the other trap. The bridge takes eno1's frames before the VLAN interface sees them, so it never receives traffic. Use `vlandev: br0` instead. A VLAN on an interface that isn't part of any bridge or bond, like vlan50 on eno5, is unaffected.

The role checks these cases and prints a warning naming the fix:

- A VLAN interface on a filtering bridge whose ID isn't in that bridge's `vlans`.
- A VLAN interface whose `vlandev` is a bridge or bond port.
- A VLAN in a bridge's own `vlans` that no port carries (it only reaches local interfaces, which may be intended).

## Validation

The whole file is checked before any connection is touched: errors stop the run, and warnings print and continue unless `nm_fail_on_warnings` is set.

| Errors (run stops) | Warnings (run continues) |
| --- | --- |
| Unknown section or setting, with a suggested spelling | VLAN interface on a filtering bridge without the bridge's own membership |
| A setting that doesn't apply to the type (e.g. `miimon` on a bridge) | VLAN interface whose parent is a bridge or bond port |
| Bridge-port setting outside a port's `settings` | Bridge VLAN that no port carries |
| Missing `vlanid`/`vlandev`, or VLAN ID outside 1–4094 | IP settings on a port |
| Invalid port VLAN value, or more than one `private` VLAN on a port | STP timers that break the 802.1D rule |
| Port listed under two masters, or `master` that disagrees with the `ports` list | Bond with neither `miimon` nor `arp_interval` |
| `master` not in the file and no `slave_type` given | |
| Port VLANs with `vlan_filtering: false` | |
| `routes4` with `routes4_extended` (and the other module conflicts), wifi without `ssid` | |
| Same interface defined in two sections | |

## Full example

[`examples/network.yaml`](../examples/network.yaml) validates with no errors or warnings and produces nine connection profiles:

| Profile | Type | Created as | Extra properties set |
| --- | --- | --- | --- |
| br0 | bridge | own section | vlan-filtering yes, vlans 100 |
| bond0 | bond | own section, attached to br0 | bridge-port vlans 100, 200, 300, 400 |
| eno6 | ethernet | own section | none |
| br0.100 | vlan | own section | none |
| vlan50 | vlan | own section | none |
| bond0-eno3, bond0-eno4 | ethernet | generated bond port | none |
| br0-eno1 | ethernet | generated bridge port | hairpin yes, vlans 100, 200 |
| br0-eno2 | ethernet | generated bridge port | vlans 100 pvid untagged |
