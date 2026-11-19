#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
temp_dir="$(mktemp -d)"
trap 'rm -rf "$temp_dir"' EXIT
mkdir -p "$temp_dir/bin" "$temp_dir/ios" "$temp_dir/license"
mkdir -p "$temp_dir/networks"
touch "$temp_dir/ios/iol.bin" "$temp_dir/license/CiscoIOUKeygen3f.py"

cat > "$temp_dir/bin/docker" <<'EOF'
#!/usr/bin/env bash
set -eu
printf '%s\n' "$*" >> "$DOCKER_LOG"
case "${1:-} ${2:-}" in
  "network create")
    [[ "$*" != *"--subnet"* && "$*" != *"--gateway"* ]] || exit 1
    if [[ "${FAIL_SECOND_NETWORK:-false}" == true && "${*: -1}" == *-network-b ]]; then
      exit 1
    fi
    if [[ "$*" == *"--label io.cisco-iol.cisco-l3-test.owner="* ]]; then
      network_name="${*: -1}"
      printf '%s\n' "$6" > "$NETWORK_STATE_DIR/$network_name"
    else
      exit 1
    fi
    if [[ "${INTERRUPT_DURING_CREATE:-false}" == true && "$network_name" == *-network-a ]]; then
      kill -TERM "$PPID"
      sleep 0.1
      exit 0
    fi
    ;;
  "network inspect")
    if [[ "$*" == *"Labels"* ]]; then
      network_name="${*: -1}"
      if [[ -f "$NETWORK_STATE_DIR/$network_name" ]]; then
        echo "${network_name%-network-*}"
      else
        exit 1
      fi
    elif [[ "${*: -1}" == *-network-a ]]; then
      if [[ "${SMALL_NETWORK:-false}" == true ]]; then
        echo "172.20.0.0/30 172.20.0.1"
      else
        echo "172.20.0.0/16 172.20.0.1"
      fi
    else
      echo "192.168.42.0/24 192.168.42.254"
    fi
    ;;
  "network ls")
    expected_label="${4#label=}"
    for network_file in "$NETWORK_STATE_DIR"/*; do
      [[ -f "$network_file" ]] || continue
      if [[ "$(cat "$network_file")" == "$expected_label" ]]; then
        basename "$network_file"
      fi
    done
    ;;
  "network rm")
    rm -f "$NETWORK_STATE_DIR/${*: -1}"
    ;;
  "inspect --format")
    case "$3 $4" in
      *-network-a*router) echo "172.20.0.2" ;;
      *-network-a*client-a) echo "172.20.0.3" ;;
      *-network-b*router) echo "192.168.42.1" ;;
      *-network-b*client-b) echo "192.168.42.2" ;;
      *) exit 1 ;;
    esac
    ;;
  "compose --project-name")
    if [[ " $* " == *" ps -q "* ]]; then
      echo "${*: -1}"
    elif [[ " $* " == *" exec -T cisco-router sh -c "* ]]; then
      exit 42
    fi
    ;;
esac
EOF
chmod +x "$temp_dir/bin/docker"

export PATH="$temp_dir/bin:$PATH"
export IOS_IMAGE_DIR="$temp_dir/ios" IOS_LICENSE_DIR="$temp_dir/license" IOS_IMAGE_FILE=iol.bin
export DOCKER_LOG="$temp_dir/docker.log" NETWORK_STATE_DIR="$temp_dir/networks"
cd "$repo_root"

run_failure() {
  : > "$DOCKER_LOG"
  rm -f "$NETWORK_STATE_DIR"/*
  if bash "$repo_root/.github/scripts/test-cisco-compose.sh" >"$temp_dir/output" 2>&1; then
    echo "Expected integration test to fail" >&2
    exit 1
  fi
  grep -Eq '^network rm iol-test-.*-network-a$' "$DOCKER_LOG"
}

run_failure
grep -Fx 'Network A: 172.20.0.0/16, Cisco 172.20.0.4, client 172.20.0.3' "$temp_dir/output"
grep -Fx 'Network B: 192.168.42.0/24, Cisco 192.168.42.3, client 192.168.42.2' "$temp_dir/output"
grep -q '^compose .* down ' "$DOCKER_LOG"
grep -Eq '^network rm iol-test-.*-network-b$' "$DOCKER_LOG"

export FAIL_SECOND_NETWORK=true
run_failure
grep -Eq '^network rm iol-test-.*-network-a$' "$DOCKER_LOG"
if grep -Eq '^network rm .*network-b$' "$DOCKER_LOG"; then
  echo "Removed a network that was not created by this invocation" >&2
  exit 1
fi
if grep -q '^network inspect' "$DOCKER_LOG"; then
  echo "Unexpected network inspection after allocation failure" >&2
  exit 1
fi

unset FAIL_SECOND_NETWORK
export SMALL_NETWORK=true
run_failure
grep -F 'Docker network has too few usable addresses' "$temp_dir/output"
if grep -q '^compose .* exec -T cisco-router sh -c ' "$DOCKER_LOG"; then
  echo "Unexpected router configuration with undersized network" >&2
  exit 1
fi

unset SMALL_NETWORK
export INTERRUPT_DURING_CREATE=true
: > "$DOCKER_LOG"
rm -f "$NETWORK_STATE_DIR"/*
printf '%s=another-invocation\n' "io.cisco-iol.cisco-l3-test.owner" > "$NETWORK_STATE_DIR/unrelated-network"
if bash "$repo_root/.github/scripts/test-cisco-compose.sh" >"$temp_dir/output" 2>&1; then
  echo "Expected integration test to stop after SIGTERM" >&2
  exit 1
else
  status=$?
  if [[ "$status" != 143 ]]; then
    echo "Expected SIGTERM exit status 143, got $status" >&2
    exit 1
  fi
fi
grep -Eq '^network rm iol-test-.*-network-a$' "$DOCKER_LOG"
grep -Eq '^network ls --filter label=io\.cisco-iol\.cisco-l3-test\.owner=iol-test-.*--format \{\{\.Name\}\}$' "$DOCKER_LOG"
grep -Eq '^network create --driver bridge --label io\.cisco-iol\.cisco-l3-test\.owner=iol-test-.* iol-test-.*-network-a$' "$DOCKER_LOG"
if grep -Eq '^network rm .*network-b$' "$DOCKER_LOG"; then
  echo "Removed a network that was not created by this invocation" >&2
  exit 1
fi
if [[ ! -f "$NETWORK_STATE_DIR/unrelated-network" ]]; then
  echo "Removed a network owned by another invocation" >&2
  exit 1
fi
