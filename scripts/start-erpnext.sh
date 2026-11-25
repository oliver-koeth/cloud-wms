#!/usr/bin/env sh
set -eu

project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)

"$project_root/scripts/erpnext-compose.sh" up -d

cat <<'MESSAGE'

ERPNext is starting. First boot creates the site and can take several minutes.
Open http://localhost:8080 once `make status` reports the frontend as running.
Local evaluation login: Administrator / admin

This stack is intentionally disposable and must not receive the future WMS UI.
MESSAGE
