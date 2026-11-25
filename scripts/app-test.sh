#!/usr/bin/env sh
# Run the cloud_wms test suite on an isolated, disposable ERPNext stack (project cloud-wms-test).
# The first run creates a test site (several minutes); later runs reuse it and only migrate.
# Pass `clean` to remove the stack and its volumes. Any other arguments go to `bench run-tests`.
set -eu

project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
compose_file="$project_root/docker/compose.test.yml"
wms_image="cloud-wms/erpnext:v16.60.0-wms"

if ! docker image inspect "$wms_image" >/dev/null 2>&1; then
  echo "Image $wms_image is missing. Run \`make image\` first." >&2
  exit 1
fi

if docker compose version >/dev/null 2>&1; then
  compose="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  compose="docker-compose"
else
  echo "Docker Compose is required." >&2
  exit 1
fi
compose="$compose --project-name cloud-wms-test --file $compose_file"

if [ "${1:-}" = "clean" ]; then
  exec $compose down --volumes --remove-orphans
fi

test_args="${*:---app cloud_wms}"

set +e
$compose run --rm runner "
  set -e
  wait-for-it -t 120 db:3306
  wait-for-it -t 120 redis-cache:6379
  ls -1 apps > sites/apps.txt
  bench set-config -g db_host db
  bench set-config -gp db_port 3306
  bench set-config -g redis_cache redis://redis-cache:6379
  bench set-config -g redis_queue redis://redis-queue:6379
  bench set-config -g redis_socketio redis://redis-queue:6379
  site=wms-test.localhost
  if [ ! -d sites/\$site ]; then
    bench new-site \$site --admin-password admin --db-root-username root --db-root-password admin \
      --mariadb-user-host-login-scope='%' --install-app erpnext --install-app cloud_wms
  fi
  bench --site \$site set-config allow_tests true
  bench --site \$site migrate
  bench --site \$site run-tests $test_args
"
status=$?
set -e
$compose stop >/dev/null 2>&1 || true
exit $status
