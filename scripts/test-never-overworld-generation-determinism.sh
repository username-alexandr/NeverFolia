#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 2 ]; then
  echo "usage: $0 /path/to/NeverFolia.jar /path/to/NeverOverworld-Core.zip" >&2
  exit 2
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
JAR="$(realpath "$1")"
PACK="$(realpath "$2")"
TEST_ROOT="${ROOT_DIR}/overworld-determinism-test"
# Diagnostic mode: a single isolated target proves whether the mismatch is
# intrinsic run-to-run scheduling rather than interaction between sample halos.
CHUNKS=("64,64")
ORDER_A=("${CHUNKS[@]}")
ORDER_B=()
for ((i=${#CHUNKS[@]}-1; i>=0; i--)); do ORDER_B+=("${CHUNKS[$i]}"); done

cleanup_pid=""; cleanup_keeper=""; cleanup_pipe=""
cleanup_server() {
  if [ -n "${cleanup_pid}" ]; then kill "${cleanup_pid}" 2>/dev/null || true; wait "${cleanup_pid}" 2>/dev/null || true; fi
  if [ -n "${cleanup_keeper}" ]; then kill "${cleanup_keeper}" 2>/dev/null || true; wait "${cleanup_keeper}" 2>/dev/null || true; fi
  if [ -n "${cleanup_pipe}" ]; then rm -f "${cleanup_pipe}"; fi
  cleanup_pid=""; cleanup_keeper=""; cleanup_pipe=""
}
trap cleanup_server EXIT

write_server_files() {
  local dir="$1"
  rm -rf "${dir}"; mkdir -p "${dir}/world/datapacks"
  cp "${PACK}" "${dir}/world/datapacks/NeverOverworld-Core.zip"
  printf 'eula=true\n' > "${dir}/eula.txt"
  cat > "${dir}/server.properties" <<'EOF'
level-name=world
level-seed=NeverOverworld-CI-Determinism-1
level-type=minecraft:normal
initial-enabled-packs=vanilla,file/NeverOverworld-Core.zip
initial-disabled-packs=
online-mode=false
enforce-secure-profile=false
server-port=25578
view-distance=2
simulation-distance=2
spawn-protection=0
max-tick-time=-1
enable-status=false
EOF
}

send_console() { printf '%s\n' "$1" > "${cleanup_pipe}"; }
wait_ready() {
  local log="$1"
  for _ in $(seq 1 240); do
    if grep -q 'Done (' "${log}" 2>/dev/null; then return 0; fi
    if ! kill -0 "${cleanup_pid}" 2>/dev/null; then break; fi
    sleep 1
  done
  echo "NeverFolia exited or timed out before ready: ${log}" >&2; cat "${log}" >&2 || true; return 1
}
wait_literal() {
  local log="$1" literal="$2" timeout="$3" description="$4"
  for _ in $(seq 1 "${timeout}"); do
    if grep -Fq -- "${literal}" "${log}" 2>/dev/null; then return 0; fi
    if ! kill -0 "${cleanup_pid}" 2>/dev/null; then break; fi
    sleep 1
  done
  echo "Timed out waiting for ${description}: ${literal}" >&2; cat "${log}" >&2 || true; return 1
}
wait_chunk_full() {
  local log="$1" bx="$2" bz="$3" token="$4"
  for _ in $(seq 1 150); do
    send_console "execute in minecraft:overworld if loaded ${bx} 0 ${bz} run say ${token}"
    sleep 1
    if grep -Fq -- "${token}" "${log}" 2>/dev/null; then return 0; fi
    if ! kill -0 "${cleanup_pid}" 2>/dev/null; then break; fi
  done
  echo "Overworld chunk did not reach FULL: ${token}" >&2; cat "${log}" >&2 || true; return 1
}

generate_world() {
  local label="$1"; shift
  local dir="${TEST_ROOT}/${label}" log="${TEST_ROOT}/${label}/server.log"
  write_server_files "${dir}"; cleanup_server
  cleanup_pipe="${dir}/console.pipe"; mkfifo "${cleanup_pipe}"
  tail -f /dev/null > "${cleanup_pipe}" & cleanup_keeper=$!
  (cd "${dir}" && java -Xms1G -Xmx2G -jar "${JAR}" nogui < "${cleanup_pipe}" > "${log}" 2>&1) & cleanup_pid=$!
  wait_ready "${log}"
  send_console 'execute in minecraft:overworld run gamerule minecraft:random_tick_speed 0'
  wait_literal "${log}" 'Gamerule random_tick_speed is now set to: 0' 15 'random tick isolation'

  local index=0 total="$#"
  for coord in "$@"; do
    IFS=',' read -r cx cz <<< "${coord}"; index=$((index+1))
    local bx=$((cx*16+8)) bz=$((cz*16+8))
    local marked="Marked chunk [${cx}, ${cz}] in minecraft:overworld to be force loaded"
    local unmarked="Unmarked chunk [${cx}, ${cz}] in minecraft:overworld for force loading"
    local token="NEVEROVERWORLD_FULL_${label}_${index}_${cx}_${cz}"
    echo "[NeverFolia][NeverOverworld strict determinism] ${label} ${index}/${total}: ${cx},${cz}"
    send_console "execute in minecraft:overworld run forceload add ${bx} ${bz}"
    wait_literal "${log}" "${marked}" 30 "forceload add ${cx},${cz}"
    wait_chunk_full "${log}" "${bx}" "${bz}" "${token}"
    send_console "execute in minecraft:overworld run forceload remove ${bx} ${bz}"
    wait_literal "${log}" "${unmarked}" 30 "forceload remove ${cx},${cz}"
  done
  send_console stop
  for _ in $(seq 1 90); do kill -0 "${cleanup_pid}" 2>/dev/null || break; sleep 1; done
  cleanup_server
  if grep -Eqi "Failed to parse|Couldn't parse|Unknown registry|Errors in currently selected datapacks|Failed to load datapacks|Failed to load registries|NullPointerException|An unexpected error occurred while trying to execute that command|Unknown or incomplete command|Incorrect argument for command|Command exception" "${log}"; then
    echo "NeverOverworld determinism world ${label} contains errors." >&2; cat "${log}" >&2; exit 1
  fi
}

rm -rf "${TEST_ROOT}"; mkdir -p "${TEST_ROOT}"
echo '[NeverFolia][NeverOverworld strict determinism] world A forward order'
generate_world world-a "${ORDER_A[@]}"
echo '[NeverFolia][NeverOverworld strict determinism] world B reverse order'
generate_world world-b "${ORDER_B[@]}"
HASH_ARGS=(); for coord in "${CHUNKS[@]}"; do HASH_ARGS+=("--chunk=${coord}"); done
python3 "${ROOT_DIR}/scripts/hash-never-overworld-generation-chunks.py" --world "${TEST_ROOT}/world-a/world" "${HASH_ARGS[@]}" --output "${TEST_ROOT}/world-a-hash.json" > /dev/null
python3 "${ROOT_DIR}/scripts/hash-never-overworld-generation-chunks.py" --world "${TEST_ROOT}/world-b/world" "${HASH_ARGS[@]}" --output "${TEST_ROOT}/world-b-hash.json" > /dev/null
python3 - "${TEST_ROOT}/world-a-hash.json" "${TEST_ROOT}/world-b-hash.json" <<'PY'
import json,sys
from pathlib import Path
a=json.loads(Path(sys.argv[1]).read_text()); b=json.loads(Path(sys.argv[2]).read_text())
if a['algorithm'] != b['algorithm']:
    raise SystemExit(f"algorithm mismatch: {a['algorithm']} != {b['algorithm']}")
if a['chunks'] != b['chunks']:
    aa={(x['x'],x['z']):x['sha256'] for x in a['chunks']}; bb={(x['x'],x['z']):x['sha256'] for x in b['chunks']}
    lines=['NeverOverworld strict chunk-order generation mismatch:']
    for key in sorted(set(aa)|set(bb)):
        if aa.get(key)!=bb.get(key): lines.append(f"  chunk {key[0]},{key[1]}: {aa.get(key)} != {bb.get(key)}")
    raise SystemExit('\n'.join(lines))
if a['overall_sha256'] != b['overall_sha256']:
    raise SystemExit('NeverOverworld strict overall hash mismatch')
print('[NeverFolia][NeverOverworld strict determinism] ORDER-INDEPENDENCE OK')
print('  algorithm:',a['algorithm']); print('  chunks:',a['chunk_count']); print('  canonical_sha256:',a['overall_sha256'])
PY
