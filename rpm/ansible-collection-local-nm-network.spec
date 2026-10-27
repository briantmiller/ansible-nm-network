# RPM spec for the local.nm_network Ansible collection.
#
# Build with scripts/build-rpm.sh (or `make rpm`), which makes the source tarball
# and checks that the values below match galaxy.yml. `make version` and
# `make namespace` keep them in sync, and the namespace change also renames
# this file, since rpmlint expects it to be named after the package.
#
# Build options:
#   --without community_general_rpm  Drop the RPM dependency on community.general,
#                                    for hosts that get it from Galaxy or
#                                    Automation Hub instead of EPEL.
#   --without tests                  Skip the parser unit tests in %%check.

%global collection_namespace local
%global collection_name nm_network
%global collection_version 1.0.0

# Oldest community.general this collection runs with. galaxy.yml asks for 10.3.0
# because fail_over_mac needs it, but every newer module option is only passed
# when the config sets it, and EPEL 10 first shipped 10.0.1.
%global community_general_min 10.0.0

%bcond_without community_general_rpm
%bcond_without tests

# Project home page; change to where the repository is hosted.
%global project_url https://github.com/%{collection_namespace}/ansible-nm-network

%global collection_dir %{_datadir}/ansible/collections/ansible_collections/%{collection_namespace}/%{collection_name}
# Package name suffix: namespace-name with underscores as hyphens (Fedora naming).
%global pkg_suffix local-nm-network

# Ansible modules keep their #!/usr/bin/python shebang (Ansible rewrites it on
# the target) and are never imported from site-packages, so skip shebang
# mangling and byte-compilation for the collection tree.
%global __brp_mangle_shebangs_exclude_from ^%{_datadir}/ansible/collections/
%global __brp_python_bytecompile %{nil}
%global _python_bytecompile_extra 0

Name:           ansible-collection-%{pkg_suffix}
Version:        %{collection_version}
Release:        1%{?dist}
Summary:        Ansible collection that configures NetworkManager from a structured YAML file

License:        GPL-3.0-or-later
URL:            %{project_url}
Source0:        %{name}-%{version}.tar.gz

BuildArch:      noarch

BuildRequires:  ansible-core >= 2.15
# python3-pyyaml comes with ansible-core; listed for the %%check tests.
BuildRequires:  python3-pyyaml

Requires:       ansible-core >= 2.15
%if %{with community_general_rpm}
Requires:       ansible-collection-community-general >= %{community_general_min}
%endif
Requires:       NetworkManager

Provides:       ansible-collection(%{collection_namespace}.%{collection_name}) = %{version}

%description
The %{collection_namespace}.%{collection_name} Ansible collection configures
NetworkManager from one structured YAML file per host: bridges with VLAN
filtering and per-port VLANs, bonds, teams, VLANs, Ethernet and every other
connection type the community.general NetworkManager module supports. The
whole file is validated before any connection is changed.

It contains the configure role, the site playbook, the nm_parse filter and
the nm_conn_props module. Run the playbook as
%{collection_namespace}.%{collection_name}.site. The configuration file format
is documented in the package documentation directory.

%prep
%autosetup -n %{name}-%{version}

%build
export ANSIBLE_HOME="%{_builddir}/ansible-home"
ansible-galaxy collection build --output-path build .

%install
export ANSIBLE_HOME="%{_builddir}/ansible-home"
export ANSIBLE_COLLECTIONS_PATH=%{buildroot}%{_datadir}/ansible/collections
ansible-galaxy collection install --offline --no-deps --force \
    -p %{buildroot}%{_datadir}/ansible/collections \
    build/%{collection_namespace}-%{collection_name}-%{version}.tar.gz

%check
%if %{with tests}
# Runs tests/unit without pytest, which RHEL 10 does not ship in AppStream.
%{?python3}%{!?python3:python3} -I -B - %{buildroot}%{collection_dir} <<'EOF'
import importlib.util, inspect, pathlib, sys
root = pathlib.Path(sys.argv[1])
failed = 0
for path in sorted((root / "tests" / "unit").rglob("test_*.py")):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for name, fn in inspect.getmembers(mod, inspect.isfunction):
        if not name.startswith("test_"):
            continue
        try:
            fn()
            print("PASS", name)
        except Exception as exc:
            failed += 1
            print("FAIL", name, repr(exc))
sys.exit(1 if failed else 0)
EOF
%endif

%files
%license LICENSE
%doc README.md CHANGELOG.md docs/config-format.md examples/network.yaml
%dir %{_datadir}/ansible/collections/ansible_collections/%{collection_namespace}
%{collection_dir}

%changelog
* Tue Oct 27 2026 brun064 <brun064@gmail.com> - 1.0.0-1
- First RPM release of the local.nm_network collection
