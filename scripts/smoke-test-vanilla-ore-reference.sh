#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "usage: $0 /path/to/NeverFolia.jar" >&2
  exit 2
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
JAR="$(realpath "$1")"
TEST_DIR="${ROOT_DIR}/vanilla-ore-reference-test"

SAMPLE_BLOCKS=(
  '0 0'
  '512 0'
  '-512 0'
  '0 512'
  '0 -512'
  '512 512'
  '-512 -512'
  '503 7'
  '-264 -398'
  '-60 -268'
)

rm -rf "${TEST_DIR}"
mkdir -p "${TEST_DIR}"
printf 'eula=true\n' > "${TEST_DIR}/eula.txt"
cat > "${TEST_DIR}/server.properties" <<'EOF'
level-name=world
level-seed=NeverOverworld-CI-Test-1
level-type=minecraft:normal
online-mode=false
enforce-secure-profile=false
server-port=25578
view-distance=2
simulation-distance=2
spawn-protection=0
max-tick-time=-1
enable-status=false
EOF

SERVER_PID=""; KEEPER_PID=""; PIPE_PATH=""
cleanup_server() {
  if [ -n "${SERVER_PID}" ]; then kill "${SERVER_PID}" 2>/dev/null || true; wait "${SERVER_PID}" 2>/dev/null || true; fi
  if [ -n "${KEEPER_PID}" ]; then kill "${KEEPER_PID}" 2>/dev/null || true; wait "${KEEPER_PID}" 2>/dev/null || true; fi
  if [ -n "${PIPE_PATH}" ]; then rm -f "${TEST_DIR}/${PIPE_PATH}"; fi
  SERVER_PID=""; KEEPER_PID=""; PIPE_PATH=""
}
trap cleanup_server EXIT

cd "${TEST_DIR}"
PIPE_PATH="console.pipe"
mkfifo "${PIPE_PATH}"
tail -f /dev/null > "${PIPE_PATH}" & KEEPER_PID=$!
java -Xms1G -Xmx2G -jar "${JAR}" nogui < "${PIPE_PATH}" > server.log 2>&1 & SERVER_PID=$!
cd "${ROOT_DIR}"

send_console() { printf '%s\n' "$1" > "${TEST_DIR}/${PIPE_PATH}"; }

for _ in $(seq 1 240); do
  if grep -q 'Done (' "${TEST_DIR}/server.log" 2>/dev/null; then break; fi
  if ! kill -0 "${SERVER_PID}" 2>/dev/null; then break; fi
  sleep 1
done
if ! grep -q 'Done (' "${TEST_DIR}/server.log" 2>/dev/null; then
  echo 'Vanilla ore reference server did not reach ready state.' >&2
  cat "${TEST_DIR}/server.log" >&2 || true
  exit 1
fi

sample_index=0
for coords in "${SAMPLE_BLOCKS[@]}"; do
  read -r x z <<< "${coords}"
  sample_index=$((sample_index + 1))
  token="VANILLA_ORE_REF_FULL_${sample_index}_${x}_${z}"
  send_console "execute in minecraft:overworld run forceload add ${x} ${z}"
  loaded=0
  for _ in $(seq 1 150); do
    send_console "execute in minecraft:overworld if loaded ${x} 0 ${z} run say ${token}"
    sleep 1
    if grep -Fq -- "${token}" "${TEST_DIR}/server.log" 2>/dev/null; then
      loaded=1
      break
    fi
    if ! kill -0 "${SERVER_PID}" 2>/dev/null; then break; fi
  done
  if [ "${loaded}" -ne 1 ]; then
    echo "Vanilla reference chunk did not reach loaded/FULL barrier: ${x},${z}" >&2
    cat "${TEST_DIR}/server.log" >&2 || true
    exit 1
  fi
done

sleep 3
send_console 'execute in minecraft:overworld run forceload remove all'
sleep 2
send_console 'stop'
for _ in $(seq 1 90); do
  if ! kill -0 "${SERVER_PID}" 2>/dev/null; then break; fi
  sleep 1
done
cleanup_server

LOG="${TEST_DIR}/server.log"
if grep -Eqi "Failed to parse|Couldn't parse|Unknown registry|Failed to load datapacks|Failed to load registries|NullPointerException|An unexpected error occurred while trying to execute that command|Unknown or incomplete command|Incorrect argument for command|Command exception" "${LOG}"; then
  echo 'Vanilla ore reference runtime/command error detected.' >&2
  cat "${LOG}" >&2
  exit 1
fi

if [ -d "${TEST_DIR}/world/region" ]; then
  echo "Vanilla reference region layout: ${TEST_DIR}/world/region"
elif [ -d "${TEST_DIR}/world/dimensions/minecraft/overworld/region" ]; then
  echo "Vanilla reference region layout: ${TEST_DIR}/world/dimensions/minecraft/overworld/region"
else
  echo 'Vanilla ore reference region directory missing in supported layouts.' >&2
  find "${TEST_DIR}/world" -maxdepth 6 -type d -name region -print >&2 || true
  exit 1
fi

echo '[NeverFolia][Vanilla ore reference] TRUE VANILLA 26.2 SAMPLE OK'
