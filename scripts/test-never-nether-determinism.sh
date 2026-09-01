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

  cat > "${dir}/eula.txt" <<'EOF'
eula=true
EOF

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
  local command="$1"
  printf '%s\n' "${command}" > "${cleanup_pipe}"
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
  local cx="$2"
  local cz="$3"
  local bx="$4"
  local bz="$5"
  local token="NEVERNETHER_FULL_${cx}_${cz}"

  # `execute if loaded` only succeeds once the addressed chunk is fully loaded
  # (Entity Ticking). Polling this condition makes FULL status the barrier instead
  # of assuming that a fixed wall-clock sleep is enough for Folia's async pipeline.
  for _ in $(seq 1 120); do
    send_console "execute in minecraft:the_nether if loaded ${bx} 0 ${bz} run say ${token}"
    if wait_log_literal "${log}" "${token}" 1 "chunk ${cx},${cz} FULL status"; then
      return 0
    fi
    if ! kill -0 "${cleanup_pid}" 2>/dev/null; then
      echo "NeverFolia exited while waiting for chunk ${cx},${cz} FULL status." >&2
      cat "${log}" >&2 || true
      return 1
    fi
  done

  echo "Chunk ${cx},${cz} did not reach FULL/Entity Ticking status." >&2
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

  # Determinism here is about world generation, not about how long an already
  # generated chunk happened to receive random block ticks while the harness
  # waited for other chunks. Disable random ticking before touching the Nether.
  send_console "gamerule randomTickSpeed 0"

  local index=0
  local total="$#"
  for coord in "$@"; do
    IFS=',' read -r cx cz <<< "${coord}"
    local bx=$((cx * 16 + 8))
    local bz=$((cz * 16 + 8))
    local marked="Marked chunk [${cx}, ${cz}] in minecraft:the_nether to be force loaded"
    local unmarked="Unmarked chunk [${cx}, ${cz}] in minecraft:the_nether for force loading"
    index=$((index + 1))

    echo "[NeverFolia][NeverNether determinism] ${label} ${index}/${total}: chunk ${cx},${cz}"
    send_console "execute in minecraft:the_nether run forceload add ${bx} ${bz}"
    wait_log_literal "${log}" "${marked}" 30 "forceload add for chunk ${cx},${cz}"
    wait_chunk_full "${log}" "${cx}" "${cz}" "${bx}" "${bz}"
    send_console "execute in minecraft:the_nether run forceload remove ${bx} ${bz}"
    wait_log_literal "${log}" "${unmarked}" 30 "forceload remove for chunk ${cx},${cz}"
  done

  # Folia 26.2 has no global save-all command. The normal stop path is the only
  # explicit persistence barrier: it halts chunk systems, saves every world and
  # waits for RegionFile I/O before the process exits.
  send_console "stop"

  for _ in $(seq 1 60); do
    if ! kill -0 "${cleanup_pid}" 2>/dev/null; then
      break
    fi
    sleep 1
  done
  cleanup_server

  if ! grep -q 'Done (' "${log}"; then
    echo "NeverFolia determinism world ${label} never reached ready state." >&2
    cat "${log}" >&2
    exit 1
  fi
  if grep -Eqi "Failed to parse|Couldn't parse|Unknown registry|Errors in currently selected datapacks|Failed to load datapacks|Failed to load registries|worldgen fingerprint mismatch|NullPointerException|An unexpected error occurred while trying to execute that command|Unknown or incomplete command|Command exception" "${log}"; then
    echo "NeverFolia determinism world ${label} contains startup/worldgen/command errors." >&2
    cat "${log}" >&2
    exit 1
  fi

  local marked_count
  local unmarked_count
  marked_count="$(grep -c 'Marked chunk \[' "${log}" || true)"
  unmarked_count="$(grep -c 'Unmarked chunk \[' "${log}" || true)"
  if [ "${marked_count}" -ne "${total}" ] || [ "${unmarked_count}" -ne "${total}" ]; then
    echo "NeverFolia determinism world ${label} did not execute every forceload command: marked=${marked_count}/${total}, unmarked=${unmarked_count}/${total}" >&2
    cat "${log}" >&2
    exit 1
  fi
}

rm -rf "${TEST_ROOT}"
mkdir -p "${TEST_ROOT}"

echo '[NeverFolia][NeverNether determinism] generating world A in forward order'
generate_world "world-a" "${ORDER_A[@]}"

echo '[NeverFolia][NeverNether determinism] generating world B in reverse order'
generate_world "world-b" "${ORDER_B[@]}"

HASH_ARGS=()
for coord in "${CHUNKS[@]}"; do
  HASH_ARGS+=("--chunk=${coord}")
done

python3 "${ROOT_DIR}/scripts/hash-never-nether-chunks.py" \
  --world "${TEST_ROOT}/world-a/world" \
  "${HASH_ARGS[@]}" \
  --output "${TEST_ROOT}/world-a-hash.json" \
  > "${TEST_ROOT}/world-a-hash.stdout.json"

python3 "${ROOT_DIR}/scripts/hash-never-nether-chunks.py" \
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
    lines = ['NeverNether chunk-order determinism mismatch:']
    for key in sorted(set(by_a) | set(by_b)):
        if by_a.get(key) != by_b.get(key):
            lines.append(f"  chunk {key[0]},{key[1]}: {by_a.get(key)} != {by_b.get(key)}")
    raise SystemExit('\n'.join(lines))
if a['overall_sha256'] != b['overall_sha256']:
    raise SystemExit(
        f"NeverNether overall canonical hash mismatch: "
        f"{a['overall_sha256']} != {b['overall_sha256']}"
    )

print('[NeverFolia][NeverNether determinism] ORDER-INDEPENDENCE OK')
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
