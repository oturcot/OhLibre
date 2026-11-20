#!/usr/bin/env bash
set -euo pipefail

version="$1"
arch="$2"
[[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+(-beta\.[0-9]+)?$ ]]
[[ "$arch" == amd64 || "$arch" == arm64 ]]
image=ohlibre:local
[[ "$(docker image inspect "$image" --format '{{.Os}}/{{.Architecture}}')" == "linux/$arch" ]]
container="$(docker create --platform "linux/$arch" "$image")"
trap 'docker rm "$container" >/dev/null' EXIT
[[ -z "$(docker diff "$container")" ]]
docker commit --change "ENV OHDIO_VERSION=$version" "$container" "$image" >/dev/null
docker image inspect "$image" --format '{{json .Config.Env}}' | jq -e \
  --arg expected "OHDIO_VERSION=$version" 'any(.[]; . == $expected)' >/dev/null
