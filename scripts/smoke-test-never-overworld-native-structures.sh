#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 2 ]; then
  echo "usage: $0 /path/to/NeverFolia.jar /path/to/NeverOverworld-Core.zip" >&2
  exit 2
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
JAR="$(realpath "$1")"
PACK="$(realpath "$2")"
TEST_DIR="${ROOT_DIR}/overworld-structures-smoke-test"
WORLD_DIR="${TEST_DIR}/world"
DATAPACK="${WORLD_DIR}/datapacks/NeverOverworld-Core.zip"

rm -rf "${TEST_DIR}"
mkdir -p "${WORLD_DIR}/datapacks"
cp "${PACK}" "${DATAPACK}"
printf 'eula=true\n' > "${TEST_DIR}/eula.txt"
cat > "${TEST_DIR}/server.properties" <<'PROPS'
level-name=world
level-seed=NeverOverworld-Structures-CI-1
level-type=minecraft:normal
initial-enabled-packs=vanilla,file/NeverOverworld-Core.zip
initial-disabled-packs=
online-mode=false
enforce-secure-profile=false
server-port=25579
view-distance=2
simulation-distance=2
spawn-protection=0
max-tick-time=-1
enable-status=false
PROPS

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

for _ in $(seq 1 240); do
  if grep -q 'Done (' "${TEST_DIR}/server.log" 2>/dev/null; then break; fi
  if ! kill -0 "${SERVER_PID}" 2>/dev/null; then break; fi
  sleep 1
done
if ! grep -q 'Done (' "${TEST_DIR}/server.log" 2>/dev/null; then
  echo 'NeverOverworld structures smoke server did not reach ready state.' >&2
  cat "${TEST_DIR}/server.log" >&2 || true
  exit 1
fi

# Keep test sites loaded, then place every NBT template directly. This forces the
# runtime StructureTemplateManager to decode our gzip NBT rather than merely
# accepting worldgen JSON during registry bootstrap.
for x in 0 64 128 192 256 320 384 448; do
  send_console "execute in minecraft:overworld run forceload add ${x} 0"
done
sleep 3

send_console 'execute in minecraft:overworld run place template neverfolia:never_overworld/structures/buried_sanctum 0 300 0'
send_console 'execute in minecraft:overworld run place template neverfolia:never_overworld/structures/abyssal_archive 64 300 0'
send_console 'execute in minecraft:overworld run place template neverfolia:never_overworld/structures/ancient_cistern 128 300 0'
send_console 'execute in minecraft:overworld run place template neverfolia:never_overworld/structures/collapsed_mine 192 300 0'
send_console 'execute in minecraft:overworld run place template neverfolia:never_overworld/structures/geode_vault 256 300 0'
send_console 'execute in minecraft:overworld run place template neverfolia:never_overworld/structures/flooded_ruins 320 300 0'
send_console 'execute in minecraft:overworld run place template neverfolia:never_overworld/structures/prospector_camp 384 300 0'
send_console 'execute in minecraft:overworld run place template neverfolia:never_overworld/structures/sealed_cache 448 300 0'
sleep 5

send_console 'execute in minecraft:overworld if block 8 303 8 minecraft:lodestone run say NR_STRUCT_BURIED_OK'
send_console 'execute in minecraft:overworld if block 71 302 9 minecraft:lapis_block run say NR_STRUCT_ARCHIVE_OK'
send_console 'execute in minecraft:overworld if block 132 302 4 minecraft:water run say NR_STRUCT_CISTERN_OK'
send_console 'execute in minecraft:overworld if block 196 301 4 minecraft:crafting_table run say NR_STRUCT_MINE_OK'
send_console 'execute in minecraft:overworld if block 263 302 7 minecraft:budding_amethyst run say NR_STRUCT_GEODE_OK'
send_console 'execute in minecraft:overworld if block 330 301 7 minecraft:sea_lantern run say NR_STRUCT_RUINS_OK'
send_console 'execute in minecraft:overworld if block 394 301 9 minecraft:campfire run say NR_STRUCT_CAMP_OK'
send_console 'execute in minecraft:overworld if block 452 303 4 minecraft:gold_block run say NR_STRUCT_CACHE_OK'

for token in \
  NR_STRUCT_BURIED_OK NR_STRUCT_ARCHIVE_OK NR_STRUCT_CISTERN_OK NR_STRUCT_MINE_OK \
  NR_STRUCT_GEODE_OK NR_STRUCT_RUINS_OK NR_STRUCT_CAMP_OK NR_STRUCT_CACHE_OK; do
  wait_literal "${token}" 30
done

send_console 'execute in minecraft:overworld run forceload remove all'
send_console 'stop'
for _ in $(seq 1 90); do
  if ! kill -0 "${SERVER_PID}" 2>/dev/null; then break; fi
  sleep 1
done
cleanup_server

LOG="${TEST_DIR}/server.log"
if grep -Eqi "Failed to parse|Couldn't parse|Unknown registry|Errors in currently selected datapacks|Failed to load datapacks|Failed to load registries|Unknown template|Failed to place|Unknown or incomplete command|Incorrect argument for command|Command exception|NullPointerException" "${LOG}"; then
  echo 'NeverOverworld native structure runtime error detected.' >&2
  cat "${LOG}" >&2
  exit 1
fi

echo '[NeverFolia][NeverOverworld structures] all 8 native NBT templates loaded and placed.'
tail -n 100 "${LOG}"
