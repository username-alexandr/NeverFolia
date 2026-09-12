#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 4 ]; then
  echo "usage: $0 /path/to/NeverFolia.jar /path/to/NeverOverworld-Core.zip /output/dir source-sha" >&2
  exit 2
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
JAR="$(realpath "$1")"
PACK="$(realpath "$2")"
OUT_DIR="$(realpath -m "$3")"
SOURCE_SHA="$4"
TEST_DIR="${ROOT_DIR}/village-v4-bbox-test"
WORLD_DIR="${TEST_DIR}/world"
DATAPACK="${WORLD_DIR}/datapacks/NeverOverworld-Core.zip"
PREDICTIONS="${TEST_DIR}/predictions.tsv"
BBOXES="${TEST_DIR}/bboxes.tsv"
SEED_TEXT='NeverOverworld-R9-Village-Locate-CI-1'
ORIGIN_X=8192
ORIGIN_Y=200
ORIGIN_Z=8192
COMMAND_TIMEOUT=20
STRIPE_MAX_CHUNKS=8
STRIPE_TIMEOUT=180

VARIANTS=(plains desert savanna snowy taiga)

rm -rf "${TEST_DIR}"
mkdir -p "${WORLD_DIR}/datapacks" "${OUT_DIR}"
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
server-port=25591
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

start_server() {
  cleanup_server
  cd "${TEST_DIR}"
  PIPE_PATH="console.pipe"
  rm -f "${PIPE_PATH}"
  mkfifo "${PIPE_PATH}"
  tail -f /dev/null > "${PIPE_PATH}" & KEEPER_PID=$!
  java -Dneverfolia.debugVillageLocate=true -Xms1G -Xmx3G -jar "${JAR}" nogui < "${PIPE_PATH}" >> server.log 2>&1 & SERVER_PID=$!
  cd "${ROOT_DIR}"
  for _ in $(seq 1 300); do
    if grep -q 'Done (' "${TEST_DIR}/server.log" 2>/dev/null; then return 0; fi
    if ! kill -0 "${SERVER_PID}" 2>/dev/null; then break; fi
    sleep 1
  done
  echo '[NeverFolia][village v4 bbox] server did not reach ready state.' >&2
  tail -n 300 "${TEST_DIR}/server.log" >&2 || true
  return 1
}

send_console() { printf '%s\n' "$1" > "${TEST_DIR}/${PIPE_PATH}"; }

wait_loaded() {
  local x="$1" z="$2" token="$3" timeout="${4:-240}"
  for _ in $(seq 1 "${timeout}"); do
    send_console "execute in minecraft:overworld if loaded ${x} 128 ${z} run say ${token}"
    sleep 1
    if grep -Fq -- "${token}" "${TEST_DIR}/server.log" 2>/dev/null; then return 0; fi
    if ! kill -0 "${SERVER_PID}" 2>/dev/null; then break; fi
  done
  echo "[NeverFolia][village v4 bbox] FULL barrier timeout at ${x},${z}" >&2
  return 1
}

normal_stop() {
  send_console 'execute in minecraft:overworld run forceload remove all'
  sleep 2
  send_console stop
  for _ in $(seq 1 180); do
    if ! kill -0 "${SERVER_PID}" 2>/dev/null; then break; fi
    sleep 1
  done
  if kill -0 "${SERVER_PID}" 2>/dev/null; then
    echo '[NeverFolia][village v4 bbox] normal stop timeout' >&2
    return 1
  fi
  if [ -n "${KEEPER_PID}" ]; then kill "${KEEPER_PID}" 2>/dev/null || true; wait "${KEEPER_PID}" 2>/dev/null || true; fi
  if [ -n "${PIPE_PATH}" ]; then rm -f "${TEST_DIR}/${PIPE_PATH}"; fi
  SERVER_PID=""; KEEPER_PID=""; PIPE_PATH=""
}

# Phase 1: locate all five variants under the zero-generation predictor and
# materialize only the predicted start chunks. A normal stop then gives the NBT
# parser a consistent persisted StructureStart containing all Jigsaw child bboxes.
: > "${TEST_DIR}/server.log"
: > "${PREDICTIONS}"
start_server
send_console 'execute in minecraft:overworld run gamerule minecraft:random_tick_speed 0'

