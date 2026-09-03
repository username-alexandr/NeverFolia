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
NATIVE_FLUID_MARKER='[NeverFolia][NeverOverworld] Native fluid picker active: lava aquifer disabled'
FLOOD_MARKER='[NeverFolia][NeverOverworld] LIGHT flood active: chunk-owned surface-connected Y<=128'

# Seven dispersed geometry/flood samples plus three deterministic native-geology
# probes for seed NeverOverworld-CI-Test-1. The rare-ore chunks were selected from
# the exact NR-DEV-1 hash/province model with enough pre-carver voxel headroom:
# diamond chunk 31,0; emerald chunk -17,-25; gold chunk -4,-17.
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

wait_chunk_loaded() {
  local x="$1" z="$2" token="$3"
  for _ in $(seq 1 150); do
    send_console "execute in minecraft:overworld if loaded ${x} 0 ${z} run say ${token}"
    sleep 1
    if grep -Fq -- "${token}" "${TEST_DIR}/server.log" 2>/dev/null; then return 0; fi
    if ! kill -0 "${SERVER_PID}" 2>/dev/null; then break; fi
  done
  echo "NeverOverworld dispersed smoke chunk did not reach loaded/FULL barrier: ${x},${z}" >&2
  cat "${TEST_DIR}/server.log" >&2 || true
  return 1
}

start_server
wait_ready
wait_literal "${NATIVE_FLUID_MARKER}" 15
send_console 'execute in minecraft:overworld run gamerule minecraft:random_tick_speed 0'
wait_literal 'Gamerule random_tick_speed is now set to: 0' 15

sample_index=0
for coords in "${SAMPLE_BLOCKS[@]}"; do
  read -r x z <<< "${coords}"
  sample_index=$((sample_index + 1))
  token="NEVEROVERWORLD_SMOKE_FULL_${sample_index}_${x}_${z}"
  send_console "execute in minecraft:overworld run forceload add ${x} ${z}"
  wait_chunk_loaded "${x}" "${z}" "${token}"
done
wait_literal "${FLOOD_MARKER}" 30
# The explicit loaded/FULL barrier above replaces the old fixed 20-second sleep.
# Give pending chunk I/O a short deterministic flush window before stopping.
sleep 3

send_console 'execute in minecraft:overworld run setblock 0 500 0 minecraft:stone'
send_console 'execute in minecraft:overworld run setblock 0 -500 0 minecraft:gold_block'
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
if ! grep -Fq -- "${NATIVE_FLUID_MARKER}" "${LOG}"; then
  echo 'NeverOverworld native fluid picker did not activate.' >&2
  cat "${LOG}" >&2
  exit 1
fi
if ! grep -Fq -- "${FLOOD_MARKER}" "${LOG}"; then
  echo 'NeverOverworld LIGHT flood hook did not activate.' >&2
  cat "${LOG}" >&2
  exit 1
fi
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

sample_chunks = [(0,0),(32,0),(-32,0),(0,32),(0,-32),(32,32),(-32,-32),(31,0),(-17,-25),(-4,-17)]
chunks = {}
for cx, cz in sample_chunks:
    try:
        chunks[(cx, cz)] = raw.read_chunk_nbt(region, cx, cz)
    except FileNotFoundError as exc:
        raise SystemExit(f'dispersed flood/ore sample chunk {cx},{cz} was not generated: {exc}')

chunk = chunks[(0, 0)]
for x,y,z,expected in [(0,500,0,'minecraft:stone'),(0,-500,0,'minecraft:gold_block')]:
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

AIR = {'minecraft:air', 'minecraft:cave_air', 'minecraft:void_air'}
FLUID = {'minecraft:water', 'minecraft:lava'}
flood_water = 0
low_open_columns = 0
per_chunk = []
for (cx, cz), current in chunks.items():
    water_here = 0
    low_here = 0
    min_surface = None
    max_surface = None
    base_x = cx * 16
    base_z = cz * 16
    for lz in range(16):
        for lx in range(16):
            wx = base_x + lx
            wz = base_z + lz
            for y in (64, 80, 96, 112, 128):
                if raw.block_at(current, wx, y, wz) == 'minecraft:water':
                    water_here += 1
            if raw.block_at(current, wx, 128, wz) in AIR:
                surface = None
                for y in range(127, -65, -1):
                    block = raw.block_at(current, wx, y, wz)
                    if block not in AIR and block not in FLUID:
                        surface = y
                        break
                if surface is not None:
                    low_here += 1
                    min_surface = surface if min_surface is None else min(min_surface, surface)
                    max_surface = surface if max_surface is None else max(max_surface, surface)
    flood_water += water_here
    low_open_columns += low_here
    per_chunk.append((cx, cz, water_here, low_here, min_surface, max_surface))

for cx, cz, water_here, low_here, min_surface, max_surface in per_chunk:
    print(f'NR-DEV-1 flood diagnostic chunk {cx},{cz}: water={water_here} open_low_columns={low_here} low_surface_range={min_surface}..{max_surface}')

if flood_water == 0:
    if low_open_columns:
        raise SystemExit('VANILLA_FLOODED produced no water despite ' f'{low_open_columns} final-NBT open low-column candidates across dispersed samples')
    raise SystemExit('VANILLA_FLOODED produced no water, but dispersed samples also contained no open terrain below Y=128; choose/locate a deterministic low-terrain smoke sample')
print('NR-DEV-1 dispersed flood sample water blocks:', flood_water)

deep_air = 0
deep_lava = 0
for current in chunks.values():
    cx = int(current.get('xPos', 0))
    cz = int(current.get('zPos', 0))
    base_x = cx * 16
    base_z = cz * 16
    for y in (-440, -360, -280, -200, -120, -80, -40, 0, 32, 63):
        for lz in range(0, 16, 4):
            for lx in range(0, 16, 4):
                block = raw.block_at(current, base_x + lx, y, base_z + lz)
                if block in AIR:
                    deep_air += 1
                elif block == 'minecraft:lava':
                    deep_lava += 1
if deep_air == 0:
    raise SystemExit('no dry cave air observed below Y=64; closed caves were over-flooded')
if deep_lava != 0:
    raise SystemExit(f'generated underground lava remained in NR dispersed smoke samples: {deep_lava}')
print('NR-DEV-1 dispersed dry-cave sample air blocks:', deep_air)

level = world / 'level.dat'
if not level.is_file():
    raise SystemExit('world/level.dat was not created')
with gzip.open(level,'rb') as fh:
    payload = fh.read()
if b'file/NeverOverworld-Core.zip' not in payload:
    raise SystemExit('NeverOverworld-Core.zip is not recorded as enabled')
print('[NeverFolia][NeverOverworld CI] native aquifer + runtime geometry + flood diagnostics OK')
PY

echo '[NeverFolia][NeverOverworld CI] smoke test passed.'
tail -n 100 "${LOG}"
