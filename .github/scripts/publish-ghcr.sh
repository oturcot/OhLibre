#!/usr/bin/env bash
set -euo pipefail

image="$1"
version="$2"
archives="$3"
[[ "$image" =~ ^ghcr\.io/[a-z0-9][a-z0-9-]*/radio-canada-podcast$ ]]
[[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+(-beta\.[0-9]+)?$ ]]
repository="${image#ghcr.io/}"

reply="$(mktemp)"
trap 'rm -f "$reply"' EXIT
status="$(curl --silent --show-error --max-time 30 --output "$reply" --write-out '%{http_code}' \
    --get https://ghcr.io/token --data-urlencode service=ghcr.io \
    --data-urlencode "scope=repository:$repository:pull")"
if [[ "$status" == 200 ]]; then
    anonymous="$(jq -er '.token // .access_token' "$reply")"
    status="$(curl --silent --show-error --max-time 30 --output "$reply" --write-out '%{http_code}' \
        --header "Authorization: Bearer $anonymous" "https://ghcr.io/v2/$repository/tags/list")"
fi
case "$status" in
    401|403) ;;
    200) echo "Refusing to publish: $image is publicly readable." >&2; exit 1 ;;
    *) echo "Could not verify anonymous access to $image (HTTP $status)." >&2; exit 1 ;;
esac

sources=()
for arch in amd64 arm64; do
    docker image load --platform "linux/$arch" -i "$archives/radio-canada-podcast-linux-$arch.tar.gz"
    tagged="$image:$version-$arch"
    docker image tag radio-canada-podcast:local "$tagged"
    docker image push --platform "linux/$arch" "$tagged"
    sources+=("$tagged")
    docker image rm "$tagged" radio-canada-podcast:local
done

channel=latest
if [[ "$version" == *-beta.* ]]; then
    channel=beta
fi
docker buildx imagetools create --tag "$image:$version" --tag "$image:$channel" "${sources[@]}"
docker buildx imagetools inspect --raw "$image:$version" | jq -e \
    '[.manifests[].platform | select(.os == "linux") | .architecture] | sort == ["amd64","arm64"]'
