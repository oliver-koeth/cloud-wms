#!/usr/bin/env sh
set -eu

project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)

for path in README.md AGENTS.md ARCHITECTURE.md spec/external-order-flow.md \
  scripts/checkout-erpnext.sh scripts/erpnext-compose.sh scripts/start-erpnext.sh \
  scripts/app-test.sh docker/Containerfile docker/compose.cloud-wms.yml docker/compose.test.yml \
  apps/cloud_wms/pyproject.toml apps/cloud_wms/cloud_wms/hooks.py; do
  test -f "$project_root/$path"
done

test -f "$project_root/.gitmodules"
git -C "$project_root" config --file .gitmodules --get-regexp '^submodule\..*\.path$' \
  | grep -qx 'submodule.vendor/erpnext.path vendor/erpnext'

app_version=$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' "$project_root/apps/cloud_wms/cloud_wms/__init__.py")
test -n "$app_version"

echo "Project scaffold is valid."
