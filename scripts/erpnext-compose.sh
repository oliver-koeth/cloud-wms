#!/usr/bin/env sh
set -eu

project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
runtime_dir="$project_root/.runtime/frappe_docker"
frappe_docker_commit="f5c32e532c6b3d1549ad4a530f7e5a7d4d2d76e9"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker Desktop (or Docker Engine) is required. See README.md." >&2
  exit 1
fi

if [ ! -d "$runtime_dir/.git" ]; then
  mkdir -p "$(dirname "$runtime_dir")"
  git clone --depth 1 https://github.com/frappe/frappe_docker.git "$runtime_dir"
  git -C "$runtime_dir" checkout --detach "$frappe_docker_commit"
fi

if ! grep -Fq 'image: frappe/erpnext:v16.60.0' "$runtime_dir/pwd.yml"; then
  echo "Pinned Frappe Docker checkout does not contain the expected ERPNext v16.60.0 image." >&2
  exit 1
fi

wms_image="cloud-wms/erpnext:v16.60.0-wms"
if ! docker image inspect "$wms_image" >/dev/null 2>&1; then
  echo "Image $wms_image is missing. Run \`make image\` first." >&2
  exit 1
fi

# `pwd.yml` is the upstream, disposable local evaluation stack and is used without local edits.
# The override only swaps the ERPNext image for one that also contains the cloud_wms app.
if docker compose version >/dev/null 2>&1; then
  exec docker compose --project-name cloud-wms-erpnext --file "$runtime_dir/pwd.yml" \
    --file "$project_root/docker/compose.cloud-wms.yml" "$@"
fi

if command -v docker-compose >/dev/null 2>&1; then
  exec docker-compose --project-name cloud-wms-erpnext --file "$runtime_dir/pwd.yml" \
    --file "$project_root/docker/compose.cloud-wms.yml" "$@"
fi

echo "Docker Compose is required. Install Docker Compose v2 or provide docker-compose." >&2
exit 1
