#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 3 ]]; then
  echo "Usage: $0 <repository> <base-ref> <target-ref>" >&2
  exit 2
fi

repository="$1"
base_ref="$2"
target_ref="$3"

git -C "$repository" rev-parse --verify "${base_ref}^{commit}" >/dev/null
git -C "$repository" rev-parse --verify "${target_ref}^{commit}" >/dev/null

if git -C "$repository" diff --quiet "$base_ref" "$target_ref" -- dockerfile entrypoint.sh; then
  exit 1
else
  status=$?
  [[ "$status" -eq 1 ]] || exit "$status"
fi
