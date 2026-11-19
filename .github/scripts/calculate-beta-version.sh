#!/usr/bin/env bash
set -euo pipefail

next_version="${1:-}"
latest_version="${2:-}"
existing_tags="${3:-}"

version_pattern='^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$'
if [[ ! "$next_version" =~ $version_pattern ]]; then
  echo "NEXT_VERSION must use X.Y.Z format." >&2
  exit 1
fi
if [[ -n "$latest_version" && ! "$latest_version" =~ $version_pattern ]]; then
  echo "Latest stable version must use X.Y.Z format." >&2
  exit 1
fi

IFS=. read -r next_major next_minor _ <<< "$next_version"
if [[ -z "$latest_version" ]]; then
  base_version="$next_major.$next_minor.0"
else
  IFS=. read -r current_major current_minor current_patch <<< "$latest_version"
  if (( next_major > current_major )) ||
    (( next_major == current_major && next_minor > current_minor )); then
    base_version="$next_major.$next_minor.0"
  else
    base_version="$current_major.$current_minor.$((current_patch + 1))"
  fi
fi

beta_number=0
while IFS= read -r tag; do
  if [[ "$tag" =~ ^${base_version//./\.}-beta\.([0-9]+)$ ]] &&
    (( BASH_REMATCH[1] >= beta_number )); then
    beta_number=$((BASH_REMATCH[1] + 1))
  fi
done <<< "$existing_tags"

printf '%s-beta.%s\n' "$base_version" "$beta_number"
