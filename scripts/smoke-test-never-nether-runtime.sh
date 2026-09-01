#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 2 ]; then
  echo "usage: $0 /path/to/NeverFolia.jar /path/to/NeverNether-Core.zip" >&2
  exit 2
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
JAR="$(realpath "$1")"
PACK="$(realpath "$2")"
TEST_DIR="${ROOT_DIR}/smoke-test"
WORLD_DIR="${TEST_DIR}/world"
DATAPACK="${WORLD_DIR}/datapacks/NeverNether-Core.zip"
LOCK_FILE="${WORLD_DIR}/.neverfolia-nevernether-worldgen.lock"

rm -rf "${TEST_DIR}"
mkdir -p "${WORLD_DIR}/datapacks"
cp "${PACK}" "${DATAPACK}"

cat > "${TEST_DIR}/eula.txt" <<'EOF'
eula=true
EOF

cat > "${TEST_DIR}/server.properties" <<'EOF'
level-name=world
level-seed=NeverNether-CI-Test-1
level-type=minecraft:normal
initial-enabled-packs=vanilla,file/NeverNether-Core.zip
initial-disabled-packs=
online-mode=false
enforce-secure-profile=false
server-port=25575
view-distance=2
simulation-distance=2
spawn-protection=0
max-tick-time=-1
enable-status=false
EOF

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
    rm -f "${PIPE_PATH}"
  fi
  SERVER_PID=""
  KEEPER_PID=""
  PIPE_PATH=""
}
trap cleanup_server EXIT

start_interactive() {
  local log_name="$1"
  cleanup_server
  cd "${TEST_DIR}"
  PIPE_PATH="console-${log_name}.pipe"
  rm -f "${PIPE_PATH}"
  mkfifo "${PIPE_PATH}"
  tail -f /dev/null > "${PIPE_PATH}" &
  KEEPER_PID=$!
  java -Xms1G -Xmx2G -jar "${JAR}" nogui < "${PIPE_PATH}" > "${log_name}" 2>&1 &
  SERVER_PID=$!
  cd "${ROOT_DIR}"
}

wait_ready() {
  local log_path="$1"
  local ready=0
  for _ in $(seq 1 180); do
    if grep -q 'Done (' "${log_path}" 2>/dev/null; then
      ready=1
      break
    fi
    if ! kill -0 "${SERVER_PID}" 2>/dev/null; then
      break
    fi
    sleep 1
  done
  if [ "${ready}" -ne 1 ]; then
    echo "NeverFolia did not reach ready state: ${log_path}" >&2
    cat "${log_path}" >&2 || true
    return 1
  fi
}

send_console() {
  printf '%s\n' "$1" > "${TEST_DIR}/${PIPE_PATH}"
}

stop_interactive() {
  send_console 'stop'
  for _ in $(seq 1 60); do
    if ! kill -0 "${SERVER_PID}" 2>/dev/null; then
      break
    fi
    sleep 1
  done
  cleanup_server
}

# ---------------------------------------------------------------------------
# Pass 1: first fingerprinted startup, real Nether generation and boundaries.
# Boundary reads are performed from the saved Anvil/NBT data after shutdown.
# ---------------------------------------------------------------------------
echo '[NeverFolia][NeverNether CI] PASS 1: initial startup and geometry'
start_interactive 'server-first.log'
wait_ready "${TEST_DIR}/server-first.log"

send_console 'execute in minecraft:the_nether run forceload add 0 0'
sleep 8
send_console 'execute in minecraft:the_nether run setblock 0 500 0 minecraft:stone'
send_console 'save-all'
sleep 5
send_console 'execute in minecraft:the_nether run forceload remove 0 0'
sleep 2
stop_interactive

FIRST_LOG="${TEST_DIR}/server-first.log"
if ! grep -q "Selecting spawn point for level 'minecraft:the_nether'" "${FIRST_LOG}"; then
  echo 'Nether spawn generation was not observed.' >&2
  cat "${FIRST_LOG}" >&2
  exit 1
fi
if ! grep -q "Saving chunks for level 'ServerLevel\[world\]'/minecraft:the_nether" "${FIRST_LOG}"; then
  echo 'Nether chunk save was not observed.' >&2
  cat "${FIRST_LOG}" >&2
  exit 1
fi
if grep -Eqi "Failed to parse|Couldn't parse|Unknown registry|Errors in currently selected datapacks|Failed to load datapacks|Failed to load registries|NullPointerException|An unexpected error occurred while trying to execute that command|Command exception|Unknown or incomplete command" "${FIRST_LOG}"; then
  echo 'NeverNether runtime/command error detected.' >&2
  cat "${FIRST_LOG}" >&2
  exit 1
fi

python3 "${ROOT_DIR}/scripts/hash-never-nether-chunks.py" \
  --world "${WORLD_DIR}" \
  --assert-block=0,-128,0=minecraft:bedrock \
  --assert-block=0,383,0=minecraft:bedrock \
  --assert-block=0,384,0=minecraft:air \
  --assert-block=0,500,0=minecraft:stone

