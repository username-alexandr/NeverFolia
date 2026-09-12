#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 5 ]; then
  echo "usage: $0 /path/to/NeverFolia.jar /path/to/NeverOverworld-Core.zip variant /output/dir source-sha" >&2
  exit 2
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
JAR="$(realpath "$1")"
PACK="$(realpath "$2")"
VARIANT="$3"
OUT_DIR="$(realpath -m "$4")"
SOURCE_SHA="$5"

case "$VARIANT" in
  desert|plains|savanna|snowy|taiga) ;;
  *) echo "unsupported village variant: $VARIANT" >&2; exit 2 ;;
esac

TARGET="minecraft:village_${VARIANT}"
TEST_DIR="${ROOT_DIR}/village-persisted-${VARIANT}"
WORLD_DIR="${TEST_DIR}/world"
PORT=$((25620 + (${#VARIANT} * 11)))

rm -rf "$TEST_DIR"
mkdir -p "$WORLD_DIR/datapacks" "$OUT_DIR"
cp "$PACK" "$WORLD_DIR/datapacks/NeverOverworld-Core.zip"
printf 'eula=true\n' > "$TEST_DIR/eula.txt"
cat > "$TEST_DIR/server.properties" <<PROPS
level-name=world
level-seed=NeverOverworld-Vanilla-Field-Structures-1
level-type=minecraft:normal
initial-enabled-packs=vanilla,file/NeverOverworld-Core.zip
initial-disabled-packs=
online-mode=false
enforce-secure-profile=false
server-port=${PORT}
view-distance=2
simulation-distance=2
spawn-protection=0
max-tick-time=-1
enable-status=false
PROPS

SERVER_PID=""
KEEPER_PID=""
PIPE_PATH="console.pipe"
cleanup() {
  if [ -n "${SERVER_PID}" ]; then kill "${SERVER_PID}" 2>/dev/null || true; wait "${SERVER_PID}" 2>/dev/null || true; fi
  if [ -n "${KEEPER_PID}" ]; then kill "${KEEPER_PID}" 2>/dev/null || true; wait "${KEEPER_PID}" 2>/dev/null || true; fi
  SERVER_PID=""; KEEPER_PID=""
}
trap cleanup EXIT

cd "$TEST_DIR"
mkfifo "$PIPE_PATH"
tail -f /dev/null > "$PIPE_PATH" & KEEPER_PID=$!
java -Dneverfolia.debugVillageLocate=true -Xms1G -Xmx3G -jar "$JAR" nogui < "$PIPE_PATH" > server.log 2>&1 & SERVER_PID=$!
cd "$ROOT_DIR"

send_console() { printf '%s\n' "$1" > "$TEST_DIR/$PIPE_PATH"; }

for _ in $(seq 1 300); do
  if grep -q 'Done (' "$TEST_DIR/server.log" 2>/dev/null; then break; fi
  if ! kill -0 "$SERVER_PID" 2>/dev/null; then break; fi
  sleep 1
done
if ! grep -q 'Done (' "$TEST_DIR/server.log" 2>/dev/null; then
  echo "$VARIANT: server did not reach ready state" >&2
  tail -n 250 "$TEST_DIR/server.log" >&2 || true
  exit 1
fi

START_LINE=$(( $(wc -l < "$TEST_DIR/server.log") + 1 ))
send_console "execute in minecraft:overworld positioned 0 128 0 run locate structure ${TARGET}"
LOCATED=0
for _ in $(seq 1 420); do
  SEG="$(tail -n +"$START_LINE" "$TEST_DIR/server.log" 2>/dev/null || true)"
  if grep -Fq "The nearest ${TARGET} is at [" <<<"$SEG"; then LOCATED=1; break; fi
  if grep -Fq 'Could not find' <<<"$SEG"; then
    echo "$VARIANT: locate exhausted without ACCEPT" >&2
    tail -n +"$START_LINE" "$TEST_DIR/server.log" >&2 || true
    exit 1
  fi
  if ! kill -0 "$SERVER_PID" 2>/dev/null; then
    echo "$VARIANT: server exited during locate" >&2
    tail -n 250 "$TEST_DIR/server.log" >&2 || true
    exit 1
  fi
  sleep 1
done
if [ "$LOCATED" -ne 1 ]; then
  echo "$VARIANT: locate timeout" >&2
  tail -n +"$START_LINE" "$TEST_DIR/server.log" >&2 || true
  exit 1
fi

python3 - "$TEST_DIR/server.log" "$START_LINE" "$VARIANT" > "$TEST_DIR/parsed.tsv" <<'PY'
import re,sys
log,start,variant=sys.argv[1],int(sys.argv[2]),sys.argv[3]
target=f"minecraft:village_{variant}"
lines=open(log,errors='replace').read().splitlines()[start-1:]
locate=re.compile(rf'The nearest {re.escape(target)} is at \[\s*(-?\d+)\s*,\s*[^,\]]+\s*,\s*(-?\d+)\s*\]')
accept=re.compile(rf'id={re.escape(target)} reason=ACCEPT .*? detail=bbox=(-?\d+),(-?\d+)\.\.(-?\d+),(-?\d+),exact-all-columns-dry')
loc=None; box=None
for line in lines:
    m=accept.search(line)
    if m: box=tuple(map(int,m.groups()))
    m=locate.search(line)
    if m: loc=tuple(map(int,m.groups()))
if not loc or not box:
    raise SystemExit(f'{variant}: missing exact ACCEPT/locate evidence: loc={loc} box={box}')
bx,bz=loc
minx,minz,maxx,maxz=box
cminx=minx//16-1; cminz=minz//16-1; cmaxx=maxx//16+1; cmaxz=maxz//16+1
count=(cmaxx-cminx+1)*(cmaxz-cminz+1)
if count > 256:
    raise SystemExit(f'{variant}: exact bbox forceload exceeds 256 chunks: {count}')
print(bx,bz,bx//16,bz//16,minx,minz,maxx,maxz,cminx,cminz,cmaxx,cmaxz,count,sep='\t')
PY

IFS=$'\t' read -r bx bz cx cz minx minz maxx maxz cminx cminz cmaxx cmaxz count < "$TEST_DIR/parsed.tsv"
printf '%s\t%s\t%s\t%s\t%s\n' "$TARGET" "$bx" "$bz" "$cx" "$cz" > "$TEST_DIR/locate.tsv"
echo "[$VARIANT] ACCEPT locate=$bx,$bz chunk=$cx,$cz bbox=$minx,$minz..$maxx,$maxz forceload=$count"

x1=$((cminx*16)); z1=$((cminz*16)); x2=$((cmaxx*16+15)); z2=$((cmaxz*16+15))
send_console "execute in minecraft:overworld run forceload add $x1 $z1 $x2 $z2"

wait_loaded() {
  local x="$1" z="$2" token="$3"
  for _ in $(seq 1 240); do
    send_console "execute in minecraft:overworld if loaded $x 128 $z run say $token"
    sleep 1
    if grep -Fq "$token" "$TEST_DIR/server.log" 2>/dev/null; then return 0; fi
    if ! kill -0 "$SERVER_PID" 2>/dev/null; then break; fi
  done
  echo "$VARIANT: FULL barrier timeout at $x,$z" >&2
  return 1
}

wait_loaded "$bx" "$bz" "NR_${VARIANT}_CENTER"
wait_loaded "$minx" "$minz" "NR_${VARIANT}_NW"
wait_loaded "$maxx" "$minz" "NR_${VARIANT}_NE"
wait_loaded "$minx" "$maxz" "NR_${VARIANT}_SW"
wait_loaded "$maxx" "$maxz" "NR_${VARIANT}_SE"
sleep 8

# Folia persistence contract: normal stop only. Never use save-all.
send_console stop
for _ in $(seq 1 240); do
  if ! kill -0 "$SERVER_PID" 2>/dev/null; then break; fi
  sleep 1
done
if kill -0 "$SERVER_PID" 2>/dev/null; then
  echo "$VARIANT: normal stop timeout" >&2
  exit 1
fi
kill "$KEEPER_PID" 2>/dev/null || true
wait "$KEEPER_PID" 2>/dev/null || true
KEEPER_PID=""; SERVER_PID=""
trap - EXIT

cp "$TEST_DIR/server.log" "$OUT_DIR/${VARIANT}-server.log"
cp "$TEST_DIR/locate.tsv" "$OUT_DIR/${VARIANT}-locate.tsv"
cp "$TEST_DIR/parsed.tsv" "$OUT_DIR/${VARIANT}-parsed.tsv"

python3 "$ROOT_DIR/scripts/audit-never-overworld-village-persisted-bbox.py" \
  --root "$ROOT_DIR" \
  --world "$WORLD_DIR" \
  --locate "$TEST_DIR/locate.tsv" \
  --output "$OUT_DIR/${VARIANT}-persisted-bbox.json" \
  --source-sha "$SOURCE_SHA"

echo "[NeverFolia][village persisted bbox] FINAL PASS variant=$VARIANT source=$SOURCE_SHA"
