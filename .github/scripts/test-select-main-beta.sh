#!/usr/bin/env bash
set -euo pipefail

script="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/select-main-beta.sh"
reservation_script="$(dirname "$script")/find-reserved-beta-tag.sh"
temp_dir="$(mktemp -d)"
trap 'rm -rf "$temp_dir"' EXIT
cd "$temp_dir"
mkdir -p bin artifacts
cat > bin/gh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
[[ "$1" == api && "$2" == --paginate && "$4" == --jq ]]
run_id="${3##*/runs/}"
run_id="${run_id%%/*}"
[[ "$run_id" =~ ^[0-9]+$ ]]
if [[ -f "$TEST_ARTIFACTS/$run_id.error" ]]; then
  exit 1
elif [[ -f "$TEST_ARTIFACTS/$run_id.json" ]]; then
  jq -r "$5" "$TEST_ARTIFACTS/$run_id.json"
else
  printf '%s\n' '{"artifacts":[{"id":1,"name":"tested-beta-image","expired":false}]}' | jq -r "$5"
fi
EOF
chmod +x bin/gh
export PATH="$temp_dir/bin:$PATH" TEST_ARTIFACTS="$temp_dir/artifacts" GITHUB_REPOSITORY="test/repo"
next_run=0
add_success() {
  next_run=$((next_run + 1))
  printf '%s %s\n' "$1" "$next_run" >> successful
}
git init -q
git config user.name "Test"
git config user.email "test@example.invalid"
git commit -q --allow-empty -m before-dispatcher
old_sha="$(git rev-parse HEAD)"
mkdir -p .github/scripts
touch .github/scripts/select-main-beta.sh
git add .github/scripts/select-main-beta.sh
git commit -q -m enable-dispatcher
first_sha="$(git rev-parse HEAD)"
: > successful
add_success "$old_sha"
add_success "$first_sha"
: > releases

assert_selected() {
  local actual
  actual="$(bash "$script" successful releases)"
  if [[ "$actual" != "$1" ]]; then
    echo "Expected '$1', got '$actual'." >&2
    exit 1
  fi
}

assert_selected "$first_sha 2"
git tag 0.1.0-beta.0 "$first_sha"
echo 0.1.0-beta.0 >> releases
assert_selected ""
git tag "beta-publish-pending-$first_sha" "$first_sha"
assert_selected "$first_sha 2"
retry_tag="beta-publish-retry-$first_sha-$(date +%s)"
git tag "$retry_tag" "$first_sha"
assert_selected ""
git tag -d "beta-publish-pending-$first_sha" "$retry_tag" >/dev/null

for i in {1..105}; do
  git commit -q --allow-empty -m "merge-$i"
  sha="$(git rev-parse HEAD)"
  add_success "$sha"
  if (( i <= 104 )); then
    git tag "0.1.0-beta.$i" "$sha"
    echo "0.1.0-beta.$i" >> releases
  fi
done
last_sha="$sha"
assert_selected "$last_sha $next_run"

git commit -q --allow-empty -m untested
assert_selected "$last_sha $next_run"
git tag -a 0.1.0-beta.105 "$last_sha" -m released
echo 0.1.0-beta.105 >> releases
assert_selected ""

failed_sha="$(git rev-parse HEAD)"
add_success "$failed_sha"
failed_run="$next_run"
assert_selected "$failed_sha $failed_run"
now="$(date +%s)"
git tag "beta-publish-retry-$failed_sha-$now" "$failed_sha"
git commit -q --allow-empty -m later-merge
later_sha="$(git rev-parse HEAD)"
add_success "$later_sha"
later_run="$next_run"
assert_selected "$later_sha $later_run"
git tag -d "beta-publish-retry-$failed_sha-$now" >/dev/null
git tag "beta-publish-retry-$failed_sha-$((now - 3601))" "$failed_sha"
assert_selected "$failed_sha $failed_run"

printf '%s\n' '{"artifacts":[{"id":1,"name":"tested-beta-image","expired":true},{"id":2,"name":"other","expired":false}]}' > "artifacts/$failed_run.json"
assert_selected "$later_sha $later_run"
printf '%s\n' '{"artifacts":[]}' > "artifacts/$later_run.json"
assert_selected ""

add_success "$failed_sha"
alternate_run="$next_run"
assert_selected "$failed_sha $alternate_run"
touch "artifacts/$failed_run.error"
if bash "$script" successful releases >/dev/null 2>&1; then
  echo "Expected artifact API failure to fail selection." >&2
  exit 1
fi
rm "artifacts/$failed_run.error"

printf '%s\n' '{"artifacts":[{"id":3,"name":"tested-beta-image","expired":false}]}' > "artifacts/$failed_run.json"
assert_selected "$failed_sha $failed_run"

git tag 0.1.0-beta.106 "$failed_sha"
git tag -a 0.1.0-beta.107 "$failed_sha" -m reserved
[[ "$(bash "$reservation_script" "$failed_sha")" == 0.1.0-beta.107 ]]
[[ -z "$(bash "$reservation_script" "$(git rev-parse HEAD)")" ]]
