#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 4 ]]; then
  echo "Usage: $0 <source-repo> <target-repo> <merge-commit-sha> <pathspec>" >&2
  exit 2
fi

source_repo="$1"
target_repo="$2"
merge_commit="$3"
pathspec="$4"

[[ "$merge_commit" =~ ^[0-9a-f]{40}$ ]] || {
  echo "Merge commit must be a full SHA." >&2
  exit 1
}

case "$pathspec" in
  dockerfile|.github/workflows/) ;;
  *)
    echo "Unexpected dependency pathspec: $pathspec" >&2
    exit 1
    ;;
esac

git -C "$source_repo" rev-parse --verify "${merge_commit}^1" >/dev/null
patch="$(git -C "$source_repo" diff --binary "${merge_commit}^1" "$merge_commit" -- "$pathspec")"
[[ -n "$patch" ]] || {
  echo "No changes found for $pathspec in the merged dependency commit." >&2
  exit 1
}
printf '%s\n' "$patch" | git -C "$target_repo" apply -
