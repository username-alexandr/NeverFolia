#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 3 ]; then
  echo "usage: $0 /path/to/NeverFolia.jar /path/to/NeverOverworld-Core.zip /path/to/NeverNether-Core.zip" >&2
  exit 2
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
JAR="$(realpath "$1")"
OVERWORLD_PACK="$(realpath "$2")"
NETHER_PACK="$(realpath "$3")"
TEST_DIR="${ROOT_DIR}/test1-integration-smoke"
WORLD_DIR="${TEST_DIR}/world"
OVERWORLD_NAME="NeverOverworld-Core.zip"
NETHER_NAME="NeverNether-Core.zip"
NATIVE_FLUID_MARKER='[NeverFolia][NeverOverworld] Native fluid picker active: lava aquifer disabled'
FLOOD_MARKER='[NeverFolia][NeverOverworld] LIGHT flood active: chunk-owned surface-connected Y<=128'

rm -rf "${TEST_DIR}"
mkdir -p "${WORLD_DIR}/datapacks"
cp "${OVERWORLD_PACK}" "${WORLD_DIR}/datapacks/${OVERWORLD_NAME}"
cp "${NETHER_PACK}" "${WORLD_DIR}/datapacks/${NETHER_NAME}"
printf 'eula=true\n' > "${TEST_DIR}/eula.txt"
cat > "${TEST_DIR}/server.properties" <<'EOF'
level-name=world
level-seed=NeverFolia-TEST1-Integration
level-type=minecraft:normal
initial-enabled-packs=vanilla,file/NeverOverworld-Core.zip,file/NeverNether-Core.zip
initial-disabled-packs=
online-mode=false
enforce-secure-profile=false
server-port=25579
view-distance=2
simulation-distance=2
spawn-protection=0
max-tick-time=-1
enable-status=false
EOF

SERVER_PID=""; KEEPER_PID=""; PIPE_PATH="console.pipe"
cleanup() {
  if [ -n "${SERVER_PID}" ]; then kill "${SERVER_PID}" 2>/dev/null || true; wait "${SERVER_PID}" 2>/dev/null || true; fi
  if [ -n "${KEEPER_PID}" ]; then kill "${KEEPER_PID}" 2>/dev/null || true; wait "${KEEPER_PID}" 2>/dev/null || true; fi
  rm -f "${TEST_DIR}/${PIPE_PATH}" 2>/dev/null || true
}
trap cleanup EXIT

cd "${TEST_DIR}"
mkfifo "${PIPE_PATH}"
tail -f /dev/null > "${PIPE_PATH}" & KEEPER_PID=$!
java -Xms1G -Xmx2G -jar "${JAR}" nogui < "${PIPE_PATH}" > server.log 2>&1 & SERVER_PID=$!
cd "${ROOT_DIR}"

send_console() { printf '%s\n' "$1" > "${TEST_DIR}/${PIPE_PATH}"; }
wait_literal() {
  local literal="$1" timeout="$2"
  for _ in $(seq 1 "${timeout}"); do
    if grep -Fq -- "${literal}" "${TEST_DIR}/server.log" 2>/dev/null; then return 0; fi
    if ! kill -0 "${SERVER_PID}" 2>/dev/null; then break; fi
    sleep 1
  done
  echo "Timed out waiting for: ${literal}" >&2
  cat "${TEST_DIR}/server.log" >&2 || true
  return 1
}

wait_literal 'Done (' 240
wait_literal "${NATIVE_FLUID_MARKER}" 20
send_console 'execute in minecraft:overworld run gamerule minecraft:random_tick_speed 0'
send_console 'execute in minecraft:overworld run forceload add 0 0'
send_console 'execute in minecraft:the_nether run forceload add 0 0'
wait_literal "${FLOOD_MARKER}" 45
sleep 12
send_console 'execute in minecraft:overworld run setblock 0 -500 0 minecraft:gold_block'
send_console 'execute in minecraft:the_nether run setblock 0 500 0 minecraft:stone'
sleep 3
send_console 'execute in minecraft:overworld run forceload remove all'
send_console 'execute in minecraft:the_nether run forceload remove all'
sleep 2
send_console 'stop'
for _ in $(seq 1 90); do
  if ! kill -0 "${SERVER_PID}" 2>/dev/null; then break; fi
  sleep 1
done
cleanup
SERVER_PID=""; KEEPER_PID=""

LOG="${TEST_DIR}/server.log"
for required in "${NATIVE_FLUID_MARKER}" "${FLOOD_MARKER}" "Selecting spawn point for level 'minecraft:the_nether'"; do
  if ! grep -Fq -- "${required}" "${LOG}"; then
    echo "Missing TEST1 integration evidence: ${required}" >&2
    cat "${LOG}" >&2
    exit 1
  fi
done
if grep -Eqi "Failed to parse|Couldn't parse|Unknown registry|Errors in currently selected datapacks|Failed to load datapacks|Failed to load registries|NullPointerException|An unexpected error occurred while trying to execute that command|Unknown or incomplete command|Incorrect argument for command|Command exception" "${LOG}"; then
  echo 'NeverFolia TEST1 integration runtime/command error detected.' >&2
  cat "${LOG}" >&2
  exit 1
fi

python3 - "${WORLD_DIR}" <<'PY'
import gzip
import sys
from pathlib import Path

world = Path(sys.argv[1])
level = world / 'level.dat'
if not level.is_file():
    raise SystemExit('world/level.dat was not created')
with gzip.open(level, 'rb') as fh:
    payload = fh.read()
for pack in (b'file/NeverOverworld-Core.zip', b'file/NeverNether-Core.zip'):
    if pack not in payload:
        raise SystemExit(f'combined TEST1 world did not record enabled pack: {pack!r}')

if not (world / '.neverfolia-nevernether-worldgen.lock').is_file():
    raise SystemExit('NeverNether fingerprint lock was not created in combined TEST1 world')
if not (world / '.neverfolia-neveroverworld-worldgen.lock').is_file():
    raise SystemExit('NeverOverworld fingerprint lock was not created in combined TEST1 world')

# Datapack overrides of minecraft:overworld/the_nether are stored by the
# dimension key under dimensions/minecraft/... rather than being guaranteed to
# use the legacy world/region and DIM-1 layouts. Accept both layouts so this
# harness verifies generated data instead of asserting a storage convention.
overworld_candidates = [
    world / 'region',
    world / 'dimensions/minecraft/overworld/region',
]
nether_candidates = [
    world / 'DIM-1/region',
    world / 'dimensions/minecraft/the_nether/region',
    world.parent / 'world_nether/region',
    world.parent / 'world_nether/DIM-1/region',
]

def has_regions(paths):
    return any(path.is_dir() and any(path.glob('*.mca')) for path in paths)

if not has_regions(overworld_candidates):
    checked = ', '.join(str(path) for path in overworld_candidates)
    raise SystemExit(f'combined TEST1 did not generate Overworld region data; checked: {checked}')
if not has_regions(nether_candidates):
    checked = ', '.join(str(path) for path in nether_candidates)
    raise SystemExit(f'combined TEST1 did not generate Nether region data; checked: {checked}')

print('[NeverFolia][TEST1 integration] both Core packs enabled and both dimensions generated')
PY

echo '[NeverFolia][TEST1 integration] combined Overworld + Nether smoke passed.'
tail -n 100 "${LOG}"
