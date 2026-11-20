#!/usr/bin/env bash
set -euo pipefail

mode="$1"
next="$2"
latest="$3"
requested="${4:-}"
pattern='^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$'
[[ "$next" =~ $pattern ]] || { echo "Invalid NEXT_VERSION: $next" >&2; exit 1; }
[[ -z "$latest" || "$latest" =~ $pattern ]] || { echo "Invalid stable version: $latest" >&2; exit 1; }
IFS=. read -r nmajor nminor npatch <<< "$next"
if [[ -n "$latest" ]]; then
  IFS=. read -r major minor patch <<< "$latest"
else
  if [[ "$mode" == promotion || "$mode" == beta ]]; then
    major="$nmajor" minor="$nminor" patch=-1
  else
    major=0 minor=1 patch=-1
  fi
fi

case "$mode" in
  promotion|beta)
    if (( nmajor > major || (nmajor == major && nminor > minor) )); then
      (( nmajor == major || nminor == 0 )) || { echo "A new major line must be X.0" >&2; exit 1; }
      base="$nmajor.$nminor.0"
    else
      base="$major.$minor.$((patch + 1))"
    fi
    ;;
  patch) base="$major.$minor.$((patch + 1))" ;;
  minor)
    if [[ -z "$latest" ]]; then
      base=0.1.0
    else
      (( nmajor == major && nminor > minor && npatch == 0 )) || {
        echo "For a minor release, NEXT_VERSION must advance the minor line and end in .0." >&2
        exit 1
      }
      base="$next"
    fi
    ;;
  major)
    if [[ -z "$latest" ]]; then
      base=1.0.0
    else
      (( nmajor > major && nminor == 0 && npatch == 0 )) || {
        echo "For a major release, NEXT_VERSION must advance the major line and end in .0.0." >&2
        exit 1
      }
      base="$next"
    fi
    ;;
  custom)
    [[ "$requested" =~ $pattern ]] || { echo "Custom version must be X.Y.Z" >&2; exit 1; }
    if [[ -n "$latest" && "$(printf '%s\n%s\n' "$latest" "$requested" | sort -V | tail -n 1)" != "$requested" ]] ||
       [[ "$latest" == "$requested" ]]; then
      echo "Custom version must be greater than $latest" >&2
      exit 1
    fi
    base="$requested"
    ;;
  *) echo "Invalid release type: $mode" >&2; exit 1 ;;
esac
if [[ "$mode" == beta ]]; then
  number=0
  while IFS= read -r tag; do
    if [[ "$tag" =~ ^${base//./\.}-beta\.([0-9]+)$ ]] && (( BASH_REMATCH[1] >= number )); then
      number=$((BASH_REMATCH[1] + 1))
    fi
  done < <(git tag --list "${base}-beta.*")
  base="$base-beta.$number"
fi
printf '%s\n' "$base"