python3 - "${WORLD_DIR}" "${LOCK_FILE}" <<'PY'
import gzip
import re
import sys
from pathlib import Path

world = Path(sys.argv[1])
lock = Path(sys.argv[2])
level = world / 'level.dat'
if not level.is_file():
    raise SystemExit('world/level.dat was not created')
with gzip.open(level, 'rb') as fh:
    payload = fh.read()
if b'file/NeverNether-Core.zip' not in payload:
    raise SystemExit('NeverNether-Core.zip is not recorded in the enabled datapack list')
if not lock.is_file():
    raise SystemExit('NeverNether worldgen fingerprint lock was not created')
text = lock.read_text(encoding='utf-8')
if 'worldgen_id=NN-DEV-1' not in text:
    raise SystemExit('NeverNether lock worldgen_id mismatch')
if 'algorithm=sha256-path-and-content-v1' not in text:
    raise SystemExit('NeverNether lock algorithm mismatch')
match = re.search(r'^content_sha256=([0-9a-f]{64})$', text, re.MULTILINE)
if not match:
    raise SystemExit('NeverNether lock has no valid content_sha256')
print('NeverNether world lock:', match.group(1))

candidates = (
    world / 'dimensions/minecraft/the_nether/region',
    world.parent / 'world_nether/region',
    world.parent / 'world_nether/DIM-1/region',
    world / 'DIM-1/region',
)
discovered = []
for region_dir in candidates:
    if region_dir.is_dir():
        files = sorted(region_dir.glob('*.mca'))
        if files:
            discovered.append((region_dir, files))
if not discovered:
    all_regions = sorted(world.parent.glob('**/region/*.mca'))
    listing = '\n'.join(f'  - {path}' for path in all_regions) or '  (none)'
    raise SystemExit('No Nether region file generated.\nRegion files found:\n' + listing)
for region_dir, files in discovered:
    print(f'NeverNether runtime verification: {len(files)} region file(s) in {region_dir}')
PY

# ---------------------------------------------------------------------------
# Pass 2: unchanged datapack must verify the existing lock and start normally.
# ---------------------------------------------------------------------------
echo '[NeverFolia][NeverNether CI] PASS 2: unchanged fingerprint restart'
start_interactive 'server-restart.log'
wait_ready "${TEST_DIR}/server-restart.log"
stop_interactive
RESTART_LOG="${TEST_DIR}/server-restart.log"
if ! grep -q '\[NeverFolia\]\[NeverNether\] Worldgen fingerprint verified:' "${RESTART_LOG}"; then
  echo 'Unchanged NeverNether fingerprint was not verified on restart.' >&2
  cat "${RESTART_LOG}" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Pass 3: mutate content, create a NEW internally valid fingerprint, and prove
# that the existing world lock rejects this different worldgen before startup.
# ---------------------------------------------------------------------------
echo '[NeverFolia][NeverNether CI] PASS 3: valid fingerprint mismatch rejection'
python3 - "${DATAPACK}" <<'PY'
import sys
import zipfile
from pathlib import Path
pack = Path(sys.argv[1])
with zipfile.ZipFile(pack, 'a', zipfile.ZIP_DEFLATED) as zf:
    zf.writestr('neverfolia-ci-worldgen-mutation.txt', b'intentional mismatch for startup guard CI\n')
PY
python3 "${ROOT_DIR}/scripts/fingerprint-never-nether-pack.py" --input "${DATAPACK}" --inject

MISMATCH_LOG="${TEST_DIR}/server-mismatch.log"
cd "${TEST_DIR}"
set +e
timeout 120s java -Xms1G -Xmx2G -jar "${JAR}" nogui < /dev/null > "${MISMATCH_LOG}" 2>&1
MISMATCH_RC=$?
set -e
cd "${ROOT_DIR}"

if grep -q 'Done (' "${MISMATCH_LOG}"; then
  echo 'NeverNether mismatched worldgen unexpectedly reached ready state.' >&2
  cat "${MISMATCH_LOG}" >&2
  exit 1
fi
if ! grep -q 'NeverNether worldgen fingerprint mismatch' "${MISMATCH_LOG}"; then
  echo "NeverNether mismatch startup failed without the expected guard reason (rc=${MISMATCH_RC})." >&2
  cat "${MISMATCH_LOG}" >&2
  exit 1
fi
if [ "${MISMATCH_RC}" -eq 124 ]; then
  echo 'NeverNether mismatched startup timed out instead of being rejected.' >&2
  cat "${MISMATCH_LOG}" >&2
  exit 1
fi

echo '[NeverFolia][NeverNether CI] runtime + fingerprint guard smoke test passed.'
tail -n 60 "${FIRST_LOG}"
tail -n 40 "${RESTART_LOG}"
tail -n 60 "${MISMATCH_LOG}"
