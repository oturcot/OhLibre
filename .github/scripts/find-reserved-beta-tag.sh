#!/usr/bin/env bash
set -euo pipefail

tags="$(git tag --list --points-at "$1" --sort=-v:refname '*-beta.*')"
while IFS= read -r tag; do
  if [[ "$tag" =~ ^[0-9]+\.[0-9]+\.[0-9]+-beta\.[0-9]+$ ]]; then
    printf '%s\n' "$tag"
    exit 0
  fi
done <<< "$tags"
