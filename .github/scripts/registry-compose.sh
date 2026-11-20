#!/usr/bin/env bash
set -euo pipefail

source_file="$1"
owner="$2"
[[ "$owner" =~ ^[a-z0-9][a-z0-9-]*$ ]]
sed -e 's|^    image: radio-canada-podcast:local$|    image: ghcr.io/'"$owner"'/radio-canada-podcast:${OHDIO_TAG:-latest}|' \
    -e 's/^    pull_policy: never$/    pull_policy: always/' "$source_file"
