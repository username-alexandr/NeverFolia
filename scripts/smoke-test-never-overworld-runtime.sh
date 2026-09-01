#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 2 ]; then
  echo "usage: $0 /path/to/NeverFolia.jar /path/to/NeverOverworld-Core.zip" >&2
  exit 2
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
JAR="$(realpath "$1")"
PACK="$(realpath "$2")"
TEST_DIR="${ROOT_DIR}/overworld-smoke-test"
WORLD_DIR="${TEST_DIR}/world"
DATAPACK="${WORLD_DIR}/datapacks/NeverOverworld-Core.zip"

rm -rf "${TEST_DIR}"
mkdir -p "${WORLD_DIR}/datapacks"
cp "${PACK}" "${DATAPACK}"
printf 'eula=true\n' > "${TEST_DIR}/eula.txt"
cat > "${TEST_DIR}/server.properties" <<'EOF'
level-name=world
level-seed=NeverOverworld-CI-Test-1
level-type=minecraft:normal
initial-enabled-packs=vanilla,file/NeverOverworld-Core.zip
initial-disabled-packs=
online-mode=false
enforce-secure-profile=false
server-port=25577
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

start_server() {
  cleanup_server
  cd "${TEST_DIR}"
  PIPE_PATH="console.pipe"
  mkfifo "${PIPE_PATH}"
  tail -f /dev/null > "${PIPE_PATH}" & KEEPER_PID=$!
  java -Xms1G -Xmx2G -jar "${JAR}" nogui < "${PIPE_PATH}" > server.log 2>&1 & SERVER_PID=$!
  cd "${ROOT_DIR}"
}

send_console() { printf '%s\n' "$1" > "${TEST_DIR}/${PIPE_PATH}"; }

wait_ready() {
  for _ in $(seq 1 240); do
    if grep -q 'Done (' "${TEST_DIR}/server.log" 2>/dev/null; then return 0; fi
    if ! kill -0 "${SERVER_PID}" 2>/dev/null; then break; fi
    sleep 1
  done
  echo 'NeverOverworld smoke server did not reach ready state.' >&2
  cat "${TEST_DIR}/server.log" >&2 || true
  return 1
}

wait_literal() {
  local literal="$1"; local timeout="$2"
  for _ in $(seq 1 "${timeout}"); do
    if grep -Fq -- "${literal}" "${TEST_DIR}/server.log" 2>/dev/null; then return 0; fi
    if ! kill -0 "${SERVER_PID}" 2>/dev/null; then break; fi
    sleep 1
  done
  echo "Timed out waiting for: ${literal}" >&2
  cat "${TEST_DIR}/server.log" >&2 || true
  return 1
}

start_server
wait_ready
send_console 'execute in minecraft:overworld run gamerule minecraft:random_tick_speed 0'
wait_literal 'Gamerule random_tick_speed is now set to: 0' 15
send_console 'execute in minecraft:overworld run forceload add 0 0'
wait_literal 'Marked chunk [0, 0] in minecraft:overworld to be force loaded' 30
sleep 8
send_console 'execute in minecraft:overworld run setblock 0 500 0 minecraft:stone'
send_console 'execute in minecraft:overworld run setblock 0 -500 0 minecraft:gold_block'
sleep 3
send_console 'execute in minecraft:overworld run forceload remove 0 0'
wait_literal 'Unmarked chunk [0, 0] in minecraft:overworld for force loading' 30
send_console 'stop'
for _ in $(seq 1 90); do
  if ! kill -0 "${SERVER_PID}" 2>/dev/null; then break; fi
  sleep 1
done
cleanup_server

LOG="${TEST_DIR}/server.log"
if grep -Eqi "Failed to parse|Couldn't parse|Unknown registry|Errors in currently selected datapacks|Failed to load datapacks|Failed to load registries|NullPointerException|An unexpected error occurred while trying to execute that command|Unknown or incomplete command|Incorrect argument for command|Command exception" "${LOG}"; then
  echo 'NeverOverworld runtime/command error detected.' >&2
  cat "${LOG}" >&2
  exit 1
fi

python3 - "${ROOT_DIR}" "${WORLD_DIR}" <<'PY'
import gzip
import importlib.util
import sys
from pathlib import Path

root = Path(sys.argv[1])
world = Path(sys.argv[2])
raw_spec = importlib.util.spec_from_file_location('raw_hasher', root / 'scripts/hash-never-nether-chunks.py')
raw = importlib.util.module_from_spec(raw_spec); raw_spec.loader.exec_module(raw)
over_spec = importlib.util.spec_from_file_location('over_hasher', root / 'scripts/hash-never-overworld-generation-chunks.py')
over = importlib.util.module_from_spec(over_spec); over_spec.loader.exec_module(over)
region = over.find_region_dir(world)
print('NeverOverworld region directory:', region)
chunk = raw.read_chunk_nbt(region, 0, 0)
for x,y,z,expected in [
    (0,500,0,'minecraft:stone'),
    (0,-500,0,'minecraft:gold_block'),
]:
    actual = raw.block_at(chunk,x,y,z)
    if actual != expected:
        raise SystemExit(f'extended-height persistence mismatch at {x},{y},{z}: {actual} != {expected}')

bottom = [raw.block_at(chunk,x,-512,z) for x in (0,4,8,12) for z in (0,4,8,12)]
if 'minecraft:bedrock' not in bottom:
    raise SystemExit('no bedrock observed at NR-DEV-1 min_y=-512')

deep = [raw.block_at(chunk,x,-200,z) for x in (0,4,8,12) for z in (0,4,8,12)]
if all(block == 'minecraft:air' for block in deep):
    raise SystemExit('deep geology sample at Y=-200 is entirely air')
print('NR-DEV-1 deep sample:', sorted(set(deep)))

flood_water = 0
for y in (64, 80, 96, 112, 128):
    for z in range(16):
        for x in range(16):
            if raw.block_at(chunk, x, y, z) == 'minecraft:water':
                flood_water += 1
if flood_water == 0:
    raise SystemExit('VANILLA_FLOODED produced no water in sampled Y=64..128 planes')
print('NR-DEV-1 flood sample water blocks:', flood_water)

deep_air = 0
deep_lava = 0
for y in (-440, -360, -280, -200, -120, -80, -40, 0, 32, 63):
    for z in range(0, 16, 2):
        for x in range(0, 16, 2):
            block = raw.block_at(chunk, x, y, z)
            if block == 'minecraft:air':
                deep_air += 1
            elif block == 'minecraft:lava':
                deep_lava += 1
if deep_air == 0:
    raise SystemExit('no dry cave air observed below Y=64; closed caves were over-flooded')
if deep_lava != 0:
    raise SystemExit(f'generated underground lava remained in NR smoke sample: {deep_lava}')
print('NR-DEV-1 dry-cave sample air blocks:', deep_air)

level = world / 'level.dat'
if not level.is_file():
    raise SystemExit('world/level.dat was not created')
with gzip.open(level,'rb') as fh:
    payload = fh.read()
if b'file/NeverOverworld-Core.zip' not in payload:
    raise SystemExit('NeverOverworld-Core.zip is not recorded as enabled')
print('[NeverFolia][NeverOverworld CI] runtime geometry + flood verification OK')
PY

echo '[NeverFolia][NeverOverworld CI] smoke test passed.'
tail -n 80 "${LOG}"
