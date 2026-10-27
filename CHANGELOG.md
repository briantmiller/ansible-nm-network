# Changelog

## Unreleased

- RPM packaging for RHEL 10: spec in `rpm/`, `make rpm`, `make rpm-container`, `make rpmlint`.
- `make version` also updates the RPM spec version and changelog.
- LICENSE now contains the full GPL-3.0 text.

## 1.0.0 (2026-10-26)

First release.

- `configure` role and `site` playbook: configure NetworkManager from one YAML file per host.
- `nm_parse` filter: parses and validates bridges, bonds, teams, VLANs, ethernet and every
  other connection type `community.general.nmcli` supports; infers port masters.
- `nm_conn_props` module: sets bridge VLAN filtering, per-port VLANs and bridge-port settings
  the nmcli module lacks.
