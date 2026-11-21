#!/usr/bin/env bash
set -euo pipefail

operation="$1"
run_id="$2"
sha="$3"
[[ "$run_id" =~ ^[0-9]+$ ]]
[[ "$sha" =~ ^[0-9a-f]{40}$ ]]
root="${RUNNER_WORKSPACE:?}/.ohlibre-image-archives"
mkdir -p "$root"
exec 9>"$root/.lock"
flock -x 9

dir="$root/$run_id"
validate() {
    [[ -d "$dir" ]] || return 1
    [[ -z "$(find "$dir" -maxdepth 0 -mtime +6 -print)" ]] || return 1
    for arch in amd64 arm64; do
        [[ -f "$dir/$arch.sha" && "$(cat "$dir/$arch.sha")" == "$sha" ]] || return 1
        (cd "$dir" && sha256sum --status -c "$arch.sha256") || return 1
    done
}

case "$operation" in
    store)
        arch="$4"
        archive="$5"
        [[ "$arch" == amd64 || "$arch" == arm64 ]]
        [[ -f "$archive" ]]
        mkdir -p "$dir"
        name="ohlibre-linux-$arch.tar.gz"
        cp "$archive" "$dir/$name.tmp"
        mv -f "$dir/$name.tmp" "$dir/$name"
        (cd "$dir" && sha256sum "$name" > "$arch.sha256.tmp")
        mv -f "$dir/$arch.sha256.tmp" "$dir/$arch.sha256"
        printf '%s\n' "$sha" > "$dir/$arch.sha.tmp"
        mv -f "$dir/$arch.sha.tmp" "$dir/$arch.sha"
        touch "$dir"
        while IFS= read -r expired; do
            [[ "${expired##*/}" =~ ^[0-9]+$ ]] || continue
            find "$expired" -mindepth 1 -maxdepth 1 -type f -delete
            rmdir "$expired"
        done < <(find "$root" -mindepth 1 -maxdepth 1 -type d -mtime +6 -print)
        ;;
    check)
        validate
        ;;
    copy)
        destination="$4"
        if ! validate; then
            echo "Tested image archives for run $run_id and commit $sha are missing, expired or corrupt." >&2
            exit 1
        fi
        mkdir -p "$destination"
        for arch in amd64 arm64; do
            cp "$dir/ohlibre-linux-$arch.tar.gz" "$destination/"
        done
        ;;
    *)
        echo "Unknown image archive operation: $operation" >&2
        exit 1
        ;;
esac
