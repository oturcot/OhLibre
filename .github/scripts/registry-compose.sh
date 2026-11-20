#!/usr/bin/env bash
set -euo pipefail

source_file="$1"
owner="$2"
tag="${3:-latest}"
[[ "$owner" =~ ^[a-z0-9][a-z0-9_-]*$ ]]
[[ "$tag" =~ ^[a-zA-Z0-9_][a-zA-Z0-9_.-]*$ ]]
sed -e 's|^    image: ohlibre:local$|    image: '"$owner"'/ohlibre:'"$tag"'|' \
    -e 's/^    pull_policy: never$/    pull_policy: always/' "$source_file"