ordinal=0
for variant in "${VARIANTS[@]}"; do
  ordinal=$((ordinal + 1))
  target="minecraft:village_${variant}"
  token="NR_V4_BBOX_LOCATE_${ordinal}"
  start_line=$(( $(wc -l < "${TEST_DIR}/server.log") + 1 ))
  echo "[NeverFolia][village v4 bbox] locate ${target}"
  send_console "execute in minecraft:overworld positioned ${ORIGIN_X} ${ORIGIN_Y} ${ORIGIN_Z} run locate structure ${target}"
  send_console "say ${token}"
  completed=0
  for _ in $(seq 1 "${COMMAND_TIMEOUT}"); do
    if tail -n +"${start_line}" "${TEST_DIR}/server.log" | grep -Fq -- "${token}"; then completed=1; break; fi
    if ! kill -0 "${SERVER_PID}" 2>/dev/null; then break; fi
    sleep 1
  done
  segment="${TEST_DIR}/locate-${variant}.log"
  tail -n +"${start_line}" "${TEST_DIR}/server.log" > "${segment}"
  if [ "${completed}" -ne 1 ]; then
    echo "${target}: locate timeout" >&2; tail -n 250 "${segment}" >&2 || true; exit 1
  fi
  if grep -Eqi 'FoliaWatchdogThread|has not responded in [0-9]|NeverOverworldGeneratedVillageSafety\.preview|JigsawPlacement.*Stack|Command exception|Could not find|Couldn.t find' "${segment}"; then
    echo "${target}: locate failed/watchdog/unbounded path" >&2; tail -n 250 "${segment}" >&2 || true; exit 1
  fi
  python3 - "${segment}" "${target}" >> "${PREDICTIONS}" <<'PY'
import re,sys
from pathlib import Path
segment=Path(sys.argv[1]); target=sys.argv[2]
text=segment.read_text(errors='replace')
coord=re.compile(r'\[\s*(-?\d+)\s*,\s*[^,\]]+\s*,\s*(-?\d+)\s*\]')
matches=list(coord.finditer(text))
if not matches:
    raise SystemExit(f'cannot parse locate coordinates for {target}\n{text}')
