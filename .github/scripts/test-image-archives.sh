#!/usr/bin/env bash
set -euo pipefail

script="$(cd "$(dirname "$0")" && pwd)/image-archives.sh"
temp="$(mktemp -d)"
trap 'find "$temp" -depth -delete' EXIT
export RUNNER_WORKSPACE="$temp/workspace"
mkdir -p "$RUNNER_WORKSPACE"
sha=0123456789012345678901234567890123456789
other=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
printf 'amd64 image\n' > "$temp/amd64"
printf 'arm64 image\n' > "$temp/arm64"

archive() { bash "$script" "$@"; }
archive store 123 "$sha" amd64 "$temp/amd64"
if archive check 123 "$sha"; then
    echo "An incomplete run must not be publishable." >&2
    exit 1
fi
archive store 123 "$sha" arm64 "$temp/arm64"
archive check 123 "$sha"
if archive check 123 "$other"; then
    echo "Archives must match the commit." >&2
    exit 1
fi
archive copy 123 "$sha" "$temp/output"
cmp "$temp/amd64" "$temp/output/ohlibre-linux-amd64.tar.gz"
cmp "$temp/arm64" "$temp/output/ohlibre-linux-arm64.tar.gz"
printf 'changed\n' > "$temp/output/ohlibre-linux-amd64.tar.gz"
archive check 123 "$sha"

printf 'corrupt\n' > "$RUNNER_WORKSPACE/.ohlibre-image-archives/123/ohlibre-linux-arm64.tar.gz"
if archive copy 123 "$sha" "$temp/output"; then
    echo "Corrupt archives must not be published." >&2
    exit 1
fi
archive store 123 "$sha" arm64 "$temp/arm64"
archive check 123 "$sha"

touch -t 200001010000 "$RUNNER_WORKSPACE/.ohlibre-image-archives/123"
if archive check 123 "$sha"; then
    echo "Expired archives must not be published." >&2
    exit 1
fi
archive store 456 "$sha" amd64 "$temp/amd64"
test ! -e "$RUNNER_WORKSPACE/.ohlibre-image-archives/123"

archive store 789 "$sha" amd64 "$temp/amd64" &
first=$!
archive store 789 "$sha" arm64 "$temp/arm64" &
second=$!
wait "$first"
wait "$second"
archive check 789 "$sha"
echo "Image archive tests passed."
