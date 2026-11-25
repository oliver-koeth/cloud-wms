#!/usr/bin/env sh
set -eu

project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)

"$project_root/scripts/erpnext-compose.sh" up -d

cat <<'MESSAGE'

ERPNext is starting. First boot creates the site and can take several minutes.
Open http://localhost:8080 once `make status` reports the frontend as running.
Local evaluation login: Administrator / admin

The stack runs the cloud-wms/erpnext image (upstream ERPNext + the cloud_wms app).
Apply the app to the site with `make install-app` (first time) or `make migrate`,
then `make demo-data` for the local Sales/Supervisor/Worker users and locations.

This stack is intentionally disposable and must not receive the future WMS UI.
MESSAGE
