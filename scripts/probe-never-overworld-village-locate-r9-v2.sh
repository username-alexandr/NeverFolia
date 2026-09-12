#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 2 ]; then
  echo "usage: $0 /path/to/NeverFolia.jar /path/to/NeverOverworld-Core.zip" >&2
  exit 2
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
JAR="$(realpath "$1")"
PACK="$(realpath "$2")"
TEST_DIR="${ROOT_DIR}/overworld-village-locate-r9-v2-test"
WORLD_DIR="${TEST_DIR}/world"
DATAPACK="${WORLD_DIR}/datapacks/NeverOverworld-Core.zip"
BEFORE="${TEST_DIR}/chunks-before-locate.txt"
AFTER_LOCATE="${TEST_DIR}/chunks-after-locate.txt"
RESULTS="${TEST_DIR}/results.tsv"
PREDICTIONS="${TEST_DIR}/direct-predictions.tsv"
REPORT="${ROOT_DIR}/artifacts/village-locate-r9-v2-proof.json"
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
server-port=25590
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
PIPE_PATH="console.pipe"; mkfifo "${PIPE_PATH}"
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
regions=[world/'dimensions'/'minecraft'/'overworld'/'region',world/'region']
region=next((p for p in regions if p.is_dir()),None)
if region is None: raise SystemExit(f'overworld region directory not found under {world}')
root=region.parent; rows=[]; pat=re.compile(r'^r\.(-?\d+)\.(-?\d+)\.mca$')
for kind in ('region','entities','poi'):
    d=root/kind
    if not d.is_dir(): continue
    for path in sorted(d.glob('r.*.*.mca')):
        m=pat.match(path.name)
        if not m: continue
        rx,rz=map(int,m.groups()); header=path.read_bytes()[:4096]
        for i in range(min(1024,len(header)//4)):
            if int.from_bytes(header[i*4:(i+1)*4],'big'):
                rows.append(f'{kind}:{rx*32+(i&31)},{rz*32+(i>>5)}')
out.write_text('\n'.join(sorted(rows))+('\n' if rows else ''),encoding='utf-8')
print(f'[NeverFolia][R9-v2 village locate] snapshot {out.name}: {len(rows)} Anvil records')
PY
}

for _ in $(seq 1 300); do
  if grep -q 'Done (' "${TEST_DIR}/server.log" 2>/dev/null; then break; fi
  if ! kill -0 "${SERVER_PID}" 2>/dev/null; then break; fi
  sleep 1
done
if ! grep -q 'Done (' "${TEST_DIR}/server.log" 2>/dev/null; then
  echo '[NeverFolia][R9-v2 village locate] server did not reach ready state.' >&2
  tail -n 300 "${TEST_DIR}/server.log" >&2 || true
  exit 1
fi
send_console 'execute in minecraft:overworld run gamerule minecraft:random_tick_speed 0'
send_console 'save-all flush'; sleep 5
snapshot_chunks "${BEFORE}"
: > "${RESULTS}"; : > "${PREDICTIONS}"

for index in "${!TARGETS[@]}"; do
  target="${TARGETS[$index]}"; ordinal=$((index+1)); token="NR_R9V2_LOCATE_DONE_${ordinal}"
  start_line=$(( $(wc -l < "${TEST_DIR}/server.log") + 1 )); started=$SECONDS
  echo "[NeverFolia][R9-v2 village locate] ${ordinal}/${#TARGETS[@]} ${target}"
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
  if [ "${completed}" -ne 1 ]; then echo "TIMEOUT ${target}" >&2; tail -n 250 "${segment}" >&2; exit 1; fi
  if grep -Eqi 'FoliaWatchdogThread|has not responded in [0-9]|NeverOverworldGeneratedVillageSafety\.preview|NeverOverworldGeneratedVillageSafety\.inspectBoundingBox|JigsawPlacement.*Stack|Command exception|StackOverflowError|OutOfMemoryError' "${segment}"; then
    echo "watchdog/unbounded signature for ${target}" >&2; tail -n 250 "${segment}" >&2; exit 1
  fi
  if grep -Eqi 'Could not find|Couldn.t find|Unknown registry|Unknown structure|Failed to execute|Incorrect argument' "${segment}"; then
    printf '%s\t%s\tNOT_FOUND\n' "${target}" "${elapsed}" >> "${RESULTS}"
    echo "[NeverFolia][R9-v2 village locate] NOT_FOUND ${target}" >&2
    continue
  fi
  printf '%s\t%s\tFOUND\n' "${target}" "${elapsed}" >> "${RESULTS}"
  if [ "${index}" -lt 5 ]; then
    python3 - "${segment}" "${target}" >> "${PREDICTIONS}" <<'PY'
import re,sys
from pathlib import Path
segment=Path(sys.argv[1]); target=sys.argv[2]
text=segment.read_text(errors='replace')
coord=re.compile(r'\[\s*(-?\d+)\s*,\s*[^,\]]+\s*,\s*(-?\d+)\s*\]')
matches=list(coord.finditer(text))
if not matches: raise SystemExit(f'could not parse locate coordinates for {target}\n{text}')
m=matches[-1]; x=int(m.group(1)); z=int(m.group(2))
print(f'{target}\t{x}\t{z}\t{x//16}\t{z//16}')
PY
  fi
done

if grep -q $'\tNOT_FOUND$' "${RESULTS}"; then
  echo '[NeverFolia][R9-v2 village locate] one or more targets were not found.' >&2
  cat "${RESULTS}" >&2
  exit 1
fi
if [ "$(wc -l < "${PREDICTIONS}")" -ne 5 ]; then
  echo 'expected five direct village predictions' >&2; cat "${PREDICTIONS}" >&2; exit 1
fi

send_console 'save-all flush'; sleep 5
snapshot_chunks "${AFTER_LOCATE}"
if ! cmp -s "${BEFORE}" "${AFTER_LOCATE}"; then
  echo '[NeverFolia][R9-v2 village locate] locate created Anvil records.' >&2
  diff -u "${BEFORE}" "${AFTER_LOCATE}" >&2 || true
  exit 1
fi

# Now explicitly generate each predicted direct-village start chunk. This occurs
# only after zero-generation locate has been proven above.
index=0
while IFS=$'\t' read -r target bx bz cx cz; do
  index=$((index+1)); token="NR_R9V2_FULL_${index}_${cx}_${cz}"
  echo "[NeverFolia][R9-v2 village locate] materialize ${target} at chunk ${cx},${cz}"
  send_console "execute in minecraft:overworld run forceload add ${bx} ${bz}"
  loaded=0
  for _ in $(seq 1 180); do
    send_console "execute in minecraft:overworld if loaded ${bx} 0 ${bz} run say ${token}"
    sleep 1
    if grep -Fq -- "${token}" "${TEST_DIR}/server.log" 2>/dev/null; then loaded=1; break; fi
    if ! kill -0 "${SERVER_PID}" 2>/dev/null; then break; fi
  done
  if [ "${loaded}" -ne 1 ]; then echo "predicted chunk ${cx},${cz} did not reach FULL" >&2; exit 1; fi
  send_console "execute in minecraft:overworld run forceload remove ${bx} ${bz}"
done < "${PREDICTIONS}"

send_console 'save-all flush'; sleep 5
send_console 'stop'
for _ in $(seq 1 120); do if ! kill -0 "${SERVER_PID}" 2>/dev/null; then break; fi; sleep 1; done
cleanup_server

python3 - "${ROOT_DIR}" "${WORLD_DIR}" "${PREDICTIONS}" "${RESULTS}" "${BEFORE}" "${AFTER_LOCATE}" "${REPORT}" <<'PY'
import importlib.util,json,sys
from pathlib import Path
root,world,preds_path,results_path,before_path,after_path,report_path=map(Path,sys.argv[1:])
raw_spec=importlib.util.spec_from_file_location('raw',root/'scripts/hash-never-nether-chunks.py'); raw=importlib.util.module_from_spec(raw_spec); raw_spec.loader.exec_module(raw)
over_spec=importlib.util.spec_from_file_location('over',root/'scripts/hash-never-overworld-generation-chunks.py'); over=importlib.util.module_from_spec(over_spec); over_spec.loader.exec_module(over)
region=over.find_region_dir(world)
proofs=[]
for line in preds_path.read_text().splitlines():
    target,bx,bz,cx,cz=line.split('\t'); cx=int(cx); cz=int(cz)
    chunk=raw.read_chunk_nbt(region,cx,cz); starts=((chunk.get('structures') or {}).get('starts') or {})
    start=starts.get(target); valid=start is not None and not (isinstance(start,dict) and str(start.get('id','')).upper()=='INVALID')
    proofs.append({'target':target,'predicted_chunk':[cx,cz],'persisted_start':valid,'start_id':start.get('id') if isinstance(start,dict) else None,'available_starts':sorted(map(str,starts.keys()))})
missing=[p['target'] for p in proofs if not p['persisted_start']]
results=[]
for line in results_path.read_text().splitlines():
    target,elapsed,status=line.split('\t'); results.append({'target':target,'elapsed_seconds':int(elapsed),'status':status})
before=before_path.read_text().splitlines(); after=after_path.read_text().splitlines()
report={'status':'ok' if not missing and all(r['status']=='FOUND' for r in results) and before==after else 'failed',
        'contract':'R9-v2 bounded locate + zero-generation + predicted direct village persists',
        'targets_checked':len(results),'max_elapsed_seconds':max(r['elapsed_seconds'] for r in results),
        'new_anvil_records_from_locate':sorted(set(after)-set(before)),'results':results,'direct_prediction_proofs':proofs,'missing_persisted_starts':missing}
report_path.parent.mkdir(parents=True,exist_ok=True); report_path.write_text(json.dumps(report,indent=2)+'\n')
print('[NeverFolia][R9-v2 village locate] PROOF:',json.dumps(report,sort_keys=True))
if report['status']!='ok': raise SystemExit('R9-v2 locate/persisted-start proof failed')
PY

if grep -Eqi 'FoliaWatchdogThread|has not responded in [0-9]' "${TEST_DIR}/server.log"; then
  echo '[NeverFolia][R9-v2 village locate] watchdog signature exists in runtime log.' >&2; exit 1
fi

echo '[NeverFolia][R9-v2 village locate] ALL TARGETS FOUND / ZERO-GENERATION / DIRECT PREDICTIONS PERSIST / NO-WATCHDOG OK'
