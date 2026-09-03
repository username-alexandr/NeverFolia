#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 2 ]; then
  echo "usage: $0 /path/to/NeverFolia.jar /path/to/NeverOverworld-Core.zip" >&2
  exit 2
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
JAR="$(realpath "$1")"
PACK="$(realpath "$2")"
TEST_DIR="${ROOT_DIR}/overworld-fast-locate-test"
WORLD_DIR="${TEST_DIR}/world"
DATAPACK="${WORLD_DIR}/datapacks/NeverOverworld-Core.zip"
STRUCTURE_ID="neverfolia:prospector_camp"
ORIGIN_X=8192
ORIGIN_Y=64
ORIGIN_Z=8192
SEED_TEXT='NeverOverworld-Fast-Locate-CI-1'
BEFORE="${TEST_DIR}/chunks-before-locate.txt"
AFTER="${TEST_DIR}/chunks-after-locate.txt"
PREDICTION="${TEST_DIR}/prediction.json"
PROOF="${ROOT_DIR}/artifacts/fast-locate-proof.json"

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
server-port=25582
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
  if [ -n "${SERVER_PID}" ]; then
    kill "${SERVER_PID}" 2>/dev/null || true
    wait "${SERVER_PID}" 2>/dev/null || true
  fi
  if [ -n "${KEEPER_PID}" ]; then
    kill "${KEEPER_PID}" 2>/dev/null || true
    wait "${KEEPER_PID}" 2>/dev/null || true
  fi
  if [ -n "${PIPE_PATH}" ]; then
    rm -f "${TEST_DIR}/${PIPE_PATH}"
  fi
  SERVER_PID=""
  KEEPER_PID=""
  PIPE_PATH=""
}
trap cleanup_server EXIT

cd "${TEST_DIR}"
PIPE_PATH="console.pipe"
mkfifo "${PIPE_PATH}"
tail -f /dev/null > "${PIPE_PATH}" &
KEEPER_PID=$!
java -Xms1G -Xmx2G -jar "${JAR}" nogui < "${PIPE_PATH}" > server.log 2>&1 &
SERVER_PID=$!
cd "${ROOT_DIR}"

send_console() {
  printf '%s\n' "$1" > "${TEST_DIR}/${PIPE_PATH}"
}

wait_literal() {
  local literal="$1"
  local timeout="$2"
  for _ in $(seq 1 "${timeout}"); do
    if grep -Fq -- "${literal}" "${TEST_DIR}/server.log" 2>/dev/null; then
      return 0
    fi
    if ! kill -0 "${SERVER_PID}" 2>/dev/null; then
      break
    fi
    sleep 1
  done
  echo "Timed out waiting for: ${literal}" >&2
  tail -n 250 "${TEST_DIR}/server.log" >&2 || true
  return 1
}

snapshot_chunks() {
  local output="$1"
  python3 - "${WORLD_DIR}" "${output}" <<'PY'
import re
import sys
from pathlib import Path

world = Path(sys.argv[1])
out = Path(sys.argv[2])
region_candidates = [
    world / 'dimensions' / 'minecraft' / 'overworld' / 'region',
    world / 'region',
]
region_dir = next((p for p in region_candidates if p.is_dir()), None)
if region_dir is None:
    raise SystemExit(f'Overworld region directory not found under {world}')
dim_root = region_dir.parent
rows = []
pattern = re.compile(r'^r\.(-?\d+)\.(-?\d+)\.mca$')
for kind in ('region', 'entities', 'poi'):
    directory = dim_root / kind
    if not directory.is_dir():
        continue
    for path in sorted(directory.glob('r.*.*.mca')):
        match = pattern.match(path.name)
        if not match:
            continue
        rx, rz = map(int, match.groups())
        header = path.read_bytes()[:4096]
        if len(header) < 4096:
            continue
        for index in range(1024):
            entry = header[index * 4:(index + 1) * 4]
            if int.from_bytes(entry, 'big') == 0:
                continue
            lx = index % 32
            lz = index // 32
            rows.append(f'{kind}:{rx * 32 + lx},{rz * 32 + lz}')
out.write_text('\n'.join(sorted(rows)) + ('\n' if rows else ''), encoding='utf-8')
print(f'[NeverFolia][fast locate probe] snapshot {out.name}: {len(rows)} Anvil records')
PY
}

