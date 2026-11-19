#!/usr/bin/env bash
set -euo pipefail

: "${IOS_IMAGE_DIR:?Set IOS_IMAGE_DIR to the directory containing the Cisco IOS image}"
: "${IOS_LICENSE_DIR:?Set IOS_LICENSE_DIR to the directory containing CiscoIOUKeygen3f.py}"

ios_image_file="${IOS_IMAGE_FILE:-i86bi_linux-adventerprisek9-ms.155-2.T.bin}"
if [[ "$ios_image_file" == */* || ! -f "$IOS_IMAGE_DIR/$ios_image_file" ]]; then
  echo "Missing or invalid Cisco IOS image: $IOS_IMAGE_DIR/$ios_image_file" >&2
  exit 1
fi
if [[ ! -f "$IOS_LICENSE_DIR/CiscoIOUKeygen3f.py" ]]; then
  echo "Missing Cisco license key generator: $IOS_LICENSE_DIR/CiscoIOUKeygen3f.py" >&2
  exit 1
fi

docker info

project="iol-test-${GITHUB_RUN_ID:-local}-$(date +%s)-$$"
network_a="${project}-network-a"
network_b="${project}-network-b"
network_owner_label="io.cisco-iol.cisco-l3-test.owner"
network_owner="$project"
base_image="${IOL_BASE_IMAGE_TAG:-cisco-iol/${project}-base:local}"
test_image="cisco-iol/${project}-with-assets:local"
router_console_stream_pid=""
compose_files=(-f .github/docker-compose.l3-test.yml)
compose=(docker compose --project-name "$project" "${compose_files[@]}")
debian_image="${DEBIAN_BASE_IMAGE:-$(sed -nE 's/^ARG DEBIAN_BASE_IMAGE=(.*)$/\1/p' dockerfile)}"
ubridge_ref="${UBRIDGE_REF:-$(sed -nE 's/^ARG UBRIDGE_REF=(.*)$/\1/p' dockerfile)}"

stop_router_console_stream() {
  if [[ -n "$router_console_stream_pid" ]]; then
    kill "$router_console_stream_pid" 2>/dev/null || true
    wait "$router_console_stream_pid" 2>/dev/null || true
    router_console_stream_pid=""
  fi
}

cleanup() {
  local status=$?
  trap - EXIT
  stop_router_console_stream

  if (( status != 0 )); then
    echo "Cisco Layer 3 integration test failed; collecting router diagnostics." >&2
    "${compose[@]}" ps >&2 || true
    "${compose[@]}" logs --no-color >&2 || true
    "${compose[@]}" exec -T cisco-router tmux capture-pane -p -S -2000 -t iol:0.0 >&2 || true
  fi

  "${compose[@]}" down --volumes --remove-orphans || true
  owned_networks="$(docker network ls \
    --filter "label=$network_owner_label=$network_owner" --format '{{.Name}}' || true)"
  while IFS= read -r network; do
    [[ -n "$network" ]] && docker network rm "$network" >/dev/null 2>&1 || true
  done <<<"$owned_networks"
  if [[ "${PRESERVE_BASE_IMAGE:-false}" == "true" && "$status" == "0" ]]; then
    docker image rm "$test_image" >/dev/null 2>&1 || true
  else
    docker image rm "$test_image" "$base_image" >/dev/null 2>&1 || true
  fi
  return "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

export IOL_IMAGE_TAG="$base_image"
export L3_NETWORK_A="$network_a"
export L3_NETWORK_B="$network_b"

echo "Using Cisco IOS image: $IOS_IMAGE_DIR/$ios_image_file"

build_args=(docker buildx build --platform linux/amd64 --load --tag "$base_image" --file dockerfile)
build_args+=(
  --label "org.opencontainers.image.base.name=debian:stable"
  --label "org.opencontainers.image.base.digest=${debian_image##*@}"
  --label "org.opencontainers.image.ubridge.revision=$ubridge_ref"
)
if [[ -n "${DEBIAN_BASE_IMAGE:-}" ]]; then
  build_args+=(--build-arg "DEBIAN_BASE_IMAGE=$DEBIAN_BASE_IMAGE")
fi
if [[ -n "${UBRIDGE_REF:-}" ]]; then
  build_args+=(--build-arg "UBRIDGE_REF=$UBRIDGE_REF")
fi

echo "Building the Cisco router base image with plain BuildKit output."
"${build_args[@]}" .

echo "Building a private test image with the IOS image and license copied into it."
docker buildx build \
  --platform linux/amd64 \
  --load \
  --tag "$test_image" \
  --file Dockerfile.test \
  --build-context "ios_image=$IOS_IMAGE_DIR" \
  --build-context "ios_license=$IOS_LICENSE_DIR" \
  --build-arg "BASE_IMAGE=$base_image" \
  --build-arg "IOS_IMAGE_FILE=$ios_image_file" \
  .

echo "Creating isolated Docker networks for the Cisco L3 routing test."
docker network create --driver bridge --label "$network_owner_label=$network_owner" "$network_a"
docker network create --driver bridge --label "$network_owner_label=$network_owner" "$network_b"

export IOL_IMAGE_TAG="$test_image"
echo "Starting the Cisco router and two Alpine clients."
"${compose[@]}" up -d --wait --wait-timeout 180

network_addresses() {
  local network_info subnet gateway container_id container_ip client_id client_ip
  network_info="$(docker network inspect --format '{{(index .IPAM.Config 0).Subnet}} {{(index .IPAM.Config 0).Gateway}}' "$1")"
  read -r subnet gateway <<<"$network_info"
  container_id="$("${compose[@]}" ps -q cisco-router)"
  client_id="$("${compose[@]}" ps -q "$2")"
  container_ip="$(docker inspect --format "{{(index .NetworkSettings.Networks \"$1\").IPAddress}}" "$container_id")"
  client_ip="$(docker inspect --format "{{(index .NetworkSettings.Networks \"$1\").IPAddress}}" "$client_id")"
  python3 -c '
import ipaddress
import itertools
import sys

network = ipaddress.ip_network(sys.argv[1])
reserved = {ipaddress.ip_address(value) for value in sys.argv[2:]}
if network.version != 4 or len(reserved) != 3 or any(ip not in network for ip in reserved):
    sys.exit("Docker network must have distinct IPv4 gateway and container addresses")
addresses = list(itertools.islice((ip for ip in network.hosts() if ip not in reserved), 1))
if not addresses:
    sys.exit("Docker network has too few usable addresses")
print(network, network.netmask, addresses[0], sys.argv[4])
' "$subnet" "$gateway" "$container_ip" "$client_ip"
}

addresses_a="$(network_addresses "$network_a" alpine-client-a)"
addresses_b="$(network_addresses "$network_b" alpine-client-b)"
read -r subnet_a mask_a router_a client_a <<<"$addresses_a"
read -r subnet_b mask_b router_b client_b <<<"$addresses_b"
echo "Network A: $subnet_a, Cisco $router_a, client $client_a"
echo "Network B: $subnet_b, Cisco $router_b, client $client_b"

echo "Streaming the live Cisco IOS console to the GitHub Actions log."
"${compose[@]}" exec -T cisco-router sh -c \
  'tmux capture-pane -p -S -2000 -t iol:0.0 > /tmp/ios-console.log'
"${compose[@]}" exec -T cisco-router tmux pipe-pane -o -t iol:0.0 \
  'cat -v >> /tmp/ios-console.log'
"${compose[@]}" exec -T cisco-router tail -n +1 -F /tmp/ios-console.log &
router_console_stream_pid=$!

echo "Waiting for IOS to finish booting to its console."
router_console=""
router_console_log=""
initial_dialog_answered=0
autoinstall_answered=0
for attempt in {1..180}; do
  router_console="$("${compose[@]}" exec -T cisco-router tmux capture-pane -p -t iol:0.0 2>/dev/null || true)"
  if (( initial_dialog_answered == 0 )) &&
     grep -Eiq 'Would you like to enter the initial configuration dialog\? \[yes/no\]:' <<<"$router_console"; then
    "${compose[@]}" exec -T cisco-router tmux send-keys -t iol:0.0 no C-m
    initial_dialog_answered=1
  fi
  if (( autoinstall_answered == 0 )) &&
     grep -Eiq 'Would you like to terminate autoinstall\? \[yes\]:' <<<"$router_console"; then
    "${compose[@]}" exec -T cisco-router tmux send-keys -t iol:0.0 yes C-m
    autoinstall_answered=1
  fi
  if (( initial_dialog_answered == 1 && autoinstall_answered == 1 )); then
    router_console_log="$("${compose[@]}" exec -T cisco-router cat /tmp/ios-console.log 2>/dev/null || true)"
    if grep -Eiq 'press return to get started' <<<"$router_console$router_console_log"; then
      echo "Sending five Enter keystrokes to the IOS console."
      for enter_attempt in {1..5}; do
        "${compose[@]}" exec -T cisco-router tmux send-keys -t iol:0.0 C-m
        sleep 0.2
      done
      break
    fi
  fi
  if [[ -z "$("${compose[@]}" ps --status running -q cisco-router)" ]]; then
    echo "Cisco router container exited before IOS reached its CLI prompt." >&2
    break
  fi
  if (( attempt % 15 == 0 )); then
    echo "Still waiting for the IOS CLI prompt (attempt $attempt/180)."
  fi
  sleep 1
done
if (( initial_dialog_answered == 0 || autoinstall_answered == 0 )) ||
   ! grep -Eiq 'press return to get started' <<<"$router_console$router_console_log"; then
  echo "IOS did not reach the startup console prompt." >&2
  printf '%s\n' "$router_console" "$router_console_log" >&2
  exit 1
fi

echo "Configuring Cisco interfaces and enabling IPv4 routing."
send_router_command() {
  local command="$1"
  local expected_prompt="$2"
  local starting_size
  local response=""
  starting_size="$("${compose[@]}" exec -T cisco-router sh -c 'wc -c < /tmp/ios-console.log')"
  "${compose[@]}" exec -T cisco-router tmux send-keys -t iol:0.0 -l "$command"
  "${compose[@]}" exec -T cisco-router tmux send-keys -t iol:0.0 C-m
  for attempt in {1..30}; do
    response="$("${compose[@]}" exec -T cisco-router sh -c \
      "tail -c +$((starting_size + 1)) /tmp/ios-console.log" 2>/dev/null || true)"
    if awk -v command="$command" -v expected_prompt="$expected_prompt" '
      index($0, command) { command_seen = 1; next }
      command_seen && index($0, expected_prompt) { prompt_seen = 1 }
      END { exit !prompt_seen }
    ' <<<"$response"; then
      "${compose[@]}" exec -T cisco-router tmux capture-pane -p -S -20 -t iol:0.0
      return
    fi
    sleep 0.5
  done
  echo "Cisco did not return to the expected prompt after command: ${command}" >&2
  printf '%s\n' "$response" >&2
  return 1
}
send_router_command "enable" 'Router#'
send_router_command "configure terminal" 'Router(config)#'
send_router_command "hostname Router" 'Router(config)#'
send_router_command "ip routing" 'Router(config)#'
send_router_command "interface Ethernet0/0" 'Router(config-if)#'
send_router_command "ip address $router_a $mask_a" 'Router(config-if)#'
send_router_command "no shutdown" 'Router(config-if)#'
send_router_command "interface Ethernet0/1" 'Router(config-if)#'
send_router_command "ip address $router_b $mask_b" 'Router(config-if)#'
send_router_command "no shutdown" 'Router(config-if)#'
send_router_command "end" 'Router#'
send_router_command "terminal length 0" 'Router#'
sleep 2
router_console="$("${compose[@]}" exec -T cisco-router tmux capture-pane -p -S -2000 -t iol:0.0)"
echo "Cisco console output after sending the startup Enter keys and configuration:"
printf '%s\n' "$router_console"
if ! grep -Eq 'Router#' <<<"$router_console"; then
  echo "Cisco did not return to the privileged EXEC prompt after configuration." >&2
  exit 1
fi

echo "Configuring Alpine client addressing and Cisco default gateways."
"${compose[@]}" exec -T alpine-client-a sh -ec \
  "ip addr replace $client_a/${subnet_a#*/} dev eth0; ip route replace default via $router_a"
"${compose[@]}" exec -T alpine-client-b sh -ec \
  "ip addr replace $client_b/${subnet_b#*/} dev eth0; ip route replace default via $router_b"

echo "Checking that both clients have the expected addresses and routes."
"${compose[@]}" exec -T alpine-client-a sh -ec \
  "ip -4 -o addr show dev eth0 | grep -F '$client_a/${subnet_a#*/}'; ip route | grep -F 'default via $router_a'"
"${compose[@]}" exec -T alpine-client-b sh -ec \
  "ip -4 -o addr show dev eth0 | grep -F '$client_b/${subnet_b#*/}'; ip route | grep -F 'default via $router_b'"

echo "Waiting for Cisco interfaces to become operational."
interfaces=""
for attempt in {1..60}; do
  send_router_command "show ip interface brief" 'Router#'
  router_console="$("${compose[@]}" exec -T cisco-router tmux capture-pane -p -S -2000 -t iol:0.0)"
  if grep -Eq "Ethernet0/0[[:space:]]+${router_a//./\\.}.*up[[:space:]]+up" <<<"$router_console" &&
     grep -Eq "Ethernet0/1[[:space:]]+${router_b//./\\.}.*up[[:space:]]+up" <<<"$router_console"; then
    interfaces="ready"
    break
  fi
done
if [[ -z "$interfaces" ]]; then
  echo "Cisco interfaces did not become up/up." >&2
  exit 1
fi

echo "Checking that both Alpine clients can ping their Cisco gateways."
"${compose[@]}" exec -T alpine-client-a ping -c 3 -W 2 "$router_a"
"${compose[@]}" exec -T alpine-client-b ping -c 3 -W 2 "$router_b"

echo "Checking bidirectional routed connectivity between the two networks."
"${compose[@]}" exec -T alpine-client-a ping -c 5 -W 2 "$client_b"
"${compose[@]}" exec -T alpine-client-b ping -c 5 -W 2 "$client_a"

echo "Collecting Cisco routing table, interface status, and traffic counters."
send_router_command "show ip route" 'Router#'
send_router_command "show ip interface brief" 'Router#'
send_router_command "show interfaces Ethernet0/0" 'Router#'
send_router_command "show interfaces Ethernet0/1" 'Router#'
router_console="$("${compose[@]}" exec -T cisco-router tmux capture-pane -p -S -2000 -t iol:0.0)"
printf '%s\n' "$router_console"
grep -Eq "C[[:space:]]+${subnet_a//./\\.}.*directly connected" <<<"$router_console"
grep -Eq "C[[:space:]]+${subnet_b//./\\.}.*directly connected" <<<"$router_console"
grep -Eq "Ethernet0/0[[:space:]]+${router_a//./\\.}.*up[[:space:]]+up" <<<"$router_console"
grep -Eq "Ethernet0/1[[:space:]]+${router_b//./\\.}.*up[[:space:]]+up" <<<"$router_console"
input_counter_count="$(grep -Ec '[1-9][0-9]* packets input' <<<"$router_console" || true)"
output_counter_count="$(grep -Ec '[1-9][0-9]* packets output' <<<"$router_console" || true)"
if (( input_counter_count < 2 || output_counter_count < 2 )); then
  echo "Cisco interface input/output counters did not increase on both interfaces." >&2
  exit 1
fi

echo "Verifying inter-network traffic fails when the Cisco router is stopped."
"${compose[@]}" stop cisco-router
if "${compose[@]}" exec -T alpine-client-a ping -c 3 -W 1 "$client_b"; then
  echo "Inter-network ping unexpectedly succeeded after stopping the router." >&2
  exit 1
fi

echo "Cisco Layer 3 routing integration test passed."
