#!/usr/bin/env bash
set -euo pipefail

script="$(dirname "${BASH_SOURCE[0]}")/has-container-input-changes.sh"
temp_dir="$(mktemp -d)"
trap 'rm -rf "$temp_dir"' EXIT

git -C "$temp_dir" init -q
git -C "$temp_dir" config user.name test
git -C "$temp_dir" config user.email test@example.com
printf 'FROM debian:stable\n' > "$temp_dir/dockerfile"
printf 'name: CI\n' > "$temp_dir/.workflow"
git -C "$temp_dir" add .
git -C "$temp_dir" commit -qm baseline
baseline="$(git -C "$temp_dir" rev-parse HEAD)"

printf 'name: Updated CI\n' > "$temp_dir/.workflow"
git -C "$temp_dir" add .
git -C "$temp_dir" commit -qm workflow-only
workflow_commit="$(git -C "$temp_dir" rev-parse HEAD)"
if bash "$script" "$temp_dir" "$baseline" "$workflow_commit"; then
  echo "Workflow-only changes must not require a container release." >&2
  exit 1
fi

printf 'FROM debian:bookworm\n' > "$temp_dir/dockerfile"
git -C "$temp_dir" add .
git -C "$temp_dir" commit -qm container-change
container_commit="$(git -C "$temp_dir" rev-parse HEAD)"
bash "$script" "$temp_dir" "$baseline" "$container_commit"