for _ in $(seq 1 300); do
  if grep -q 'Done (' "${TEST_DIR}/server.log" 2>/dev/null; then
    break
  fi
  if ! kill -0 "${SERVER_PID}" 2>/dev/null; then
    break
  fi
  sleep 1
done
if ! grep -q 'Done (' "${TEST_DIR}/server.log" 2>/dev/null; then
  echo 'Fast-locate server did not reach ready state.' >&2
  cat "${TEST_DIR}/server.log" >&2 || true
  exit 1
fi

send_console 'execute in minecraft:overworld run gamerule minecraft:random_tick_speed 0'
send_console 'save-all flush'
sleep 5
snapshot_chunks "${BEFORE}"

START_LINE=$(( $(wc -l < "${TEST_DIR}/server.log") + 1 ))
LOCATE_COMMAND="execute in minecraft:overworld positioned ${ORIGIN_X} ${ORIGIN_Y} ${ORIGIN_Z} run locate structure ${STRUCTURE_ID}"
echo "[NeverFolia][fast locate probe] ${LOCATE_COMMAND}"
send_console "${LOCATE_COMMAND}"

for _ in $(seq 1 120); do
  if tail -n +"${START_LINE}" "${TEST_DIR}/server.log" | grep -Fq -- "${STRUCTURE_ID}"; then
    break
  fi
  if ! kill -0 "${SERVER_PID}" 2>/dev/null; then
    break
  fi
  sleep 1
done

python3 - "${TEST_DIR}/server.log" "${START_LINE}" "${STRUCTURE_ID}" "${PREDICTION}" <<'PY'
import json
import re
import sys
from pathlib import Path

log = Path(sys.argv[1])
start_line = int(sys.argv[2])
structure_id = sys.argv[3]
out = Path(sys.argv[4])
lines = log.read_text(errors='replace').splitlines()[start_line - 1:]
matching = [line for line in lines if structure_id in line]
coord_re = re.compile(r'\[\s*(-?\d+)\s*,\s*([^,\]]+)\s*,\s*(-?\d+)\s*\]')
parsed = None
for line in reversed(matching):
    match = coord_re.search(line)
    if match:
        x = int(match.group(1))
        z = int(match.group(3))
        parsed = {
            'structure': structure_id,
            'block_x': x,
            'block_z': z,
            'chunk_x': x // 16,
            'chunk_z': z // 16,
            'feedback': line,
        }
        break
if parsed is None:
    raise SystemExit('Could not parse /locate coordinates for ' + structure_id + '\n' + '\n'.join(matching[-20:]))
out.write_text(json.dumps(parsed, indent=2) + '\n', encoding='utf-8')
print('[NeverFolia][fast locate probe] prediction:', json.dumps(parsed, sort_keys=True))
PY

send_console 'save-all flush'
sleep 5
snapshot_chunks "${AFTER}"

if ! cmp -s "${BEFORE}" "${AFTER}"; then
  echo '[NeverFolia][fast locate probe] FAIL: /locate changed persisted Anvil chunk records.' >&2
  echo '--- before/after diff ---' >&2
  diff -u "${BEFORE}" "${AFTER}" >&2 || true
  exit 1
fi

eval "$(python3 - "${PREDICTION}" <<'PY'
import json, shlex, sys
p=json.load(open(sys.argv[1]))
for key in ('block_x','block_z','chunk_x','chunk_z'):
    print(f'P_{key.upper()}={shlex.quote(str(p[key]))}')
PY
)"

if grep -Fqx -- "region:${P_CHUNK_X},${P_CHUNK_Z}" "${BEFORE}"; then
  echo "[NeverFolia][fast locate probe] FAIL: predicted chunk ${P_CHUNK_X},${P_CHUNK_Z} already existed before /locate; proof would be ambiguous." >&2
  exit 1
fi

