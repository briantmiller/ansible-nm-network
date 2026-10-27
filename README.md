# local.nm_network

Configures NetworkManager from one structured YAML file per host: bridges (with VLAN
filtering and per-port VLANs), bonds, teams, VLANs, ethernet and every other connection
type `community.general.nmcli` supports. The file is validated before anything is changed.

The config format, port rules and validation checks are described in
[docs/config-format.md](docs/config-format.md). `examples/network.yaml` is a complete example.

## Install

Build the tarball (see Building below) or download it from a release, then:

    ansible-galaxy collection install local-nm_network-1.0.0.tar.gz

This also installs `community.general` (>= 10.3.0) if it isn't present.

## Use

Run the bundled playbook:

    ansible-playbook local.nm_network.site -i inventory -e nm_config_file=network.yaml
    ansible-playbook local.nm_network.site -i inventory -e nm_config_file=network.yaml -e nm_activate=true

Or call the role from your own playbook:

```yaml
- hosts: hypervisors
  become: true
  serial: 1
  roles:
    - role: local.nm_network.configure
      vars:
        nm_config_file: "host_network/{{ inventory_hostname }}.yaml"
```

| Variable | Default | Effect |
| --- | --- | --- |
| `nm_config_file` | none | Config file to load; or define `nm_config` directly |
| `nm_activate` | `false` | `nmcli connection up` on connections changed in this run, masters first |
| `nm_fail_on_warnings` | `false` | Fail when validation produces warnings |
| `nm_hosts`, `nm_serial` | `all`, `1` | Bundled playbook only: target hosts and batch size |

Run with `--check` first, and leave `nm_activate` off until the profiles look right,
especially when connected over an interface being changed.

## Contents

| Name | Type | Purpose |
| --- | --- | --- |
| `local.nm_network.configure` | role | Load, validate, delete, create/update, set extra properties, activate |
| `local.nm_network.site` | playbook | Runs the role with `serial` |
| `local.nm_network.nm_parse` | filter | Parses and validates the config into ordered connections |
| `local.nm_network.nm_conn_props` | module | Sets NetworkManager properties the nmcli module lacks |

## Building

Requires Python 3.10+ and GNU make.

    make deps        # ansible-core, pytest, and community.general into .collections/
    make test        # parser unit tests, no NetworkManager needed
    make sanity      # ansible-test sanity
    make dryrun      # check-mode run of examples/network.yaml against a stub nmcli
    make build       # tests, then dist/local-nm_network-<version>.tar.gz
    make install     # build and install for the current user

Other targets: `make version V=1.1.0` sets the version (galaxy.yml and RPM spec), and `make namespace NS=myorg`
renames the namespace everywhere. `local` is a placeholder; publishing to Galaxy or
Automation Hub needs a namespace you own.

`scripts/dryrun.sh other.yaml` dry-runs any config file. Set `COLLECTIONS_DIR` to use an
existing collections path instead of `.collections/`.

CI (`.github/workflows/ci.yml`) runs test, sanity, dryrun and build on ansible-core 2.16
and 2.18. Pushing a `v*` tag also attaches the tarball to a GitHub release; Galaxy
publishing is stubbed in the workflow, ready for a `GALAXY_API_KEY` secret.

## RPM for RHEL 10

The `rpm/` directory has a spec that packages the collection as
`ansible-collection-local-nm-network`, installed to
`/usr/share/ansible/collections`, which ansible-core searches by default.

Build on a RHEL 10 (or AlmaLinux/Rocky 10) host:

    sudo dnf install rpm-build ansible-core
    make rpm                # tests, then dist/rpm/*.el10.noarch.rpm and *.src.rpm
    make rpmlint            # optional: needs rpmlint (EPEL)

Or build in an EL10 container from any machine with podman or docker:

    make rpm-container                          # default image: almalinux:10
    RPM_BUILD_IMAGE=<el10 image> make rpm-container

Pass rpmbuild options with `RPMBUILD_ARGS`, e.g. `make rpm RPMBUILD_ARGS="--without tests"`.

| Build option | Effect |
| --- | --- |
| `--without community_general_rpm` | No RPM dependency on community.general; use when it comes from Galaxy or Automation Hub instead of EPEL |
| `--without tests` | Skip the parser tests in `%check` |

Install on the target:

    sudo dnf install ./ansible-collection-local-nm-network-1.0.0-1.el10.noarch.rpm

The package requires ansible-core (RHEL 10 AppStream), NetworkManager, and
`ansible-collection-community-general` from EPEL 10, unless it was built
`--without community_general_rpm`. To enable EPEL on RHEL 10, enable the
CodeReady Builder repo and install `epel-release`, following the EPEL docs.

The RPM asks for community.general 10.0.0 or later, not the 10.3.0 in
galaxy.yml, because EPEL 10 first shipped 10.0.1. Newer module options, such
as `fail_over_mac` (10.3.0), only work with a community.general that has them;
the role passes an option to the module only when your config sets it.

`make version` and `make namespace` update the spec along with galaxy.yml.
`make namespace` also renames the spec, and `scripts/build-rpm.sh` refuses to
build if the spec and galaxy.yml disagree. Set `%global project_url` in the
spec to where the repository is hosted.

## Layout

    galaxy.yml                    collection metadata and version
    plugins/filter/nm_config.py   nm_parse filter: parser and validator
    plugins/modules/nm_conn_props.py
    roles/configure/              the role
    playbooks/site.yml            bundled playbook
    examples/network.yaml         complete example config
    docs/config-format.md         config file reference
    tests/unit/                   parser tests
    tests/stub/nmcli              fake nmcli for dry runs (not shipped)
    rpm/                          RPM spec and rpmlint filters (not shipped)
    scripts/                      build, RPM build, sanity, dryrun, version and namespace (not shipped)
