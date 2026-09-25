#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 2 ]; then
  echo "usage: $0 /path/to/NeverFolia.jar /path/to/NeverOverworld-Core.zip" >&2
  exit 2
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
JAR="$(realpath "$1")"
PACK="$(realpath "$2")"
TEST_DIR="${ROOT_DIR}/overworld-natural-structures-test"
WORLD_DIR="${TEST_DIR}/world"
DATAPACK="${WORLD_DIR}/datapacks/NeverOverworld-Core.zip"
CANDIDATES="${TEST_DIR}/ambient-candidates.txt"
SEED_TEXT='NeverOverworld-Natural-Structures-CI-1'

rm -rf "${TEST_DIR}"
mkdir -p "${WORLD_DIR}/datapacks"
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
server-port=25581
view-distance=2
simulation-distance=2
spawn-protection=0
max-tick-time=-1
enable-status=false
PROPS

# Reproduce Folia 26.2 RandomSpreadStructurePlacement exactly for the ambient
# set: spacing=22, separation=8, salt=1880479151, spread_type=linear.
python3 - "${SEED_TEXT}" > "${CANDIDATES}" <<'PY'
import sys
MASK48=(1<<48)-1
MULT=25214903917
ADD=11

def java_hash(text):
    h=0
    for ch in text:
        h=(31*h+ord(ch)) & 0xffffffff
    return h-(1<<32) if h & 0x80000000 else h

class LegacyRandom:
    def __init__(self, seed): self.seed=(seed ^ MULT) & MASK48
    def nxt(self,bits):
        self.seed=(self.seed*MULT+ADD)&MASK48
        return self.seed>>(48-bits)
    def next_int(self,bound):
        if bound & (bound-1) == 0:
            return (bound*self.nxt(31))>>31
        while True:
            bits=self.nxt(31); value=bits%bound
            check=(bits-value+(bound-1)) & 0xffffffff
            if check < 0x80000000:
                return value

def candidate(seed, cell_x, cell_z):
    spacing=22; separation=8; salt=1880479151
    mixed=(cell_x*341873128712 + cell_z*132897987541 + seed + salt) & ((1<<64)-1)
    if mixed >= (1<<63): mixed -= (1<<64)
    rng=LegacyRandom(mixed)
    bound=spacing-separation
    return cell_x*spacing+rng.next_int(bound), cell_z*spacing+rng.next_int(bound)

seed=java_hash(sys.argv[1])
for cz in range(-3,4):
    for cx in range(-3,4):
        x,z=candidate(seed,cx,cz)
        print(x,z)
PY

if [ "$(wc -l < "${CANDIDATES}")" -ne 49 ]; then
  echo 'candidate generator did not produce 49 ambient chunks' >&2
  exit 1
fi

echo '[NeverFolia][NeverOverworld structures] ambient candidate sample:'
head -n 8 "${CANDIDATES}"

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
  echo 'Natural-structure smoke server did not reach ready state.' >&2
  cat "${TEST_DIR}/server.log" >&2 || true
  exit 1
fi
send_console 'execute in minecraft:overworld run gamerule minecraft:random_tick_speed 0'

index=0
while read -r cx cz; do
  index=$((index+1))
  bx=$((cx*16+8)); bz=$((cz*16+8))
  token="NR_NATURAL_CANDIDATE_${index}_${cx}_${cz}"
  send_console "execute in minecraft:overworld run forceload add ${bx} ${bz}"
  for _ in $(seq 1 120); do
    send_console "execute in minecraft:overworld if loaded ${bx} 0 ${bz} run say ${token}"
    sleep 1
    if grep -Fq -- "${token}" "${TEST_DIR}/server.log" 2>/dev/null; then break; fi
    if ! kill -0 "${SERVER_PID}" 2>/dev/null; then break; fi
  done
  if ! grep -Fq -- "${token}" "${TEST_DIR}/server.log"; then
    echo "candidate chunk ${cx},${cz} did not reach FULL" >&2
    exit 1
  fi
  send_console "execute in minecraft:overworld run forceload remove ${bx} ${bz}"
done < "${CANDIDATES}"

sleep 3
send_console 'stop'
for _ in $(seq 1 90); do
  if ! kill -0 "${SERVER_PID}" 2>/dev/null; then break; fi
  sleep 1
done
cleanup_server

LOG="${TEST_DIR}/server.log"
if grep -Eqi "Failed to parse|Couldn't parse|Unknown registry|Errors in currently selected datapacks|Failed to load datapacks|Failed to load registries|Command exception|NullPointerException" "${LOG}"; then
  echo 'Natural-structure runtime error detected.' >&2
  cat "${LOG}" >&2
  exit 1
fi

python3 - "${ROOT_DIR}" "${WORLD_DIR}" "${CANDIDATES}" <<'PY'
import importlib.util
import json
import sys
from pathlib import Path

root=Path(sys.argv[1]); world=Path(sys.argv[2]); candidates=Path(sys.argv[3])
raw_spec=importlib.util.spec_from_file_location('raw_hasher', root/'scripts/hash-never-nether-chunks.py')
raw=importlib.util.module_from_spec(raw_spec); raw_spec.loader.exec_module(raw)
over_spec=importlib.util.spec_from_file_location('over_hasher', root/'scripts/hash-never-overworld-generation-chunks.py')
over=importlib.util.module_from_spec(over_spec); over_spec.loader.exec_module(over)
region=over.find_region_dir(world)
found=[]
for line in candidates.read_text().splitlines():
    cx,cz=map(int,line.split())
    try:
        chunk=raw.read_chunk_nbt(region,cx,cz)
    except FileNotFoundError:
        continue
    structures=chunk.get('structures') or {}
    starts=structures.get('starts') or {}
    for sid,start in starts.items():
        if not str(sid).startswith('neverfolia:'):
            continue
        if isinstance(start,dict) and str(start.get('id','')).upper() == 'INVALID':
            continue
        found.append({'chunk':[cx,cz],'structure':str(sid),'start_id':start.get('id') if isinstance(start,dict) else None})

out=root/'artifacts'/'natural-structure-starts.json'
out.parent.mkdir(parents=True,exist_ok=True)
out.write_text(json.dumps({'starts':found},indent=2)+'\n')
print('[NeverFolia][NeverOverworld structures] natural starts:', json.dumps(found,indent=2))
if not found:
    raise SystemExit('No natural neverfolia structure starts were generated in 49 exact ambient RandomSpread candidates')
PY

echo '[NeverFolia][NeverOverworld structures] NATURAL PLACEMENT PROBE OK'
