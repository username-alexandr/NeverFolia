#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 2 ]; then
  echo "usage: $0 /path/to/NeverFolia.jar /path/to/NeverNether-Core.zip" >&2
  exit 2
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
JAR="$(realpath "$1")"
PACK="$(realpath "$2")"
TEST_ROOT="${ROOT_DIR}/determinism-test"

CHUNKS=(
  "8,8"
  "17,-11"
  "-23,19"
  "31,7"
  "-37,-29"
  "44,-16"
)
ORDER_A=("${CHUNKS[@]}")
ORDER_B=()
for ((i=${#CHUNKS[@]}-1; i>=0; i--)); do
  ORDER_B+=("${CHUNKS[$i]}")
done

cleanup_pid=""
cleanup_keeper=""
cleanup_pipe=""

cleanup_server() {
  if [ -n "${cleanup_pid}" ]; then
    kill "${cleanup_pid}" 2>/dev/null || true
    wait "${cleanup_pid}" 2>/dev/null || true
  fi
  if [ -n "${cleanup_keeper}" ]; then
    kill "${cleanup_keeper}" 2>/dev/null || true
    wait "${cleanup_keeper}" 2>/dev/null || true
  fi
  if [ -n "${cleanup_pipe}" ]; then
    rm -f "${cleanup_pipe}"
  fi
  cleanup_pid=""
  cleanup_keeper=""
  cleanup_pipe=""
}
trap cleanup_server EXIT

write_server_files() {
  local dir="$1"
  rm -rf "${dir}"
  mkdir -p "${dir}/world/datapacks"
  cp "${PACK}" "${dir}/world/datapacks/NeverNether-Core.zip"
  printf 'eula=true\n' > "${dir}/eula.txt"
  cat > "${dir}/server.properties" <<'EOF'
level-name=world
level-seed=NeverNether-CI-Determinism-1
level-type=minecraft:normal
initial-enabled-packs=vanilla,file/NeverNether-Core.zip
initial-disabled-packs=
online-mode=false
enforce-secure-profile=false
server-port=25576
view-distance=2
simulation-distance=2
spawn-protection=0
max-tick-time=-1
enable-status=false
EOF
}

wait_ready() {
  local log="$1"
  for _ in $(seq 1 180); do
    if grep -q 'Done (' "${log}" 2>/dev/null; then
      return 0
    fi
    if ! kill -0 "${cleanup_pid}" 2>/dev/null; then
      echo "NeverFolia exited before ready state: ${log}" >&2
      cat "${log}" >&2 || true
      return 1
    fi
    sleep 1
  done
  echo "NeverFolia did not reach ready state: ${log}" >&2
  cat "${log}" >&2 || true
  return 1
}

send_console() {
  printf '%s\n' "$1" > "${cleanup_pipe}"
}

wait_log_literal() {
  local log="$1"
  local literal="$2"
  local timeout_seconds="$3"
  local description="$4"
  for _ in $(seq 1 "${timeout_seconds}"); do
    if grep -Fq -- "${literal}" "${log}" 2>/dev/null; then
      return 0
    fi
    if ! kill -0 "${cleanup_pid}" 2>/dev/null; then
      echo "NeverFolia exited while waiting for ${description}: ${log}" >&2
      cat "${log}" >&2 || true
      return 1
    fi
    sleep 1
  done
  echo "Timed out waiting for ${description}: ${literal}" >&2
  cat "${log}" >&2 || true
  return 1
}

wait_chunk_full() {
  local log="$1"
  local bx="$2"
  local bz="$3"
  local token="$4"
  for _ in $(seq 1 120); do
    send_console "execute in minecraft:the_nether if loaded ${bx} 0 ${bz} run say ${token}"
    sleep 1
    if grep -Fq -- "${token}" "${log}" 2>/dev/null; then
      return 0
    fi
    if ! kill -0 "${cleanup_pid}" 2>/dev/null; then
      echo "NeverFolia exited while waiting for FULL status: ${token}" >&2
      cat "${log}" >&2 || true
      return 1
    fi
  done
  echo "Chunk did not reach FULL/Entity Ticking status: ${token}" >&2
  cat "${log}" >&2 || true
  return 1
}

generate_world() {
  local label="$1"
  shift
  local dir="${TEST_ROOT}/${label}"
  local log="${dir}/server.log"
  write_server_files "${dir}"
  cleanup_server

  cleanup_pipe="${dir}/console.pipe"
  mkfifo "${cleanup_pipe}"
  tail -f /dev/null > "${cleanup_pipe}" &
  cleanup_keeper=$!
  (
    cd "${dir}"
    java -Xms1G -Xmx2G -jar "${JAR}" nogui < "${cleanup_pipe}" > "${log}" 2>&1
  ) &
  cleanup_pid=$!
  wait_ready "${log}"

  send_console "execute in minecraft:the_nether run gamerule minecraft:random_tick_speed 0"
  wait_log_literal "${log}" "Gamerule random_tick_speed is now set to: 0" 10 "random tick isolation"

  local index=0
  local total="$#"
  for coord in "$@"; do
    IFS=',' read -r cx cz <<< "${coord}"
    index=$((index + 1))
    local bx=$((cx * 16 + 8))
    local bz=$((cz * 16 + 8))
    local marked="Marked chunk [${cx}, ${cz}] in minecraft:the_nether to be force loaded"
    local unmarked="Unmarked chunk [${cx}, ${cz}] in minecraft:the_nether for force loading"
    local token="NEVERNETHER_FULL_${label}_${index}_${cx}_${cz}"

    echo "[NeverFolia][NeverNether strict determinism] ${label} ${index}/${total}: ${cx},${cz}"
    send_console "execute in minecraft:the_nether run forceload add ${bx} ${bz}"
    wait_log_literal "${log}" "${marked}" 30 "forceload add ${cx},${cz}"
    wait_chunk_full "${log}" "${bx}" "${bz}" "${token}"
    send_console "execute in minecraft:the_nether run forceload remove ${bx} ${bz}"
    wait_log_literal "${log}" "${unmarked}" 30 "forceload remove ${cx},${cz}"
  done

  send_console "stop"
  for _ in $(seq 1 90); do
    if ! kill -0 "${cleanup_pid}" 2>/dev/null; then
      break
    fi
    sleep 1
  done
  cleanup_server

  if grep -Eqi "Failed to parse|Couldn't parse|Unknown registry|Errors in currently selected datapacks|Failed to load datapacks|Failed to load registries|worldgen fingerprint mismatch|NullPointerException|An unexpected error occurred while trying to execute that command|Unknown or incomplete command|Incorrect argument for command|Command exception" "${log}"; then
    echo "NeverFolia strict determinism world ${label} contains startup/worldgen/command errors." >&2
    cat "${log}" >&2
    exit 1
  fi

  local marked_count
  local unmarked_count
  marked_count="$(grep -c 'Marked chunk \[' "${log}" || true)"
  unmarked_count="$(grep -c 'Unmarked chunk \[' "${log}" || true)"
  if [ "${marked_count}" -ne "${total}" ] || [ "${unmarked_count}" -ne "${total}" ]; then
    echo "Strict determinism world ${label} missed forceload commands: marked=${marked_count}/${total}, unmarked=${unmarked_count}/${total}" >&2
    cat "${log}" >&2
    exit 1
  fi
}

rm -rf "${TEST_ROOT}"
mkdir -p "${TEST_ROOT}"

echo '[NeverFolia][NeverNether strict determinism] generating world A in forward order'
generate_world "world-a" "${ORDER_A[@]}"
echo '[NeverFolia][NeverNether strict determinism] generating world B in reverse order'
generate_world "world-b" "${ORDER_B[@]}"

HASH_ARGS=()
for coord in "${CHUNKS[@]}"; do
  HASH_ARGS+=("--chunk=${coord}")
done

python3 "${ROOT_DIR}/scripts/hash-never-nether-generation-chunks.py" \
  --world "${TEST_ROOT}/world-a/world" \
  "${HASH_ARGS[@]}" \
  --output "${TEST_ROOT}/world-a-hash.json" \
  > "${TEST_ROOT}/world-a-hash.stdout.json"
python3 "${ROOT_DIR}/scripts/hash-never-nether-generation-chunks.py" \
  --world "${TEST_ROOT}/world-b/world" \
  "${HASH_ARGS[@]}" \
  --output "${TEST_ROOT}/world-b-hash.json" \
  > "${TEST_ROOT}/world-b-hash.stdout.json"

set +e
python3 - "${TEST_ROOT}/world-a-hash.json" "${TEST_ROOT}/world-b-hash.json" <<'PY'
import json
import sys
from pathlib import Path

a = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
b = json.loads(Path(sys.argv[2]).read_text(encoding='utf-8'))
if a['algorithm'] != b['algorithm']:
    raise SystemExit(f"determinism algorithm mismatch: {a['algorithm']} != {b['algorithm']}")
if a['chunks'] != b['chunks']:
    by_a = {(x['x'], x['z']): x['sha256'] for x in a['chunks']}
    by_b = {(x['x'], x['z']): x['sha256'] for x in b['chunks']}
    lines = ['NeverNether strict chunk-order generation mismatch:']
    for key in sorted(set(by_a) | set(by_b)):
        if by_a.get(key) != by_b.get(key):
            lines.append(f"  chunk {key[0]},{key[1]}: {by_a.get(key)} != {by_b.get(key)}")
    raise SystemExit('\n'.join(lines))
if a['overall_sha256'] != b['overall_sha256']:
    raise SystemExit(f"NeverNether strict overall hash mismatch: {a['overall_sha256']} != {b['overall_sha256']}")
print('[NeverFolia][NeverNether strict determinism] ORDER-INDEPENDENCE OK')
print('  algorithm:', a['algorithm'])
print('  chunks:', a['chunk_count'])
print('  canonical_sha256:', a['overall_sha256'])
PY
COMPARE_RC=$?
set -e

if [ "${COMPARE_RC}" -ne 0 ]; then
  python3 "${ROOT_DIR}/scripts/diff-never-nether-chunks.py" \
    --world-a "${TEST_ROOT}/world-a/world" \
    --world-b "${TEST_ROOT}/world-b/world" \
    "${HASH_ARGS[@]}" \
    --output "${TEST_ROOT}/component-diff.json" \
    --allow-differences
  exit "${COMPARE_RC}"
fi
