#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 2 ]; then
  echo "usage: $0 /path/to/NeverFolia.jar /path/to/NeverOverworld-Core.zip" >&2
  exit 2
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
JAR="$(realpath "$1")"
PACK="$(realpath "$2")"
TEST_DIR="${ROOT_DIR}/overworld-r9-vanilla-structures-test"
WORLD_DIR="${TEST_DIR}/world"
DATAPACK="${WORLD_DIR}/datapacks/NeverOverworld-Core.zip"
MANIFEST="${TEST_DIR}/structure-manifest.json"
REPORT="${ROOT_DIR}/artifacts/r9-vanilla-structure-integrity.json"
SEED_TEXT='NeverOverworld-R9-Vanilla-Structure-Integrity-CI-1'
ORIGIN_X=8192
ORIGIN_Y=200
ORIGIN_Z=8192
LOAD_RADIUS_BLOCKS=64
LOCATE_TIMEOUT=30
LOAD_TIMEOUT=180

TARGETS=(
  'minecraft:swamp_hut'
  'minecraft:ruined_portal'
  'minecraft:trial_chambers'
)

rm -rf "${TEST_DIR}"
mkdir -p "${WORLD_DIR}/datapacks" "${ROOT_DIR}/artifacts"
cp "${PACK}" "${DATAPACK}"
printf 'eula=true\n' > "${TEST_DIR}/eula.txt"
printf '{}\n' > "${MANIFEST}"
cat > "${TEST_DIR}/server.properties" <<PROPS
level-name=world
level-seed=${SEED_TEXT}
level-type=minecraft:normal
initial-enabled-packs=vanilla,file/NeverOverworld-Core.zip
initial-disabled-packs=
online-mode=false
enforce-secure-profile=false
server-port=25590
view-distance=2
simulation-distance=2
spawn-protection=0
max-tick-time=-1
enable-status=false
PROPS

SERVER_PID=""
KEEPER_PID=""
PIPE_PATH=""
cleanup_server() {
  if [ -n "${SERVER_PID}" ]; then
    kill "${SERVER_PID}" 2>/dev/null || true
    wait "${SERVER_PID}" 2>/dev/null || true
  fi
  if [ -n "${KEEPER_PID}" ]; then
    kill "${KEEPER_PID}" 2>/dev/null || true
    wait "${KEEPER_PID}" 2>/dev/null || true
  fi
  if [ -n "${PIPE_PATH}" ]; then
    rm -f "${TEST_DIR}/${PIPE_PATH}"
  fi
  SERVER_PID=""
  KEEPER_PID=""
  PIPE_PATH=""
}
trap cleanup_server EXIT

cd "${TEST_DIR}"
PIPE_PATH="console.pipe"
mkfifo "${PIPE_PATH}"
tail -f /dev/null > "${PIPE_PATH}" &
KEEPER_PID=$!
java -Xms1G -Xmx3G -jar "${JAR}" nogui < "${PIPE_PATH}" > server.log 2>&1 &
SERVER_PID=$!
cd "${ROOT_DIR}"

send_console() {
  printf '%s\n' "$1" > "${TEST_DIR}/${PIPE_PATH}"
}

for _ in $(seq 1 300); do
  if grep -q 'Done (' "${TEST_DIR}/server.log" 2>/dev/null; then break; fi
  if ! kill -0 "${SERVER_PID}" 2>/dev/null; then break; fi
  sleep 1
done
if ! grep -q 'Done (' "${TEST_DIR}/server.log" 2>/dev/null; then
  echo '[NeverFolia][R9 vanilla structures] server did not reach ready state.' >&2
  tail -n 300 "${TEST_DIR}/server.log" >&2 || true
  exit 1
fi

send_console 'execute in minecraft:overworld run gamerule minecraft:random_tick_speed 0'