echo "[NeverFolia][fast locate probe] zero-generation locate confirmed; explicitly generating predicted chunk ${P_CHUNK_X},${P_CHUNK_Z}"
TOKEN="NR_FAST_LOCATE_FULL_${P_CHUNK_X}_${P_CHUNK_Z}"
send_console "execute in minecraft:overworld run forceload add ${P_BLOCK_X} ${P_BLOCK_Z}"
for _ in $(seq 1 180); do
  send_console "execute in minecraft:overworld if loaded ${P_BLOCK_X} 0 ${P_BLOCK_Z} run say ${TOKEN}"
  sleep 1
  if grep -Fq -- "${TOKEN}" "${TEST_DIR}/server.log" 2>/dev/null; then
    break
  fi
  if ! kill -0 "${SERVER_PID}" 2>/dev/null; then
    break
  fi
done
if ! grep -Fq -- "${TOKEN}" "${TEST_DIR}/server.log"; then
  echo "Predicted chunk ${P_CHUNK_X},${P_CHUNK_Z} did not reach FULL" >&2
  exit 1
fi
send_console "execute in minecraft:overworld run forceload remove ${P_BLOCK_X} ${P_BLOCK_Z}"
sleep 3
send_console 'stop'
for _ in $(seq 1 120); do
  if ! kill -0 "${SERVER_PID}" 2>/dev/null; then
    break
  fi
  sleep 1
done
cleanup_server

python3 - "${ROOT_DIR}" "${WORLD_DIR}" "${PREDICTION}" "${BEFORE}" "${AFTER}" "${PROOF}" <<'PY'
import importlib.util
import json
import sys
from pathlib import Path

root=Path(sys.argv[1]); world=Path(sys.argv[2]); prediction_path=Path(sys.argv[3])
before=Path(sys.argv[4]); after=Path(sys.argv[5]); proof_path=Path(sys.argv[6])
pred=json.loads(prediction_path.read_text())
raw_spec=importlib.util.spec_from_file_location('raw_hasher', root/'scripts/hash-never-nether-chunks.py')
raw=importlib.util.module_from_spec(raw_spec); raw_spec.loader.exec_module(raw)
over_spec=importlib.util.spec_from_file_location('over_hasher', root/'scripts/hash-never-overworld-generation-chunks.py')
over=importlib.util.module_from_spec(over_spec); over_spec.loader.exec_module(over)
region=over.find_region_dir(world)
chunk=raw.read_chunk_nbt(region, pred['chunk_x'], pred['chunk_z'])
structures=chunk.get('structures') or {}
starts=structures.get('starts') or {}
start=starts.get(pred['structure'])
if start is None:
    available=sorted(str(k) for k in starts.keys())
    raise SystemExit(f"Predicted structure {pred['structure']} missing from actual starts in chunk {pred['chunk_x']},{pred['chunk_z']}; starts={available}")
if isinstance(start, dict) and str(start.get('id','')).upper() == 'INVALID':
    raise SystemExit(f"Predicted structure {pred['structure']} persisted as INVALID")

before_rows=before.read_text().splitlines()
after_rows=after.read_text().splitlines()
proof={
    'status':'ok',
    'structure':pred['structure'],
    'origin_block':[8192,64,8192],
    'predicted_block':[pred['block_x'],pred['block_z']],
    'predicted_chunk':[pred['chunk_x'],pred['chunk_z']],
    'anvil_records_before_locate':len(before_rows),
    'anvil_records_after_locate':len(after_rows),
    'new_anvil_records_from_locate':sorted(set(after_rows)-set(before_rows)),
    'actual_start_id':start.get('id') if isinstance(start,dict) else None,
}
proof_path.parent.mkdir(parents=True,exist_ok=True)
proof_path.write_text(json.dumps(proof,indent=2)+'\n')
print('[NeverFolia][fast locate probe] PROOF:', json.dumps(proof,sort_keys=True))
if proof['new_anvil_records_from_locate']:
    raise SystemExit('Locate created Anvil records')
PY

if grep -Eqi "Failed to parse|Couldn't parse|Unknown registry|Errors in currently selected datapacks|Failed to load datapacks|Failed to load registries|Command exception|NullPointerException" "${TEST_DIR}/server.log"; then
  echo '[NeverFolia][fast locate probe] runtime error detected.' >&2
  tail -n 300 "${TEST_DIR}/server.log" >&2
  exit 1
fi

echo '[NeverFolia][NeverOverworld fast locate] ZERO-GENERATION PREDICTION == NATURAL START OK'
