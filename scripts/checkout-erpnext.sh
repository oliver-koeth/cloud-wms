#!/usr/bin/env sh
set -eu

project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
source_dir="$project_root/vendor/erpnext"

if [ ! -d "$project_root/.git" ]; then
  echo "This project must be a Git repository before ERPNext can be checked out." >&2
  exit 1
fi

if [ ! -f "$project_root/.gitmodules" ]; then
  echo "The ERPNext source submodule is not configured. See README.md." >&2
  exit 1
fi

git -C "$project_root" submodule update --init --recursive vendor/erpnext

if [ ! -f "$source_dir/erpnext/__init__.py" ]; then
  echo "ERPNext checkout did not complete as expected: package source is missing." >&2
  exit 1
fi

echo "ERPNext source is available at $source_dir"
git -C "$source_dir" status --short
