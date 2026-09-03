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

wait_chunk_loaded() {
  local x="$1" z="$2" token="$3"
  for _ in $(seq 1 150); do
    # `if loaded` is intentionally the only runtime world-read used by this harness.
    # It is the same Folia-safe FULL barrier used by the base NR runtime smoke.
    send_console "execute in minecraft:overworld if loaded ${x} 300 ${z} run say ${token}"
    sleep 1
    if grep -Fq -- "${token}" "${TEST_DIR}/server.log" 2>/dev/null; then return 0; fi
    if ! kill -0 "${SERVER_PID}" 2>/dev/null; then break; fi
  done
  echo "NeverOverworld structure smoke chunk did not reach FULL barrier: ${x},${z}" >&2
  cat "${TEST_DIR}/server.log" >&2 || true
  return 1
}

prepare_site() {
  local origin_x="$1" size_x="$2" size_z="$3" label="$4"
  local max_x=$((origin_x + size_x - 1))
  local max_z=$((size_z - 1))
  send_console "execute in minecraft:overworld run forceload add ${origin_x} 0 ${max_x} ${max_z}"

  local bx bz index=0
  for ((bx=origin_x; bx<=max_x; bx+=16)); do
    for ((bz=0; bz<=max_z; bz+=16)); do
      index=$((index + 1))
      wait_chunk_loaded "${bx}" "${bz}" "NR_STRUCT_FULL_${label}_${index}_${bx}_${bz}"
    done
  done
  # When a dimension is exactly crossed by the final block, the loop above already
  # hits that chunk. For non-aligned endings, explicitly probe the far corner too.
  wait_chunk_loaded "${max_x}" "${max_z}" "NR_STRUCT_FULL_${label}_FAR_${max_x}_${max_z}"
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

# Each one-piece template spans up to 21x19 blocks. Force-load its complete block
# footprint and wait for every touched chunk to be FULL before invoking /place.
# This avoids the previous race where all commands were sent three seconds after
# forceload and Folia correctly answered "That position is not loaded".
prepare_site 0   17 17 BURIED
prepare_site 64  15 19 ARCHIVE
prepare_site 128 17 17 CISTERN
prepare_site 192 19 13 MINE
prepare_site 256 15 15 GEODE
prepare_site 320 21 15 RUINS
prepare_site 384 15 15 CAMP
prepare_site 448 9  9 CACHE

send_console 'execute in minecraft:overworld run place template neverfolia:never_overworld/structures/buried_sanctum 0 300 0'
send_console 'execute in minecraft:overworld run place template neverfolia:never_overworld/structures/abyssal_archive 64 300 0'
send_console 'execute in minecraft:overworld run place template neverfolia:never_overworld/structures/ancient_cistern 128 300 0'
send_console 'execute in minecraft:overworld run place template neverfolia:never_overworld/structures/collapsed_mine 192 300 0'
send_console 'execute in minecraft:overworld run place template neverfolia:never_overworld/structures/geode_vault 256 300 0'
send_console 'execute in minecraft:overworld run place template neverfolia:never_overworld/structures/flooded_ruins 320 300 0'
send_console 'execute in minecraft:overworld run place template neverfolia:never_overworld/structures/prospector_camp 384 300 0'
send_console 'execute in minecraft:overworld run place template neverfolia:never_overworld/structures/sealed_cache 448 300 0'

# Give region-owned placement work a deterministic completion/IO window while all
# touched chunks remain force-loaded. Block verification itself is deliberately
# performed offline after shutdown; global-console `execute if block` is not a safe
# Folia region read and caused Level.getCurrentWorldData() NPEs in the old harness.
sleep 8
send_console 'execute in minecraft:overworld run forceload remove all'
sleep 2
send_console 'stop'
for _ in $(seq 1 120); do
  if ! kill -0 "${SERVER_PID}" 2>/dev/null; then break; fi
  sleep 1
done
cleanup_server

LOG="${TEST_DIR}/server.log"
if grep -Eqi "Failed to parse|Couldn't parse|Unknown registry|Errors in currently selected datapacks|Failed to load datapacks|Failed to load registries|Unknown template|Failed to place|That position is not loaded|Unknown or incomplete command|Incorrect argument for command|Command exception|An unexpected error occurred while trying to execute that command|NullPointerException" "${LOG}"; then
  echo 'NeverOverworld native structure runtime error detected.' >&2
  cat "${LOG}" >&2
  exit 1
fi

# Verify final blocks from persisted Anvil NBT instead of querying blocks from the
# Folia global console thread. This proves StructureTemplateManager decoded each
# gzip NBT and that /place persisted the expected one-piece template geometry.
python3 - "${ROOT_DIR}" "${WORLD_DIR}" <<'PY'
import importlib.util
import sys
from pathlib import Path

root = Path(sys.argv[1])
world = Path(sys.argv[2])
raw_spec = importlib.util.spec_from_file_location(
    "raw_hasher", root / "scripts/hash-never-nether-chunks.py"
)
raw = importlib.util.module_from_spec(raw_spec)
assert raw_spec.loader is not None
raw_spec.loader.exec_module(raw)

over_spec = importlib.util.spec_from_file_location(
    "over_hasher", root / "scripts/hash-never-overworld-generation-chunks.py"
)
over = importlib.util.module_from_spec(over_spec)
assert over_spec.loader is not None
over_spec.loader.exec_module(over)

region = over.find_region_dir(world)
print("NeverOverworld structure region directory:", region)

checks = [
    ("buried_sanctum", 8,   303, 8, "minecraft:lodestone"),
    ("abyssal_archive", 71, 302, 9, "minecraft:lapis_block"),
    ("ancient_cistern", 132,302, 4, "minecraft:water"),
    ("collapsed_mine", 196,301, 4, "minecraft:crafting_table"),
    ("geode_vault", 263,   302, 7, "minecraft:budding_amethyst"),
    ("flooded_ruins", 330, 301, 7, "minecraft:sea_lantern"),
    ("prospector_camp",394,301, 9, "minecraft:campfire"),
    ("sealed_cache", 452,  303, 4, "minecraft:gold_block"),
]

loaded = {}
for name, x, y, z, expected in checks:
    cx = x // 16
    cz = z // 16
    key = (cx, cz)
    if key not in loaded:
        try:
            loaded[key] = raw.read_chunk_nbt(region, cx, cz)
        except FileNotFoundError as exc:
            raise SystemExit(f"{name}: marker chunk {cx},{cz} was not persisted: {exc}")
    actual = raw.block_at(loaded[key], x, y, z)
    if actual != expected:
        raise SystemExit(
            f"{name}: persisted marker mismatch at {x},{y},{z}: {actual} != {expected}"
        )
    print(f"NR structure NBT OK: {name} {x},{y},{z} -> {actual}")

print("[NeverFolia][NeverOverworld structures] ALL 8 PERSISTED NBT MARKERS OK")
PY

echo '[NeverFolia][NeverOverworld structures] all 8 native NBT templates loaded, placed, and persisted.'
tail -n 100 "${LOG}"
