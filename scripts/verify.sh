#!/usr/bin/env sh
set -eu

project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)

for path in README.md AGENTS.md ARCHITECTURE.md spec/external-order-flow.md \
  scripts/checkout-erpnext.sh scripts/erpnext-compose.sh scripts/start-erpnext.sh; do
  test -f "$project_root/$path"
done

test -f "$project_root/.gitmodules"
git -C "$project_root" config --file .gitmodules --get-regexp '^submodule\..*\.path$' \
  | grep -qx 'submodule.vendor/erpnext.path vendor/erpnext'

echo "Project scaffold is valid."
