#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 2 ]; then
  echo "usage: $0 /path/to/NeverFolia.jar /path/to/NeverOverworld-Core.zip" >&2
  exit 2
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
JAR="$(realpath "$1")"
PACK="$(realpath "$2")"
TEST_DIR="${ROOT_DIR}/overworld-shoreline-flora-test"
WORLD_DIR="${TEST_DIR}/world"
DATAPACK="${WORLD_DIR}/datapacks/NeverOverworld-Core.zip"
RESULTS="${TEST_DIR}/biome-results.tsv"
REPORT="${ROOT_DIR}/artifacts/NeverOverworld-shoreline-flora.json"
SEED_TEXT='NeverOverworld-Shoreline-Flora-1'

TARGET_BIOMES=(
  'minecraft:swamp'
  'minecraft:river'
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
server-port=25587
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
java -Xms1G -Xmx3G -jar "${JAR}" nogui < "${PIPE_PATH}" > server.log 2>&1 & SERVER_PID=$!
cd "${ROOT_DIR}"
send_console() { printf '%s\n' "$1" > "${TEST_DIR}/${PIPE_PATH}"; }

for _ in $(seq 1 300); do
  if grep -q 'Done (' "${TEST_DIR}/server.log" 2>/dev/null; then break; fi
  if ! kill -0 "${SERVER_PID}" 2>/dev/null; then break; fi
  sleep 1
done
if ! grep -q 'Done (' "${TEST_DIR}/server.log" 2>/dev/null; then
  echo 'Shoreline-flora probe server did not reach ready state.' >&2
  cat "${TEST_DIR}/server.log" >&2 || true
  exit 1
fi
send_console 'execute in minecraft:overworld run gamerule minecraft:random_tick_speed 0'
sleep 1

wait_loaded() {
  local x="$1" z="$2" token="$3"
  for _ in $(seq 1 240); do
    send_console "execute in minecraft:overworld if loaded ${x} 128 ${z} run say ${token}"
    sleep 1
    if grep -Fq -- "${token}" "${TEST_DIR}/server.log" 2>/dev/null; then return 0; fi
    if ! kill -0 "${SERVER_PID}" 2>/dev/null; then break; fi
  done
  echo "Flora probe area did not reach FULL near ${x},${z}" >&2
  return 1
}

for biome in "${TARGET_BIOMES[@]}"; do
  start_line=$(( $(wc -l < "${TEST_DIR}/server.log") + 1 ))
  echo "[NeverFolia][shoreline flora] locating ${biome}"
  send_console "execute in minecraft:overworld positioned 0 128 0 run locate biome ${biome}"
  status=""
  for _ in $(seq 1 180); do
    segment="$(tail -n +"${start_line}" "${TEST_DIR}/server.log" 2>/dev/null || true)"
    if grep -Fq -- 'Could not find' <<<"${segment}"; then status="not_found"; break; fi
    if grep -Fq -- "The nearest ${biome} is at [" <<<"${segment}"; then status="found"; break; fi
    if ! kill -0 "${SERVER_PID}" 2>/dev/null; then break; fi
    sleep 1
  done
  if [ "${status}" != 'found' ]; then
    echo "Could not locate required biome ${biome} for shoreline flora QA." >&2
    tail -n +"${start_line}" "${TEST_DIR}/server.log" >&2 || true
    exit 1
  fi

  parsed="$(python3 - "${TEST_DIR}/server.log" "${start_line}" <<'PY'
import re,sys
lines=open(sys.argv[1],errors='replace').read().splitlines()[int(sys.argv[2])-1:]
pat=re.compile(r'\[\s*(-?\d+)\s*,\s*([^,\]]+)\s*,\s*(-?\d+)\s*\]')
for line in lines:
    m=pat.search(line)
    if m:
        x=int(m.group(1)); z=int(m.group(3)); print(x,z,x//16,z//16); raise SystemExit
raise SystemExit('biome locate coordinate line was not parseable')
PY
)"
  read -r bx bz cx cz <<<"${parsed}"
  printf '%s\t%s\t%s\t%s\t%s\n' "${biome}" "${bx}" "${bz}" "${cx}" "${cz}" >> "${RESULTS}"

  # Generate a 9x9 chunk square around the biome hit. This stays far below the
  # vanilla forceload 256-chunk command limit while giving old vanilla FEATURES
  # enough samples to contain swamp lilies and river-bank sugar cane.
  x1=$(( (cx-4)*16 )); z1=$(( (cz-4)*16 )); x2=$(( (cx+4)*16+15 )); z2=$(( (cz+4)*16+15 ))
  send_console "execute in minecraft:overworld run forceload add ${x1} ${z1} ${x2} ${z2}"
  wait_loaded "${bx}" "${bz}" "NR_FLORA_${cx}_${cz}"
  sleep 8
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

centers=[]
for line in results.read_text().splitlines():
    biome,bx,bz,cx,cz=line.split('\t')
    centers.append((biome,int(cx),int(cz)))

counts={'minecraft:lily_pad':0,'minecraft:sugar_cane':0}
by_biome={biome:{'lily_pad':0,'sugar_cane':0,'chunks_scanned':0} for biome,_,_ in centers}
samples=[]
seen=set()
for biome,cx,cz in centers:
    for dz in range(-4,5):
        for dx in range(-4,5):
            key=(cx+dx,cz+dz)
            if key in seen:
                continue
            seen.add(key)
            try: chunk=raw.read_chunk_nbt(region,*key)
            except Exception: continue
            status=str(chunk.get('Status') or chunk.get('status') or '').lower()
            if status not in {'full','minecraft:full'}: continue
            by_biome[biome]['chunks_scanned'] += 1
            base_x=key[0]*16; base_z=key[1]*16
            for z in range(base_z+1,base_z+15):
                for x in range(base_x+1,base_x+15):
                    below=raw.block_at(chunk,x,128,z)
                    lily=raw.block_at(chunk,x,129,z)
                    if lily == 'minecraft:lily_pad' and below == 'minecraft:water':
                        counts['minecraft:lily_pad'] += 1
                        by_biome[biome]['lily_pad'] += 1
                        if len(samples)<50: samples.append({'block':lily,'pos':[x,129,z],'biome_probe':biome})
                    for y in range(129,132):
                        cane=raw.block_at(chunk,x,y,z)
                        if cane == 'minecraft:sugar_cane':
                            counts['minecraft:sugar_cane'] += 1
                            by_biome[biome]['sugar_cane'] += 1
                            if len(samples)<50: samples.append({'block':cane,'pos':[x,y,z],'biome_probe':biome})

report={
    'schema':1,
    'seed':'NeverOverworld-Shoreline-Flora-1',
    'flood_y':128,
    'target_biomes':[row[0] for row in centers],
    'counts':counts,
    'by_probe':by_biome,
    'samples':samples,
}
report_path.parent.mkdir(parents=True,exist_ok=True)
report_path.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
if counts['minecraft:lily_pad'] <= 0:
    raise SystemExit('no relocated lily pads found at Y=129 in targeted swamp/river QA sample')
if counts['minecraft:sugar_cane'] <= 0:
    raise SystemExit('no relocated sugar cane found at Y=129..131 in targeted swamp/river QA sample')
PY

if grep -Eqi "Failed to parse|Couldn't parse|Unknown registry|Errors in currently selected datapacks|Failed to load datapacks|Failed to load registries|Command exception|NullPointerException|An unexpected error occurred" "${TEST_DIR}/server.log"; then
  echo '[NeverFolia][shoreline flora] runtime error detected.' >&2
  tail -n 400 "${TEST_DIR}/server.log" >&2
  exit 1
fi

echo '[NeverFolia][NeverOverworld shoreline flora] POSITIVE RELOCATION QA OK'
