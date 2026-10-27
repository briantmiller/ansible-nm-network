#!/usr/bin/env bash
# Build the collection SRPM and noarch RPM on an EL host (RHEL 10, Alma, Rocky).
#
#   scripts/build-rpm.sh [rpmbuild options...]
#   scripts/build-rpm.sh --without community_general_rpm
#
# Needs rpm-build and ansible-core (dnf install rpm-build ansible-core).
# Output goes to dist/rpm/. Set RPMBUILD_NODEPS=1 to skip BuildRequires checks
# (for building outside EL, e.g. a quick test on another distro).
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"
spec=$(ls rpm/*.spec)

for tool in rpmbuild ansible-galaxy tar; do
  command -v "$tool" >/dev/null || { echo "missing $tool (dnf install rpm-build ansible-core)" >&2; exit 1; }
done

galaxy() { awk -v k="$1:" '$1==k{print $2}' galaxy.yml; }
specvar() { awk -v k="$1" '$1=="%global" && $2==k{print $3}' "$spec"; }

ns=$(galaxy namespace); name=$(galaxy name); version=$(galaxy version)
# The spec is embedded in the SRPM, so its own values must be right, not just
# overridden on the command line.
mismatch=0
suffix="${ns//_/-}-${name//_/-}"
for pair in "collection_namespace:$ns" "collection_name:$name" "collection_version:$version" "pkg_suffix:$suffix"; do
  key=${pair%%:*}; want=${pair#*:}; have=$(specvar "$key")
  if [[ "$have" != "$want" ]]; then
    echo "$spec: $key is '$have' but galaxy.yml says '$want'" >&2; mismatch=1
  fi
done
if (( mismatch )); then
  echo "Run 'make version V=$version' or 'make namespace NS=$ns' to sync them." >&2
  exit 1
fi

pkg="ansible-collection-${suffix}"
[[ "$spec" == "rpm/${pkg}.spec" ]] || echo "warning: $spec should be named rpm/${pkg}.spec" >&2
top="$root/rpmbuild"
rm -rf "$top"; mkdir -p "$top"/{SOURCES,SPECS,BUILD,RPMS,SRPMS}

# Source tarball from the working tree (top dir <pkg>-<version>).
tar --exclude=./.git --exclude=./dist --exclude=./rpmbuild --exclude=./.collections \
    --exclude=./.sanity --exclude=./.pytest_cache --exclude='__pycache__' \
    --transform "s,^\.,${pkg}-${version}," \
    -czf "$top/SOURCES/${pkg}-${version}.tar.gz" .
cp "$spec" "$top/SPECS/"

opts=()
[[ "${RPMBUILD_NODEPS:-0}" == 1 ]] && opts+=(--nodeps)
rpmbuild -ba --define "_topdir $top" "${opts[@]}" "$@" "$top/SPECS/$(basename "$spec")"

mkdir -p dist/rpm
find "$top/RPMS" "$top/SRPMS" -name '*.rpm' -exec cp {} dist/rpm/ \;
echo "Built:"; find dist/rpm -name '*.rpm' | sort | sed 's/^/  /'
