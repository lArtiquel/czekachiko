#!/usr/bin/env bash
# Refuse any deploy target that is not a directory named "czekachiko", so a typo can never
# point rsync --delete at a parent directory or at another project.
set -euo pipefail
path="${1:-}"
if [[ -z "$path" || "$(basename -- "$path")" != "czekachiko" ]]; then
  echo "refusing DEPLOY_PATH='$path': it must end in /czekachiko" >&2
  exit 1
fi
