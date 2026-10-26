#!/usr/bin/env bash
# Check-mode run of the bundled playbook against localhost, with a stub nmcli that
# reports no existing connections. Proves parsing, ordering and module arguments
# without touching the network. Pass another config file as $1.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
config="$(realpath "${1:-$root/examples/network.yaml}")"
work="$(mktemp -d)"; trap 'rm -rf "$work"' EXIT

ns=$(awk '/^namespace:/{print $2}' "$root/galaxy.yml")
name=$(awk '/^name:/{print $2}' "$root/galaxy.yml")

# Collection under test, plus community.general from .collections or COLLECTIONS_DIR.
mkdir -p "$work/ac/ansible_collections/$ns"
ln -s "$root" "$work/ac/ansible_collections/$ns/$name"
deps="${COLLECTIONS_DIR:-$root/.collections}"
[[ -d "$deps/ansible_collections/community/general" ]] || \
  ansible-galaxy collection install -r "$root/requirements.yml" -p "$deps"

mkdir -p "$work/bin"; cp "$root/tests/stub/nmcli" "$work/bin/nmcli"; chmod +x "$work/bin/nmcli"
export NMCLI_STUB_LOG="$work/nmcli.log"

cd "$work"
PATH="$work/bin:$PATH" ANSIBLE_COLLECTIONS_PATH="$work/ac:$deps" \
  ansible-playbook "$ns.$name.site" -i localhost, -c local --check \
    -e "nm_config_file=$config" -e ansible_become=false \
    -e "ansible_python_interpreter=$(command -v python3)"
echo "nmcli calls:"; sed 's/^/  /' "$NMCLI_STUB_LOG"
