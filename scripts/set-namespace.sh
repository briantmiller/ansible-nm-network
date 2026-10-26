#!/usr/bin/env bash
# Rename the collection namespace everywhere it appears (galaxy.yml, FQCNs, docs).
set -euo pipefail
cd "$(dirname "$0")/.."
new="${1:?usage: set-namespace.sh <namespace>}"
[[ "$new" =~ ^[a-z][a-z0-9_]*$ ]] || { echo "namespace must be lowercase letters, digits, _" >&2; exit 1; }

old=$(awk '/^namespace:/{print $2}' galaxy.yml)
name=$(awk '/^name:/{print $2}' galaxy.yml)
[[ "$old" == "$new" ]] && { echo "already $new"; exit 0; }

sed -i -E "s/^namespace: .*/namespace: ${new}/" galaxy.yml
grep -rlF "${old}.${name}" --exclude-dir=.git --exclude-dir=dist --exclude-dir=.collections . \
  | xargs -r sed -i "s/${old}\.${name}/${new}.${name}/g"
grep -rlF "${old}-${name}-" --exclude-dir=.git --exclude-dir=dist . \
  | xargs -r sed -i "s/${old}-${name}-/${new}-${name}-/g"
echo "namespace: ${old} -> ${new}"
