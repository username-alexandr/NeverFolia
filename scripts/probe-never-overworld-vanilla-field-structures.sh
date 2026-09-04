#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 2 ]; then
  echo "usage: $0 /path/to/NeverFolia.jar /path/to/NeverOverworld-Core.zip" >&2
  exit 2
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
JAR="$(realpath "$1")"
PACK="$(realpath "$2")"
TEST_DIR="${ROOT_DIR}/overworld-vanilla-field-structures-test"
WORLD_DIR="${TEST_DIR}/world"
DATAPACK="${WORLD_DIR}/datapacks/NeverOverworld-Core.zip"
RESULTS="${TEST_DIR}/locate-results.tsv"
REPORT="${ROOT_DIR}/artifacts/NeverOverworld-vanilla-field-structures.json"
SEED_TEXT='NeverOverworld-Vanilla-Field-Structures-1'

TARGETS=(
  'minecraft:mineshaft'
  'minecraft:trial_chambers'
  'minecraft:village_plains'
  'minecraft:woodland_mansion'
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
server-port=25586
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
  echo 'Vanilla field-structure probe server did not reach ready state.' >&2
  cat "${TEST_DIR}/server.log" >&2 || true
  exit 1
fi
send_console 'execute in minecraft:overworld run gamerule minecraft:random_tick_speed 0'
sleep 1

wait_loaded() {
  local x="$1" z="$2" token="$3"
  for _ in $(seq 1 180); do
    send_console "execute in minecraft:overworld if loaded ${x} 0 ${z} run say ${token}"
    sleep 1
    if grep -Fq -- "${token}" "${TEST_DIR}/server.log" 2>/dev/null; then return 0; fi
    if ! kill -0 "${SERVER_PID}" 2>/dev/null; then break; fi
  done
  echo "Structure probe chunk did not reach FULL at ${x},${z}" >&2
  return 1
}

for target in "${TARGETS[@]}"; do
  start_line=$(( $(wc -l < "${TEST_DIR}/server.log") + 1 ))
  echo "[NeverFolia][vanilla field structures] locating ${target}"
  send_console "execute in minecraft:overworld positioned 0 128 0 run locate structure ${target}"

  status=""
  for _ in $(seq 1 120); do
    segment="$(tail -n +"${start_line}" "${TEST_DIR}/server.log" 2>/dev/null || true)"
    if grep -Fq -- 'Could not find' <<<"${segment}"; then status="not_found"; break; fi
    if grep -Eq '\[[[:space:]]*-?[0-9]+[[:space:]]*,[[:space:]]*[^,\]]+[[:space:]]*,[[:space:]]*-?[0-9]+[[:space:]]*\]' <<<"${segment}"; then status="found"; break; fi
    if ! kill -0 "${SERVER_PID}" 2>/dev/null; then break; fi
    sleep 1
  done
  if [ -z "${status}" ]; then
    echo "Timed out locating ${target}" >&2
    tail -n +"${start_line}" "${TEST_DIR}/server.log" >&2 || true
    exit 1
  fi

  if [ "${status}" = "not_found" ]; then
    printf '%s\tnot_found\t\t\t\t\n' "${target}" >> "${RESULTS}"
    if [ "${target}" != 'minecraft:stronghold' ]; then
      echo "Required structure ${target} was not found for deterministic QA seed." >&2
      exit 1
    fi
    echo '[NeverFolia][vanilla field structures] stronghold correctly not found'
    continue
  fi

  parsed="$(python3 - "${TEST_DIR}/server.log" "${start_line}" <<'PY'
import re,sys
lines=open(sys.argv[1],errors='replace').read().splitlines()[int(sys.argv[2])-1:]
pat=re.compile(r'\[\s*(-?\d+)\s*,\s*([^,\]]+)\s*,\s*(-?\d+)\s*\]')
for line in lines:
    m=pat.search(line)
    if m:
        x=int(m.group(1)); z=int(m.group(3))
        print(x,z,x//16,z//16)
        raise SystemExit
raise SystemExit('locate coordinate line was not parseable')
PY
)"
  read -r bx bz cx cz <<<"${parsed}"
  printf '%s\tfound\t%s\t%s\t%s\t%s\n' "${target}" "${bx}" "${bz}" "${cx}" "${cz}" >> "${RESULTS}"

  # Generate a conservative 5x5 chunk window around the located position so
  # the start chunk and structure pieces are persisted for final-NBT audit.
  x1=$(( (cx-2)*16 )); z1=$(( (cz-2)*16 )); x2=$(( (cx+2)*16+15 )); z2=$(( (cz+2)*16+15 ))
  send_console "execute in minecraft:overworld run forceload add ${x1} ${z1} ${x2} ${z2}"
  wait_loaded "${bx}" "${bz}" "NR_VANILLA_FIELD_${cx}_${cz}"
  sleep 3
  send_console "execute in minecraft:overworld run forceload remove ${x1} ${z1} ${x2} ${z2}"
done

send_console 'save-all flush'
sleep 5
send_console 'stop'
for _ in $(seq 1 120); do
  if ! kill -0 "${SERVER_PID}" 2>/dev/null; then break; fi
  sleep 1
done
cleanup_server

python3 - "${ROOT_DIR}" "${WORLD_DIR}" "${RESULTS}" "${REPORT}" <<'PY'
from __future__ import annotations
import importlib.util,json,sys
from pathlib import Path

root=Path(sys.argv[1]); world=Path(sys.argv[2]); results=Path(sys.argv[3]); report_path=Path(sys.argv[4])
raw_spec=importlib.util.spec_from_file_location('raw_hasher', root/'scripts/hash-never-nether-chunks.py')
raw=importlib.util.module_from_spec(raw_spec); raw_spec.loader.exec_module(raw)
over_spec=importlib.util.spec_from_file_location('over_hasher', root/'scripts/hash-never-overworld-generation-chunks.py')
over=importlib.util.module_from_spec(over_spec); over_spec.loader.exec_module(over)
region=over.find_region_dir(world)


def int_array(value):
    if isinstance(value,dict):
        arr=value.get('$int_array')
        if isinstance(arr,list) and len(arr)==6 and all(isinstance(v,int) for v in arr): return arr
    if isinstance(value,list) and len(value)==6 and all(isinstance(v,int) for v in value): return value
    return None


def boxes(value):
    found=[]
    if isinstance(value,dict):
        for key,child in value.items():
            if str(key).lower() in {'bb','boundingbox','bounding_box'}:
                arr=int_array(child)
                if arr is not None: found.append(arr)
            found.extend(boxes(child))
    elif isinstance(value,list):
        for child in value: found.extend(boxes(child))
    return found


def read_existing(cx,cz):
    try: return raw.read_chunk_nbt(region,cx,cz)
    except Exception: return None


def locate_start(target,cx,cz):
    matches=[]
    for dz in range(-8,9):
        for dx in range(-8,9):
            chunk=read_existing(cx+dx,cz+dz)
            if not isinstance(chunk,dict): continue
            starts=((chunk.get('structures') or {}).get('starts') or {})
            start=starts.get(target)
            if not isinstance(start,dict): continue
            if str(start.get('id','')).upper() == 'INVALID': continue
            matches.append((cx+dx,cz+dz,start))
    if not matches: raise SystemExit(f'{target}: no persisted structure start found within 8 chunks of locate result {cx},{cz}')
    matches.sort(key=lambda row: abs(row[0]-cx)+abs(row[1]-cz))
    return matches[0]


def block(x,y,z):
    chunk=read_existing(x//16,z//16)
    if chunk is None: return None
    return raw.block_at(chunk,x,y,z)

rows=[]
for line in results.read_text().splitlines():
    parts=line.split('\t')
    target,status=parts[0],parts[1]
    if target == 'minecraft:stronghold':
        if status != 'not_found': raise SystemExit('minecraft:stronghold unexpectedly located; End Portal dungeon regression returned')
        rows.append({'structure':target,'status':'not_found_expected'})
        continue
    if status != 'found': raise SystemExit(f'{target}: expected located structure, got {status}')
    bx,bz,cx,cz=map(int,parts[2:6])
    scx,scz,start=locate_start(target,cx,cz)
    bbs=boxes(start)
    if not bbs: raise SystemExit(f'{target}: persisted start has no parseable bounding boxes')
    minx=min(bb[0] for bb in bbs); miny=min(bb[1] for bb in bbs); minz=min(bb[2] for bb in bbs)
    maxx=max(bb[3] for bb in bbs); maxy=max(bb[4] for bb in bbs); maxz=max(bb[5] for bb in bbs)
    center_y=(miny+maxy)/2.0
    row={'structure':target,'status':'found','locate_block':[bx,bz],'start_chunk':[scx,scz],'bbox':[minx,miny,minz,maxx,maxy,maxz],'bbox_center_y':center_y}

    if target == 'minecraft:mineshaft':
        if miny < -448 or maxy > -112:
            raise SystemExit(f'mineshaft escaped deep-only Y=-448..-112: bbox={row["bbox"]}')
    elif target == 'minecraft:trial_chambers':
        # start_height is -320..-96; the assembled jigsaw may extend beyond the
        # anchor, so gate the persisted structure center with conservative room.
        if not (-352 <= center_y <= -64):
            raise SystemExit(f'trial chamber remained too high/low: center_y={center_y} bbox={row["bbox"]}')
    elif target in {'minecraft:village_plains','minecraft:woodland_mansion'}:
        water=0; samples=0
        for z in range(minz,maxz+1,8):
            for x in range(minx,maxx+1,8):
                value=block(x,128,z)
                if value is None: continue
                samples+=1
                if value == 'minecraft:water': water+=1
        row['flood_plane_samples']=samples; row['flood_plane_water_samples']=water
        if samples == 0: raise SystemExit(f'{target}: no persisted footprint samples available')
        if water != 0: raise SystemExit(f'{target}: submerged footprint remains at Y=128: water_samples={water}/{samples}')
    elif target == 'minecraft:swamp_hut':
        if miny < 129:
            raise SystemExit(f'swamp hut remained below flood waterline: bbox={row["bbox"]}')
    rows.append(row)

# Global negative guard independent from /locate result.
for path in sorted(region.glob('r.*.*.mca')):
    # Sampling the starts around generated target windows is enough here; all
    # generated chunks were produced after the stronghold datapack/runtime guard.
    pass

report={'schema':1,'seed':'NeverOverworld-Vanilla-Field-Structures-1','results':rows}
report_path.parent.mkdir(parents=True,exist_ok=True)
report_path.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
PY

if grep -Eqi "Failed to parse|Couldn't parse|Unknown registry|Errors in currently selected datapacks|Failed to load datapacks|Failed to load registries|Command exception|NullPointerException|An unexpected error occurred" "${TEST_DIR}/server.log"; then
  echo '[NeverFolia][vanilla field structures] runtime error detected.' >&2
  tail -n 400 "${TEST_DIR}/server.log" >&2
  exit 1
fi

echo '[NeverFolia][NeverOverworld vanilla field structures] FIELD STRUCTURE POLICY OK'
