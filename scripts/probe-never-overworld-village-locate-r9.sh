#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 2 ]; then
  echo "usage: $0 /path/to/NeverFolia.jar /path/to/NeverOverworld-Core.zip" >&2
  exit 2
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
JAR="$(realpath "$1")"
PACK="$(realpath "$2")"
TEST_DIR="${ROOT_DIR}/overworld-village-locate-r9-test"
WORLD_DIR="${TEST_DIR}/world"
DATAPACK="${WORLD_DIR}/datapacks/NeverOverworld-Core.zip"
BEFORE="${TEST_DIR}/chunks-before-locate.txt"
AFTER="${TEST_DIR}/chunks-after-locate.txt"
REPORT="${ROOT_DIR}/artifacts/village-locate-r9-proof.json"
SEED_TEXT='NeverOverworld-R9-Village-Locate-CI-1'
ORIGIN_X=8192
ORIGIN_Y=200
ORIGIN_Z=8192
COMMAND_TIMEOUT=20

TARGETS=(
  'minecraft:village_plains'
  'minecraft:village_desert'
  'minecraft:village_savanna'
  'minecraft:village_snowy'
  'minecraft:village_taiga'
  '#minecraft:on_plains_village_maps'
  '#minecraft:on_desert_village_maps'
  '#minecraft:on_savanna_village_maps'
  '#minecraft:on_snowy_village_maps'
  '#minecraft:on_taiga_village_maps'
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
server-port=25589
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
java -Dneverfolia.debugVillageLocate=true -Xms1G -Xmx2G -jar "${JAR}" nogui < "${PIPE_PATH}" > server.log 2>&1 & SERVER_PID=$!
cd "${ROOT_DIR}"
send_console() { printf '%s\n' "$1" > "${TEST_DIR}/${PIPE_PATH}"; }

snapshot_chunks() {
  local output="$1"
  python3 - "${WORLD_DIR}" "${output}" <<'PY'
import re, sys
from pathlib import Path
world=Path(sys.argv[1]); out=Path(sys.argv[2])
region_candidates=[world/'dimensions'/'minecraft'/'overworld'/'region', world/'region']
region_dir=next((p for p in region_candidates if p.is_dir()), None)
if region_dir is None: raise SystemExit(f'Overworld region directory not found under {world}')
dim_root=region_dir.parent; rows=[]; pattern=re.compile(r'^r\.(-?\d+)\.(-?\d+)\.mca$')
for kind in ('region','entities','poi'):
    directory=dim_root/kind
    if not directory.is_dir(): continue
    for path in sorted(directory.glob('r.*.*.mca')):
        match=pattern.match(path.name)
        if not match: continue
        rx,rz=map(int,match.groups()); header=path.read_bytes()[:4096]
        if len(header)<4096: continue
        for index in range(1024):
            if int.from_bytes(header[index*4:(index+1)*4],'big')==0: continue
            lx=index%32; lz=index//32
            rows.append(f'{kind}:{rx*32+lx},{rz*32+lz}')
out.write_text('\n'.join(sorted(rows))+('\n' if rows else ''),encoding='utf-8')
print(f'[NeverFolia][R9 village locate] snapshot {out.name}: {len(rows)} Anvil records')
PY
}

for _ in $(seq 1 300); do
  if grep -q 'Done (' "${TEST_DIR}/server.log" 2>/dev/null; then break; fi
  if ! kill -0 "${SERVER_PID}" 2>/dev/null; then break; fi
  sleep 1
done
if ! grep -q 'Done (' "${TEST_DIR}/server.log" 2>/dev/null; then
  echo '[NeverFolia][R9 village locate] server did not reach ready state.' >&2
  tail -n 300 "${TEST_DIR}/server.log" >&2 || true
  exit 1
fi

send_console 'execute in minecraft:overworld run gamerule minecraft:random_tick_speed 0'
send_console 'save-all flush'
sleep 5
snapshot_chunks "${BEFORE}"

RESULTS="${TEST_DIR}/results.tsv"
: > "${RESULTS}"

for index in "${!TARGETS[@]}"; do
  target="${TARGETS[$index]}"; ordinal=$((index+1)); token="NR_R9_VILLAGE_LOCATE_DONE_${ordinal}"
  start_line=$(( $(wc -l < "${TEST_DIR}/server.log") + 1 )); started=$SECONDS
  echo "[NeverFolia][R9 village locate] ${ordinal}/${#TARGETS[@]} ${target}"
  send_console "execute in minecraft:overworld positioned ${ORIGIN_X} ${ORIGIN_Y} ${ORIGIN_Z} run locate structure ${target}"
  send_console "say ${token}"

  completed=0
  for _ in $(seq 1 "${COMMAND_TIMEOUT}"); do
    if tail -n +"${start_line}" "${TEST_DIR}/server.log" | grep -Fq -- "${token}"; then completed=1; break; fi
    if ! kill -0 "${SERVER_PID}" 2>/dev/null; then break; fi
    sleep 1
  done
  elapsed=$((SECONDS-started)); segment="${TEST_DIR}/segment-${ordinal}.log"
  tail -n +"${start_line}" "${TEST_DIR}/server.log" > "${segment}"

  if [ "${completed}" -ne 1 ]; then
    printf '%s\t%s\t%s\n' "${target}" "${elapsed}" 'TIMEOUT' >> "${RESULTS}"
    echo "[NeverFolia][R9 village locate] FAIL: ${target} did not complete within ${COMMAND_TIMEOUT}s" >&2
    tail -n 250 "${segment}" >&2 || true
    exit 1
  fi
  if grep -Eqi 'FoliaWatchdogThread|has not responded in [0-9]|NeverOverworldGeneratedVillageSafety\.preview|NeverOverworldGeneratedVillageSafety\.inspectBoundingBox|JigsawPlacement.*Stack|Command exception|StackOverflowError|OutOfMemoryError' "${segment}"; then
    printf '%s\t%s\t%s\n' "${target}" "${elapsed}" 'WATCHDOG_OR_UNBOUNDED' >> "${RESULTS}"
    echo "[NeverFolia][R9 village locate] FAIL: watchdog/unbounded preview signature while locating ${target}" >&2
    tail -n 250 "${segment}" >&2 || true
    exit 1
  fi

  status='FOUND'
  if grep -Eqi 'Could not find|Couldn.t find' "${segment}"; then status='NOT_FOUND'; fi
  if grep -Eqi 'Unknown registry|Unknown structure|Failed to execute|Incorrect argument' "${segment}"; then status='COMMAND_ERROR'; fi
  printf '%s\t%s\t%s\n' "${target}" "${elapsed}" "${status}" >> "${RESULTS}"
  echo "[NeverFolia][R9 village locate] ${target}: ${status} (${elapsed}s)"
done

send_console 'save-all flush'
sleep 5
snapshot_chunks "${AFTER}"
ANVIL_OK=1
if ! cmp -s "${BEFORE}" "${AFTER}"; then
  ANVIL_OK=0
  echo '[NeverFolia][R9 village locate] FAIL: locate created persisted Anvil records.' >&2
  diff -u "${BEFORE}" "${AFTER}" >&2 || true
fi

WATCHDOG_COUNT="$(grep -Eic 'FoliaWatchdogThread|has not responded in [0-9]' "${TEST_DIR}/server.log" || true)"
python3 - "${RESULTS}" "${BEFORE}" "${AFTER}" "${REPORT}" "${ANVIL_OK}" "${WATCHDOG_COUNT}" <<'PY'
import json, sys
from pathlib import Path
results_path,before_path,after_path,report_path=map(Path,sys.argv[1:5]); anvil_ok=sys.argv[5]=='1'; watchdog_count=int(sys.argv[6])
results=[]
for line in results_path.read_text(encoding='utf-8').splitlines():
    target,elapsed,status=line.split('\t',2)
    results.append({'target':target,'elapsed_seconds':int(elapsed),'status':status})
before=before_path.read_text(encoding='utf-8').splitlines(); after=after_path.read_text(encoding='utf-8').splitlines()
not_found=[r['target'] for r in results if r['status']=='NOT_FOUND']; errors=[r['target'] for r in results if r['status'] not in ('FOUND','NOT_FOUND')]
report={'status':'ok' if not not_found and not errors and anvil_ok and watchdog_count==0 else 'failed',
        'contract':'R9 bounded all-village locate + cartographer map tags','targets_checked':len(results),'command_timeout_seconds':20,
        'max_elapsed_seconds':max((r['elapsed_seconds'] for r in results),default=0),'watchdog_signatures':watchdog_count,
        'anvil_records_before':len(before),'anvil_records_after':len(after),'new_anvil_records_from_locate':sorted(set(after)-set(before)),
        'not_found_targets':not_found,'error_targets':errors,'results':results}
report_path.parent.mkdir(parents=True,exist_ok=True); report_path.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print('[NeverFolia][R9 village locate] MATRIX:',json.dumps(report,sort_keys=True))
if report['status']!='ok': raise SystemExit('R9 village locate matrix has unresolved targets')
PY

send_console 'stop'
for _ in $(seq 1 120); do if ! kill -0 "${SERVER_PID}" 2>/dev/null; then break; fi; sleep 1; done
cleanup_server

echo '[NeverFolia][R9 village locate] ALL 5 VILLAGES + 5 MAP TAGS BOUNDED / FOUND / ZERO-GENERATION / NO-WATCHDOG OK'