locate_target() {
  local structure="$1" ordinal="$2"
  local token="NR_R9_STRUCTURE_LOCATE_DONE_${ordinal}"
  local start_line
  start_line=$(( $(wc -l < "${TEST_DIR}/server.log") + 1 ))

  echo "[NeverFolia][R9 vanilla structures] locating ${structure}"
  send_console "execute in minecraft:overworld positioned ${ORIGIN_X} ${ORIGIN_Y} ${ORIGIN_Z} run locate structure ${structure}"
  send_console "say ${token}"

  local completed=0
  for _ in $(seq 1 "${LOCATE_TIMEOUT}"); do
    if tail -n +"${start_line}" "${TEST_DIR}/server.log" | grep -Fq -- "${token}"; then
      completed=1
      break
    fi
    if ! kill -0 "${SERVER_PID}" 2>/dev/null; then break; fi
    sleep 1
  done
  if [ "${completed}" -ne 1 ]; then
    echo "[NeverFolia][R9 vanilla structures] locate timed out for ${structure}" >&2
    tail -n 250 "${TEST_DIR}/server.log" >&2 || true
    exit 1
  fi

  local segment="${TEST_DIR}/locate-${ordinal}.log"
  tail -n +"${start_line}" "${TEST_DIR}/server.log" > "${segment}"
  if grep -Eqi 'FoliaWatchdogThread|has not responded in [0-9]|Command exception|Could not find|Couldn.t find|Unknown registry|Incorrect argument|StackOverflowError|OutOfMemoryError' "${segment}"; then
    echo "[NeverFolia][R9 vanilla structures] locate failure/watchdog for ${structure}" >&2
    tail -n 250 "${segment}" >&2 || true
    exit 1
  fi

  python3 - "${segment}" "${structure}" "${MANIFEST}" <<'PY'
import json
import re
import sys
from pathlib import Path

segment=Path(sys.argv[1])
structure=sys.argv[2]
manifest=Path(sys.argv[3])
coord_re=re.compile(r'\[\s*(-?\d+)\s*,\s*([^,\]]+)\s*,\s*(-?\d+)\s*\]')
parsed=None
for line in reversed(segment.read_text(errors='replace').splitlines()):
    match=coord_re.search(line)
    if match:
        parsed=(int(match.group(1)), int(match.group(3)), line)
        break
if parsed is None:
    raise SystemExit(f'could not parse locate coordinates for {structure}')
data=json.loads(manifest.read_text())
data[structure]={
    'block_x':parsed[0],
    'block_z':parsed[1],
    'feedback':parsed[2],
}
manifest.write_text(json.dumps(data,indent=2)+'\n')
print(f'[NeverFolia][R9 vanilla structures] {structure} -> {parsed[0]},{parsed[1]}')
PY
}

force_generate_target() {
  local structure="$1" ordinal="$2"
  local values
  values="$(python3 - "${MANIFEST}" "${structure}" "${LOAD_RADIUS_BLOCKS}" <<'PY'
import json,sys
m=json.load(open(sys.argv[1]))[sys.argv[2]]
r=int(sys.argv[3]); x=int(m['block_x']); z=int(m['block_z'])
print(x-r,z-r,x+r,z+r,x,z)
PY
)"
  read -r min_x min_z max_x max_z center_x center_z <<< "${values}"

  echo "[NeverFolia][R9 vanilla structures] generating bounded window for ${structure}: (${min_x},${min_z})..(${max_x},${max_z})"
  send_console "execute in minecraft:overworld run forceload add ${min_x} ${min_z} ${max_x} ${max_z}"

  local points=(
    "${min_x} ${min_z}"
    "${max_x} ${min_z}"
    "${min_x} ${max_z}"
    "${max_x} ${max_z}"
    "${center_x} ${center_z}"
  )
  local point_index=0
  for point in "${points[@]}"; do
    point_index=$((point_index+1))
    read -r px pz <<< "${point}"
    local token="NR_R9_STRUCTURE_FULL_${ordinal}_${point_index}"
    local ready=0
    for _ in $(seq 1 "${LOAD_TIMEOUT}"); do
      send_console "execute in minecraft:overworld if loaded ${px} 0 ${pz} run say ${token}"
      sleep 1
      if grep -Fq -- "${token}" "${TEST_DIR}/server.log" 2>/dev/null; then
        ready=1
        break
      fi
      if ! kill -0 "${SERVER_PID}" 2>/dev/null; then break; fi
    done
    if [ "${ready}" -ne 1 ]; then
      echo "[NeverFolia][R9 vanilla structures] bounded window did not reach FULL for ${structure} at ${px},${pz}" >&2
      tail -n 250 "${TEST_DIR}/server.log" >&2 || true
      exit 1
    fi
  done

  send_console 'save-all flush'
  sleep 5
  send_console "execute in minecraft:overworld run forceload remove ${min_x} ${min_z} ${max_x} ${max_z}"
}

ordinal=0
for target in "${TARGETS[@]}"; do
  ordinal=$((ordinal+1))
  locate_target "${target}" "${ordinal}"
  force_generate_target "${target}" "${ordinal}"
done

send_console 'save-all flush'
sleep 5
send_console 'stop'
for _ in $(seq 1 120); do
  if ! kill -0 "${SERVER_PID}" 2>/dev/null; then break; fi
  sleep 1
done
cleanup_server

if grep -Eqi 'FoliaWatchdogThread|has not responded in [0-9]|Command exception|StackOverflowError|OutOfMemoryError|Failed to load datapacks|Failed to load registries' "${TEST_DIR}/server.log"; then
  echo '[NeverFolia][R9 vanilla structures] runtime failure/watchdog detected.' >&2
  grep -Ein 'FoliaWatchdogThread|has not responded in [0-9]|Command exception|StackOverflowError|OutOfMemoryError|Failed to load datapacks|Failed to load registries' "${TEST_DIR}/server.log" >&2 || true
  exit 1
fi

python3 ./scripts/audit-never-overworld-r9-vanilla-structures.py \
  --world "${WORLD_DIR}" \
  --manifest "${MANIFEST}" \
  --output "${REPORT}"

echo '[NeverFolia][R9 vanilla structures] SWAMP-HUT / RUINED-PORTAL / TRIAL-CHAMBER INTEGRITY OK'
