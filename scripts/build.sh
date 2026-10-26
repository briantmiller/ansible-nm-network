#!/usr/bin/env bash
# Build the collection tarball into dist/ and print its path.
set -euo pipefail
cd "$(dirname "$0")/.."

ns=$(awk '/^namespace:/{print $2}' galaxy.yml)
name=$(awk '/^name:/{print $2}' galaxy.yml)
version=$(awk '/^version:/{print $2}' galaxy.yml)

find . -name __pycache__ -prune -exec rm -rf {} +
rm -rf .pytest_cache
mkdir -p dist
ansible-galaxy collection build --force --output-path dist .

tarball="dist/${ns}-${name}-${version}.tar.gz"
echo "Built ${tarball}"
tar tzf "$tarball" | sed 's/^/  /'
