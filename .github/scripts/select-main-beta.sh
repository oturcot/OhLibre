#!/usr/bin/env bash
set -euo pipefail

successful_runs="$1"
released_tags="$2"
declare -A successful=() released=() deferred=() pending=()

while read -r sha run_id; do
  [[ "$sha" =~ ^[0-9a-f]{40}$ && "$run_id" =~ ^[0-9]+$ ]]
  successful["$sha"]+="$run_id "
done < "$successful_runs"

while IFS= read -r tag; do
  if [[ "$tag" =~ ^[0-9]+\.[0-9]+\.[0-9]+-beta\.[0-9]+$ ]]; then
    sha="$(git rev-list -n 1 "refs/tags/$tag")"
    released["$sha"]=1
  fi
done < "$released_tags"

now="$(date +%s)"
while IFS= read -r tag; do
  if [[ "$tag" =~ ^beta-publish-pending-([0-9a-f]{40})$ ]]; then
    pending["${BASH_REMATCH[1]}"]=1
  fi
  if [[ "$tag" =~ ^beta-publish-retry-([0-9a-f]{40})-([0-9]{10})$ ]] &&
    (( now < BASH_REMATCH[2] + 3600 )); then
    deferred["${BASH_REMATCH[1]}"]=1
  fi
done < <(git for-each-ref --format='%(refname:strip=2)' 'refs/tags/beta-publish-*')

enabled=false
while IFS= read -r sha; do
  if [[ "$enabled" == false ]] &&
    git cat-file -e "$sha:.github/scripts/select-main-beta.sh" 2>/dev/null; then
    enabled=true
  fi
  if [[ "$enabled" == true && -n "${successful[$sha]:-}" &&
    ( -z "${released[$sha]:-}" || -n "${pending[$sha]:-}" ) &&
    -z "${deferred[$sha]:-}" ]]; then
    read -r -a run_ids <<< "${successful[$sha]}"
    for run_id in "${run_ids[@]}"; do
      artifacts="$(gh api --paginate "repos/$GITHUB_REPOSITORY/actions/runs/$run_id/artifacts?per_page=100" \
        --jq '.artifacts[] | select(.name == "tested-beta-image" and .expired == false) | .id')"
      if [[ -n "$artifacts" ]]; then
        printf '%s %s\n' "$sha" "$run_id"
        exit 0
      fi
    done
    echo "::warning::Skipping $sha: no retained tested-beta-image in successful main CI runs." >&2
  fi
done < <(git rev-list --first-parent --reverse HEAD)
