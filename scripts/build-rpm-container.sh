#!/usr/bin/env bash
# Build the RPMs inside an EL10 container, from any Linux or macOS host with
# podman or docker. Output goes to dist/rpm/.
#
#   scripts/build-rpm-container.sh [rpmbuild options...]
#
# RPM_BUILD_IMAGE picks the image (default almalinux:10). Any EL10 image whose
# repos provide ansible-core works, e.g. a RHEL 10 UBI on a subscribed host.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
image="${RPM_BUILD_IMAGE:-docker.io/library/almalinux:10}"
engine="${CONTAINER_ENGINE:-$(command -v podman || command -v docker || true)}"
[[ -n "$engine" ]] || { echo "need podman or docker" >&2; exit 1; }

args=$(printf '%q ' "$@")
"$engine" run --rm -v "$root:/src:Z" -w /src "$image" bash -euc "
  dnf -y -q install rpm-build ansible-core python3-pyyaml tar gzip >/dev/null
  scripts/build-rpm.sh $args
  chown -R $(id -u):$(id -g) dist rpmbuild
"
