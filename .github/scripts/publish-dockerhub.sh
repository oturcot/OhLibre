#!/usr/bin/env bash
set -euo pipefail

image="$1"
version="$2"
archives="$3"
current_channel_version="${4:-}"
[[ "$image" =~ ^[a-z0-9][a-z0-9_-]*/ohlibre$ ]]
[[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+(-beta\.[0-9]+)?$ ]]
[[ -z "$current_channel_version" || "$current_channel_version" =~ ^[0-9]+\.[0-9]+\.[0-9]+(-beta\.[0-9]+)?$ ]]
reply="$(mktemp)"
trap 'rm -f "$reply"' EXIT

sources=()
for arch in amd64 arm64; do
    docker image load --platform "linux/$arch" -i "$archives/ohlibre-linux-$arch.tar.gz"
    tagged="$image:$version-$arch"
    docker image tag ohlibre:local "$tagged"
    docker image push --platform "linux/$arch" "$tagged"
    sources+=("$tagged")
    docker image rm "$tagged" ohlibre:local
done

channel=latest
if [[ "$version" == *-beta.* ]]; then
    channel=beta
fi
if channel_manifest="$(docker buildx imagetools inspect --raw "$image:$channel" 2>"$reply")"; then
    annotated_version="$(jq -r '.annotations["org.opencontainers.image.version"] // empty' <<< "$channel_manifest")"
    if [[ -n "$annotated_version" ]]; then
        current_channel_version="$annotated_version"
    fi
else
    if ! grep -Eqi 'manifest unknown|not found|no such manifest' "$reply"; then
        cat "$reply" >&2
        echo "Could not inspect the $channel channel." >&2
        exit 1
    fi
fi
tags=("$image:$version")
if [[ -z "$current_channel_version" ]] || {
    [[ "$current_channel_version" != "$version" ]] &&
    [[ "$(printf '%s\n%s\n' "$current_channel_version" "$version" | sort -V | tail -n 1)" == "$version" ]]
}; then
    tags+=("$image:$channel")
else
    echo "Keeping $channel at version $current_channel_version; not moving it to $version."
fi
tag_args=()
for tag in "${tags[@]}"; do
    tag_args+=(--tag "$tag")
done
docker buildx imagetools create --annotation "index:org.opencontainers.image.version=$version" \
    "${tag_args[@]}" "${sources[@]}"
docker buildx imagetools inspect --raw "$image:$version" | jq -e \
    '[.manifests[].platform | select(.os == "linux") | .architecture] | sort == ["amd64","arm64"]'
anonymous="$(curl --fail --silent --show-error --max-time 30 \
    --get https://auth.docker.io/token --data-urlencode service=registry.docker.io \
    --data-urlencode "scope=repository:$image:pull" | jq -er '.token')"
curl --fail --silent --show-error --max-time 30 --output "$reply" \
    --header "Authorization: Bearer $anonymous" \
    --header 'Accept: application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json' \
    "https://registry-1.docker.io/v2/$image/manifests/$version" || {
    echo "Docker Hub image $image:$version is not anonymously readable; make the repository public." >&2
    exit 1
}
