#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 2 ]; then
  echo "usage: $0 /path/to/NeverFolia.jar /path/to/NeverOverworld-Core.zip" >&2
  exit 2
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
JAR="$(realpath "$1")"
PACK="$(realpath "$2")"
TEST_DIR="${ROOT_DIR}/overworld-fingerprint-smoke-test"
WORLD_DIR="${TEST_DIR}/world"
DATAPACK="${WORLD_DIR}/datapacks/NeverOverworld-Core.zip"
LOCK_FILE="${WORLD_DIR}/.neverfolia-neveroverworld-worldgen.lock"

rm -rf "${TEST_DIR}"
mkdir -p "${WORLD_DIR}/datapacks"
cp "${PACK}" "${DATAPACK}"
printf 'eula=true\n' > "${TEST_DIR}/eula.txt"
cat > "${TEST_DIR}/server.properties" <<'EOF'
level-name=world
level-seed=NeverOverworld-CI-Fingerprint-1
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
EOF

SERVER_PID=""; KEEPER_PID=""; PIPE_PATH=""
cleanup_server() {
  if [ -n "${SERVER_PID}" ]; then kill "${SERVER_PID}" 2>/dev/null || true; wait "${SERVER_PID}" 2>/dev/null || true; fi
  if [ -n "${KEEPER_PID}" ]; then kill "${KEEPER_PID}" 2>/dev/null || true; wait "${KEEPER_PID}" 2>/dev/null || true; fi
  if [ -n "${PIPE_PATH}" ]; then rm -f "${TEST_DIR}/${PIPE_PATH}"; fi
  SERVER_PID=""; KEEPER_PID=""; PIPE_PATH=""
}
trap cleanup_server EXIT

start_interactive() {
  local log_name="$1"
  cleanup_server
  cd "${TEST_DIR}"
  PIPE_PATH="console-${log_name}.pipe"
  rm -f "${PIPE_PATH}"
  mkfifo "${PIPE_PATH}"
  tail -f /dev/null > "${PIPE_PATH}" & KEEPER_PID=$!
  java -Xms1G -Xmx2G -jar "${JAR}" nogui < "${PIPE_PATH}" > "${log_name}" 2>&1 & SERVER_PID=$!
  cd "${ROOT_DIR}"
}

wait_ready() {
  local log="$1"
  for _ in $(seq 1 240); do
    if grep -q 'Done (' "${log}" 2>/dev/null; then return 0; fi
    if ! kill -0 "${SERVER_PID}" 2>/dev/null; then break; fi
    sleep 1
  done
  echo "NeverOverworld fingerprint smoke did not reach ready state: ${log}" >&2
  cat "${log}" >&2 || true
  return 1
}

send_console() { printf '%s\n' "$1" > "${TEST_DIR}/${PIPE_PATH}"; }

stop_interactive() {
  send_console stop
  for _ in $(seq 1 90); do
    if ! kill -0 "${SERVER_PID}" 2>/dev/null; then break; fi
    sleep 1
  done
  cleanup_server
}

FIRST_LOG="${TEST_DIR}/server-first.log"
RESTART_LOG="${TEST_DIR}/server-restart.log"
MISMATCH_LOG="${TEST_DIR}/server-mismatch.log"

echo '[NeverFolia][NeverOverworld fingerprint CI] PASS 1: create NR world lock'
start_interactive 'server-first.log'
wait_ready "${FIRST_LOG}"
stop_interactive

if [ ! -f "${LOCK_FILE}" ]; then
  echo 'NeverOverworld worldgen fingerprint lock was not created.' >&2
  cat "${FIRST_LOG}" >&2
  exit 1
fi
if ! grep -q '^worldgen_id=NR-DEV-1$' "${LOCK_FILE}"; then
  echo 'NeverOverworld lock worldgen_id mismatch.' >&2
  cat "${LOCK_FILE}" >&2
  exit 1
fi
if ! grep -Eq '^content_sha256=[0-9a-f]{64}$' "${LOCK_FILE}"; then
  echo 'NeverOverworld lock has no valid content hash.' >&2
  cat "${LOCK_FILE}" >&2
  exit 1
fi
if ! grep -q '\[NeverFolia\]\[NeverOverworld\] Created worldgen fingerprint lock' "${FIRST_LOG}"; then
  echo 'NeverOverworld guard did not report lock creation.' >&2
  cat "${FIRST_LOG}" >&2
  exit 1
fi

echo '[NeverFolia][NeverOverworld fingerprint CI] PASS 2: unchanged restart'
start_interactive 'server-restart.log'
wait_ready "${RESTART_LOG}"
stop_interactive
if ! grep -q '\[NeverFolia\]\[NeverOverworld\] Worldgen fingerprint verified:' "${RESTART_LOG}"; then
  echo 'Unchanged NeverOverworld fingerprint was not verified.' >&2
  cat "${RESTART_LOG}" >&2
  exit 1
fi

echo '[NeverFolia][NeverOverworld fingerprint CI] PASS 3: reject different valid NR fingerprint'
python3 - "${DATAPACK}" <<'PY'
import sys
import zipfile
from pathlib import Path
pack = Path(sys.argv[1])
with zipfile.ZipFile(pack, 'a', zipfile.ZIP_DEFLATED) as zf:
    zf.writestr('neverfolia-ci-overworld-worldgen-mutation.txt', b'intentional NR fingerprint mismatch\n')
PY
python3 "${ROOT_DIR}/scripts/fingerprint-never-overworld-pack.py" --input "${DATAPACK}" --inject

cd "${TEST_DIR}"
set +e
timeout 120s java -Xms1G -Xmx2G -jar "${JAR}" nogui < /dev/null > "${MISMATCH_LOG}" 2>&1
MISMATCH_RC=$?
set -e
cd "${ROOT_DIR}"

if grep -q 'Done (' "${MISMATCH_LOG}"; then
  echo 'NeverOverworld mismatched worldgen unexpectedly reached ready state.' >&2
  cat "${MISMATCH_LOG}" >&2
  exit 1
fi
if ! grep -q 'NeverOverworld worldgen fingerprint mismatch' "${MISMATCH_LOG}"; then
  echo "NeverOverworld mismatch failed without expected guard reason (rc=${MISMATCH_RC})." >&2
  cat "${MISMATCH_LOG}" >&2
  exit 1
fi
if [ "${MISMATCH_RC}" -eq 124 ]; then
  echo 'NeverOverworld mismatch timed out instead of being rejected.' >&2
  cat "${MISMATCH_LOG}" >&2
  exit 1
fi

echo '[NeverFolia][NeverOverworld fingerprint CI] 3-pass startup guard OK'
tail -n 40 "${FIRST_LOG}"
tail -n 40 "${RESTART_LOG}"
tail -n 60 "${MISMATCH_LOG}"
