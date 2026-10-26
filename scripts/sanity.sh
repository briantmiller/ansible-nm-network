#!/usr/bin/env bash
# ansible-test needs the collection under ansible_collections/<ns>/<name>; copy it there.
set -euo pipefail
cd "$(dirname "$0")/.."
ns=$(awk '/^namespace:/{print $2}' galaxy.yml)
name=$(awk '/^name:/{print $2}' galaxy.yml)
dest=".sanity/ansible_collections/${ns}/${name}"
rm -rf .sanity && mkdir -p "$dest"
tar --exclude=./.sanity --exclude=./.git --exclude=./dist --exclude=./.collections -cf - . | tar -xf - -C "$dest"
cd "$dest"
ansible-test sanity --local --python "$(python3 -c 'import sys;print(f"{sys.version_info[0]}.{sys.version_info[1]}")')" \
  "$@"
