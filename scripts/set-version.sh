#!/usr/bin/env bash
# Set the collection version in galaxy.yml and the RPM spec, and add an RPM
# changelog entry. Add the CHANGELOG.md entry yourself.
set -euo pipefail
cd "$(dirname "$0")/.."
new="${1:?usage: set-version.sh <x.y.z>}"
[[ "$new" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "version must be x.y.z" >&2; exit 1; }
spec=$(ls rpm/*.spec)

sed -i -E "s/^version: .*/version: ${new}/" galaxy.yml
sed -i -E "s/^(%global collection_version ).*/\1${new}/" "$spec"

who="$(git config user.name 2>/dev/null || echo "${USER:-builder}") <$(git config user.email 2>/dev/null || echo "${USER:-builder}@localhost")>"
entry="* $(LC_ALL=C date '+%a %b %d %Y') ${who} - ${new}-1\n- Update to ${new}\n"
sed -i "/^%changelog$/a ${entry}" "$spec"
echo "version set to ${new} in galaxy.yml and ${spec}; add a CHANGELOG.md entry"
