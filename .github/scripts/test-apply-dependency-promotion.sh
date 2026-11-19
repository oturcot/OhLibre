#!/usr/bin/env bash
set -euo pipefail

script="$(dirname "${BASH_SOURCE[0]}")/apply-dependency-promotion.sh"
temp_dir="$(mktemp -d)"
trap 'rm -rf "$temp_dir"' EXIT

source_repo="$temp_dir/source"
target_repo="$temp_dir/target"
mkdir "$source_repo" "$target_repo"
git -C "$source_repo" init -q
git -C "$target_repo" init -q
git -C "$source_repo" config user.name test
git -C "$source_repo" config user.email test@example.com
git -C "$target_repo" config user.name test
git -C "$target_repo" config user.email test@example.com

mkdir -p "$source_repo/.github/workflows" "$target_repo/.github/workflows"
cat > "$source_repo/.github/workflows/ci.yml" <<'EOF'
name: CI
on:
  push:
    branches:
      - main
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v1
      - run: echo test
EOF
cp "$source_repo/.github/workflows/ci.yml" "$target_repo/.github/workflows/ci.yml"
git -C "$source_repo" add .
git -C "$source_repo" commit -qm base
base_commit="$(git -C "$source_repo" rev-parse HEAD)"
git -C "$target_repo" add .
git -C "$target_repo" commit -qm stable

sed -i '1i# stable-only setting' "$target_repo/.github/workflows/ci.yml"
git -C "$target_repo" add .
git -C "$target_repo" commit -qm stable-only-setting

cat > "$source_repo/.github/workflows/ci.yml" <<'EOF'
name: CI
on:
  push:
    branches:
      - main
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - run: echo test
EOF
git -C "$source_repo" add .
git -C "$source_repo" commit -qm dependency-update
merge_commit="$(git -C "$source_repo" rev-parse HEAD)"

bash "$script" "$source_repo" "$target_repo" "$merge_commit" ".github/workflows/"
grep -q '^# stable-only setting$' "$target_repo/.github/workflows/ci.yml"
grep -q 'uses: actions/checkout@v2' "$target_repo/.github/workflows/ci.yml"
git -C "$target_repo" add .
git -C "$target_repo" commit -qm promoted

cat > "$target_repo/.github/workflows/ci.yml" <<'EOF'
name: CI
on:
  push:
    branches:
      - main
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - run: echo test
# stable-only setting
EOF
git -C "$target_repo" add .
git -C "$target_repo" commit -qm conflicting-stable-change
if bash "$script" "$source_repo" "$target_repo" "$merge_commit" ".github/workflows/" >/dev/null 2>&1; then
  echo "Expected conflicting dependency changes to fail." >&2
  exit 1
fi

if bash "$script" "$source_repo" "$target_repo" "$merge_commit" "../" >/dev/null 2>&1; then
  echo "Expected unsupported pathspec to fail." >&2
  exit 1
fi

if bash "$script" "$source_repo" "$target_repo" "$base_commit" "dockerfile" >/dev/null 2>&1; then
  echo "Expected a promotion without changes in the selected path to fail." >&2
  exit 1
fi
