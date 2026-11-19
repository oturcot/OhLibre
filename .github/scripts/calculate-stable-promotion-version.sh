#!/usr/bin/env bash
set -euo pipefail

next_version="${1:-}"
latest_version="${2:-}"
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
  printf '%s.%s.0\n' "$next_major" "$next_minor"
  exit 0
fi

IFS=. read -r current_major current_minor current_patch <<< "$latest_version"
if (( next_major > current_major )); then
  if (( next_minor != 0 )); then
    echo "For a major release, NEXT_VERSION must use X.0.0." >&2
    exit 1
  fi
  printf '%s.0.0\n' "$next_major"
elif (( next_major == current_major && next_minor > current_minor )); then
  printf '%s.%s.0\n' "$next_major" "$next_minor"
else
  printf '%s.%s.%s\n' "$current_major" "$current_minor" "$((current_patch + 1))"
fi
