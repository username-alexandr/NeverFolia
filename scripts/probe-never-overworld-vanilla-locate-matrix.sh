#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 2 ]; then
  echo "usage: $0 /path/to/NeverFolia.jar /path/to/NeverOverworld-Core.zip" >&2
  exit 2
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
JAR="$(realpath "$1")"
PACK="$(realpath "$2")"
TEST_DIR="${ROOT_DIR}/overworld-vanilla-locate-matrix-test"
WORLD_DIR="${TEST_DIR}/world"
DATAPACK="${WORLD_DIR}/datapacks/NeverOverworld-Core.zip"
RESULTS="${TEST_DIR}/locate-matrix.tsv"
REPORT="${ROOT_DIR}/artifacts/NeverOverworld-vanilla-locate-matrix.json"
SEED_TEXT='NeverOverworld-Vanilla-Field-Structures-1'

TARGETS=(
  'minecraft:village_plains'
  'minecraft:village_desert'
  'minecraft:village_savanna'
  'minecraft:village_snowy'
  'minecraft:village_taiga'
  'minecraft:woodland_mansion'
  'minecraft:pillager_outpost'
  'minecraft:desert_pyramid'
  'minecraft:jungle_pyramid'
  'minecraft:igloo'
  'minecraft:swamp_hut'
  'minecraft:stronghold'
)

rm -rf "${TEST_DIR}"
mkdir -p "${WORLD_DIR}/datapacks" "${ROOT_DIR}/artifacts"
cp "${PACK}" "${DATAPACK}"
printf 'eula=true\n' > "${TEST_DIR}/eula.txt"
cat > "${TEST_DIR}/server.properties" <<PROPS
level-name=world
level-seed=${SEED_TEXT}
level-type=minecraft:normal
initial-enabled-packs=vanilla,file/NeverOverworld-Core.zip
initial-disabled-packs=
online-mode=false
enforce-secure-profile=false
server-port=25588
view-distance=2
simulation-distance=2
spawn-protection=0
max-tick-time=-1
enable-status=false
PROPS
: > "${RESULTS}"

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

for _ in $(seq 1 300); do
  if grep -q 'Done (' "${TEST_DIR}/server.log" 2>/dev/null; then break; fi
  if ! kill -0 "${SERVER_PID}" 2>/dev/null; then break; fi
  sleep 1
done
if ! grep -q 'Done (' "${TEST_DIR}/server.log" 2>/dev/null; then
  echo 'Vanilla locate matrix server did not reach ready state.' >&2
  cat "${TEST_DIR}/server.log" >&2 || true
  exit 1
fi

for target in "${TARGETS[@]}"; do
  start_line=$(( $(wc -l < "${TEST_DIR}/server.log") + 1 ))
  start_ms="$(date +%s%3N)"
  echo "[NeverFolia][vanilla locate matrix] locating ${target}"
  send_console "execute in minecraft:overworld positioned 0 128 0 run locate structure ${target}"
  status="timeout"
  line=""
  for _ in $(seq 1 30); do
    segment="$(tail -n +"${start_line}" "${TEST_DIR}/server.log" 2>/dev/null || true)"
    if grep -Fq -- 'Could not find' <<<"${segment}"; then
      status="not_found"
      line="$(grep -F -- 'Could not find' <<<"${segment}" | tail -n 1)"
      break
    fi
    if grep -Fq -- "The nearest ${target} is at [" <<<"${segment}"; then
      status="found"
      line="$(grep -F -- "The nearest ${target} is at [" <<<"${segment}" | tail -n 1)"
      break
    fi
    if ! kill -0 "${SERVER_PID}" 2>/dev/null; then break; fi
    sleep 1
  done
  end_ms="$(date +%s%3N)"
  elapsed=$((end_ms-start_ms))
  printf '%s\t%s\t%s\t%s\n' "${target}" "${status}" "${elapsed}" "${line//$'\t'/ }" >> "${RESULTS}"
  echo "[NeverFolia][vanilla locate matrix] ${target}: ${status} ${elapsed}ms"
done

send_console 'stop'
for _ in $(seq 1 90); do
  if ! kill -0 "${SERVER_PID}" 2>/dev/null; then break; fi
  sleep 1
done
cleanup_server

python3 - "${RESULTS}" "${REPORT}" <<'PY'
import json,sys
from pathlib import Path
rows=[]
for line in Path(sys.argv[1]).read_text().splitlines():
    target,status,elapsed,*rest=line.split('\t')
    rows.append({'structure':target,'status':status,'elapsed_ms':int(elapsed),'message':'\t'.join(rest)})
report={'schema':1,'seed':'NeverOverworld-Vanilla-Field-Structures-1','results':rows}
Path(sys.argv[2]).write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
if any(row['status']=='timeout' for row in rows):
    raise SystemExit('one or more locate requests timed out')
if any(row['elapsed_ms'] > 10000 for row in rows):
    raise SystemExit('one or more locate requests exceeded 10s latency gate')
PY

if grep -Eqi "server has not responded|watchdog|Failed to parse|Couldn't parse|Unknown registry|Errors in currently selected datapacks|Failed to load datapacks|Failed to load registries|Command exception|NullPointerException|An unexpected error occurred" "${TEST_DIR}/server.log"; then
  echo '[NeverFolia][vanilla locate matrix] runtime/watchdog error detected.' >&2
  tail -n 300 "${TEST_DIR}/server.log" >&2
  exit 1
fi

echo '[NeverFolia][NeverOverworld vanilla locate matrix] COMPLETE'