m=matches[-1]; x=int(m.group(1)); z=int(m.group(2))
print(target,x,z,x//16,z//16,sep='\t')
PY

done

if [ "$(wc -l < "${PREDICTIONS}")" -ne 5 ]; then
  echo 'expected five direct village predictions' >&2; cat "${PREDICTIONS}" >&2; exit 1
fi

ordinal=0
while IFS=$'\t' read -r target bx bz cx cz; do
  ordinal=$((ordinal + 1)); token="NR_V4_BBOX_START_FULL_${ordinal}_${cx}_${cz}"
  echo "[NeverFolia][village v4 bbox] materialize start ${target} chunk=${cx},${cz}"
  send_console "execute in minecraft:overworld run forceload add ${bx} ${bz}"
  wait_loaded "${bx}" "${bz}" "${token}" 240
done < "${PREDICTIONS}"
normal_stop

# Resolve the true persisted bbox for every predicted start. The persisted start
# chunk already contains the complete Jigsaw Children[*].BB list. Phase 2 only
# needs chunks intersecting that exact bbox; no extra one-chunk rectangle margin
# is required by the water-at-Y=128 audit.
python3 - "${ROOT_DIR}" "${WORLD_DIR}" "${PREDICTIONS}" "${BBOXES}" <<'PY'
import importlib.util,sys
from pathlib import Path
root,world,preds,out=map(Path,sys.argv[1:])
over_spec=importlib.util.spec_from_file_location('over',root/'scripts/hash-never-overworld-generation-chunks.py')
over=importlib.util.module_from_spec(over_spec); over_spec.loader.exec_module(over)
raw=over.BASE; region=over.find_region_dir(world)

def int_array(value):
    if isinstance(value,dict): value=value.get('$int_array')
    if isinstance(value,list) and len(value)==6 and all(isinstance(v,int) for v in value): return value
    return None

def boxes(value):
    result=[]
    if isinstance(value,dict):
        for k,v in value.items():
            if str(k).lower() in {'bb','boundingbox','bounding_box'}:
                b=int_array(v)
                if b is not None: result.append(b)
            result.extend(boxes(v))
    elif isinstance(value,list):
        for v in value: result.extend(boxes(v))
    return result

rows=[]
for line in preds.read_text().splitlines():
    target,bx,bz,cx,cz=line.split('\t'); cx=int(cx); cz=int(cz)
    found=None
    for radius in range(0,13):
        for dz in range(-radius,radius+1):
            for dx in range(-radius,radius+1):
                if radius and abs(dx)!=radius and abs(dz)!=radius: continue
                try: chunk=raw.read_chunk_nbt(region,cx+dx,cz+dz)
                except Exception: continue
                starts=((chunk.get('structures') or {}).get('starts') or {})
                start=starts.get(target)
                if isinstance(start,dict) and str(start.get('id','')).upper()!='INVALID':
                    found=(cx+dx,cz+dz,start); break
            if found: break
        if found: break
    if not found: raise SystemExit(f'{target}: persisted start missing near {cx},{cz}')
    scx,scz,start=found; bb=boxes(start)
    if not bb: raise SystemExit(f'{target}: no persisted child bbox')
    minx=min(b[0] for b in bb); miny=min(b[1] for b in bb); minz=min(b[2] for b in bb)
    maxx=max(b[3] for b in bb); maxy=max(b[4] for b in bb); maxz=max(b[5] for b in bb)
    cminx=minx//16; cminz=minz//16; cmaxx=maxx//16; cmaxz=maxz//16
    count=(cmaxx-cminx+1)*(cmaxz-cminz+1)
    if count>256: raise SystemExit(f'{target}: exact bbox materialization too large: {count} chunks')
    rows.append((target,int(bx),int(bz),int(cx),int(cz),scx,scz,minx,miny,minz,maxx,maxy,maxz,cminx,cminz,cmaxx,cmaxz,count))
out.write_text('\n'.join('\t'.join(map(str,row)) for row in rows)+'\n')
for row in rows: print('[NeverFolia][village v4 bbox] resolved',row)
PY

# Phase 2: materialize the exact bbox in bounded horizontal stripes. At most
# STRIPE_MAX_CHUNKS are forceloaded per batch, then immediately released. This
# avoids the old 80-144 chunk simultaneous generation burst that timed out the
# FULL barrier before the water audit could run.
start_server
ordinal=0
while IFS=$'\t' read -r target bx bz cx cz scx scz minx miny minz maxx maxy maxz cminx cminz cmaxx cmaxz count; do
  ordinal=$((ordinal + 1))
  echo "[NeverFolia][village v4 bbox] materialize exact bbox ${target}: ${minx},${minz}..${maxx},${maxz} chunks=${count} stripe_max=${STRIPE_MAX_CHUNKS}"
  stripe_id=0
  for ((czrow=cminz; czrow<=cmaxz; czrow++)); do
    sx=${cminx}
    while [ "${sx}" -le "${cmaxx}" ]; do
      ex=$((sx + STRIPE_MAX_CHUNKS - 1))
      if [ "${ex}" -gt "${cmaxx}" ]; then ex=${cmaxx}; fi
      x1=$((sx*16)); z1=$((czrow*16)); x2=$((ex*16+15)); z2=$((czrow*16+15))
      stripe_id=$((stripe_id + 1))
      token="NR_V4_BBOX_${ordinal}_STRIPE_${stripe_id}_${ex}_${czrow}"
      echo "[NeverFolia][village v4 bbox] stripe ${target} row=${czrow} chunks=${sx}..${ex}"
      send_console "execute in minecraft:overworld run forceload add ${x1} ${z1} ${x2} ${z2}"
      wait_loaded "${x2}" "${z2}" "${token}" "${STRIPE_TIMEOUT}"
      send_console "execute in minecraft:overworld run forceload remove ${x1} ${z1} ${x2} ${z2}"
      sx=$((ex + 1))
    done
  done
done < "${BBOXES}"
normal_stop

mkdir -p "${OUT_DIR}"
while IFS=$'\t' read -r target bx bz cx cz scx scz minx miny minz maxx maxy maxz cminx cminz cmaxx cmaxz count; do
  variant="${target#minecraft:village_}"
  printf '%s\t%s\t%s\t%s\t%s\n' "${target}" "${bx}" "${bz}" "${cx}" "${cz}" > "${TEST_DIR}/locate-${variant}.tsv"
  python3 "${ROOT_DIR}/scripts/audit-never-overworld-village-persisted-bbox.py" \
    --root "${ROOT_DIR}" \
    --world "${WORLD_DIR}" \
    --locate "${TEST_DIR}/locate-${variant}.tsv" \
    --output "${OUT_DIR}/${variant}-persisted-bbox.json" \
    --source-sha "${SOURCE_SHA}"
done < "${BBOXES}"

cp "${PREDICTIONS}" "${OUT_DIR}/predictions.tsv"
cp "${BBOXES}" "${OUT_DIR}/bboxes.tsv"
cp "${TEST_DIR}/server.log" "${OUT_DIR}/server.log"

if grep -Eqi 'FoliaWatchdogThread|has not responded in [0-9]' "${TEST_DIR}/server.log"; then
  echo '[NeverFolia][village v4 bbox] watchdog signature exists in runtime log.' >&2
  exit 1
fi

echo '[NeverFolia][village v4 bbox] ALL 5 PERSISTED VILLAGE BBOXES WATER=0 / NO-WATCHDOG OK'
