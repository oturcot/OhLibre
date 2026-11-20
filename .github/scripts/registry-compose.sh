#!/usr/bin/env bash
set -euo pipefail

source_file="$1"
owner="$2"
[[ "$owner" =~ ^[a-z0-9][a-z0-9_-]*$ ]]
sed -e 's|^    image: ohlibre:local$|    image: '"$owner"'/ohlibre:${OHDIO_TAG:-latest}|' \
    -e 's/^    pull_policy: never$/    pull_policy: always/' "$source_file"
