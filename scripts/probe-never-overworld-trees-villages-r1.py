#!/usr/bin/env python3
"""Generate a disposable Overworld sample and READ its stopped region files.

No source instrumentation, /place feature, /fill, region edits or lock bypass.
Saved wood/leaf components are observations, not identities of complete trees.
Village waterline tables require visual review; water between pieces is allowed.
"""
from __future__ import annotations

import argparse
from collections import Counter, deque
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

SEED = -2996952393010080672
SIDES = ((1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1))
FORESTS = ('minecraft:forest', 'minecraft:birch_forest', 'minecraft:taiga')
VILLAGES = ('minecraft:village_plains', 'minecraft:village_desert')
AIR = {'minecraft:air','minecraft:cave_air','minecraft:void_air'}
SPECIES = ('oak','spruce','birch','jungle','acacia','dark_oak','mangrove','cherry','pale_oak')
LOGS = {f'minecraft:{prefix}{wood}_{suffix}' for wood in SPECIES
        for prefix in ('','stripped_') for suffix in ('log','wood')}
LEAVES = {f'minecraft:{wood}_leaves' for wood in SPECIES}


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')


def sha(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def load_nbt(root: Path):
    path = root/'scripts/hash-never-nether-chunks.py'
    spec = importlib.util.spec_from_file_location('tree_natural_nbt', path)
    require(spec is not None and spec.loader is not None, 'NBT reader not available')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def unpack_section(section: dict) -> list[dict]:
    """Decode padded modern palette storage once, rejecting malformed evidence."""
    states = section.get('block_states')
    require(isinstance(states, dict), 'section block_states missing')
    palette = states.get('palette')
    require(isinstance(palette, list) and 1 <= len(palette) <= 4096, 'invalid palette')
    require(all(isinstance(p, dict) and isinstance(p.get('Name'), str) for p in palette),
            'invalid palette entry')
    if len(palette) == 1:
        return [palette[0]] * 4096
    data = states.get('data', {}).get('$long_array')
    bits = max(4, (len(palette)-1).bit_length()); per = 64//bits
    require(isinstance(data, list) and len(data) == (4096+per-1)//per, 'incomplete state array')
    mask = (1 << bits)-1
    output = []
    for i in range(4096):
        index = ((data[i//per] & ((1 << 64)-1)) >> ((i % per)*bits)) & mask
        require(index < len(palette), 'palette index out of range')
        output.append(palette[index])
    return output


class Volume:
    """Bounded read-only view. A missing sampled chunk is UNKNOWN, never air."""
    def __init__(self, roots: dict[tuple[int,int], dict]):
        self.roots = roots
        self.sections = {}
        self.decoded = {}
        for (cx,cz), root in roots.items():
            require(root.get('Status') == 'minecraft:full', f'not FULL: {cx},{cz}')
            require(root.get('xPos') == cx and root.get('zPos') == cz, 'NBT coordinate mismatch')
            for section in root.get('sections', []):
                sy = section.get('Y')
                require(type(sy) is int, 'section Y missing')
                key = (cx, sy, cz)
                require(key not in self.sections, 'duplicate section')
                # Light-only padding sections need not contain block state data.
                if 'block_states' in section:
                    self.sections[key] = section

    def section(self, key):
        if key not in self.decoded:
            raw = self.sections.get(key)
            self.decoded[key] = unpack_section(raw) if raw is not None else [{'Name':'minecraft:air'}]*4096
        return self.decoded[key]

    def at(self, x, y, z):
        if (x//16,z//16) not in self.roots or y < -512 or y > 511:
            return None
        return self.section((x//16,y//16,z//16))[((y&15)<<8)|((z&15)<<4)|(x&15)]

    def wood(self):
        output = {}
        for key, section in self.sections.items():
            palette = section['block_states'].get('palette', [])
            if not any(p.get('Name') in LOGS | LEAVES for p in palette):
                continue
            cx,sy,cz = key
            for i, state in enumerate(self.section(key)):
                if state['Name'] in LOGS | LEAVES:
                    output[(cx*16+(i&15),sy*16+(i>>8),cz*16+((i>>4)&15))] = state
        require(len(output) <= 300000, 'wood sample exceeds bounded audit capacity')
        return output


def observed_components(volume: Volume) -> dict:
    wood = volume.wood(); pending = set(wood); counts = Counter(); examples = []
    while pending:
        origin = min(pending); pending.remove(origin); queue = deque([origin]); points = []
        uncertain = False; wet = False; logs = leaves = horizontal = 0
        while queue:
            point = queue.popleft(); points.append(point); x,y,z = point; state = wood[point]
            if state['Name'] in LOGS:
                logs += 1
                horizontal += state.get('Properties', {}).get('axis') in ('x','z')
            else:
                leaves += 1
            wet |= state.get('Properties', {}).get('waterlogged') == 'true'
            for dx,dy,dz in SIDES:
                other = x+dx,y+dy,z+dz
                if other in pending:
                    pending.remove(other); queue.append(other)
                near = volume.at(*other)
                if near is None:
                    uncertain = True
                elif near['Name'] == 'minecraft:water':
                    wet = True
        counts['wood_leaf_components'] += 1
        counts['logs'] += logs; counts['leaves'] += leaves
        if uncertain:
            counts['sample_boundary_components'] += 1
            continue
        submerged = sum(y <= 128 for x,y,z in points)
        if not logs or not leaves or not wet:
            continue
        label = 'other'
        if submerged == len(points):
            label = 'wholly_submerged_components'
        elif submerged in (2,3):
            label = f'partial_{submerged}_block_components'
        counts[label] += 1
        if horizontal:
            counts['horizontal_log_components'] += 1
        if len(examples) < 50:
            examples.append({'sample':list(origin), 'blocks':len(points), 'logs':logs,
                             'leaves':leaves, 'horizontal_logs':horizontal,
                             'below_or_at_ocean_blocks':submerged, 'classification':label})
    for key in ('wholly_submerged_components','partial_2_block_components','partial_3_block_components',
                'horizontal_log_components','sample_boundary_components','logs','leaves'):
        counts.setdefault(key,0)
    return {'counts':dict(counts), 'examples':examples,
            'classification_scope':'6-connected wood/leaf components, not individual tree identities. Horizontal logs are not proof of a fallen-tree feature.'}


def boxes_for_start(root: dict, target: str) -> list[list[int]]:
    start = root.get('structures', {}).get('starts', {}).get(target)
    require(isinstance(start, dict) and start.get('id') == target, f'start missing: {target}')
    boxes = []
    for child in start.get('Children', []):
        box = child.get('BB')
        if isinstance(box, dict):
            box = box.get('$int_array')
        require(isinstance(box,list) and len(box)==6 and all(type(v) is int for v in box), 'invalid piece bbox')
        require(all(box[i] <= box[i+3] for i in range(3)), 'inverted piece bbox')
        boxes.append(box)
    require(bool(boxes), 'no saved village pieces')
    return boxes


def coverage(boxes, margin=0):
    minx = min(b[0] for b in boxes)-margin; maxx = max(b[3] for b in boxes)+margin
    minz = min(b[2] for b in boxes)-margin; maxz = max(b[5] for b in boxes)+margin
    require(maxx-minx <= 256 and maxz-minz <= 256, 'unbounded village bbox')
    selected = [(x,z) for z in range(minz//16,maxz//16+1) for x in range(minx//16,maxx//16+1)]
    require(len(selected) <= 324, 'village coverage too large')
    return selected


def village_plane(volume: Volume, boxes, output: Path) -> dict:
    counts = Counter()
    minx,minz = min(b[0] for b in boxes), min(b[2] for b in boxes)
    maxx,maxz = max(b[3] for b in boxes), max(b[5] for b in boxes)
    with output.open('x',newline='',encoding='utf-8') as stream:
        writer = csv.writer(stream); writer.writerow(('x','z','y128_block','within_piece_xz_bbox'))
        for z in range(minz,maxz+1):
            for x in range(minx,maxx+1):
                state = volume.at(x,128,z)
                require(state is not None, 'missing village column')
                inside = any(b[0] <= x <= b[3] and b[2] <= z <= b[5] for b in boxes)
                name = state['Name']; writer.writerow((x,z,name,int(inside)))
                counts['columns'] += 1
                if not inside:
                    counts['outside_piece_bbox_columns'] += 1
                    counts['outside_piece_bbox_water' if name=='minecraft:water' else 'outside_piece_bbox_nonwater'] += 1
    return {'piece_count':len(boxes), 'xz_bounds':[minx,minz,maxx,maxz], 'counts':dict(counts),
            'plane_csv':output.name, 'visual_shape_accepted':False,
            'note':'XZ piece bboxes are not exact foundation footprints. Water between pieces is allowed. No all-dry-bbox gate.'}


class Server:
    COMMAND_ERROR = r'Unknown or incomplete command|Incorrect argument|Unknown command|Could not find|Couldn.t find'

    def __init__(self, jar: Path, folder: Path, log: Path):
        self.log = log; self.stream = log.open('x',encoding='utf-8'); self.token = 0
        try:
            self.p = subprocess.Popen(['java','-Xms1G','-Xmx4G','-XX:ActiveProcessorCount=4',
                # Natural acceptance requires deterministic cross-chunk FEATURES ordering.
                # This affects only the disposable CI server process, never the packaged JAR.
                '-DPaper.WorkerThreadCount=1','-jar',str(jar),'--nogui'],cwd=folder,stdin=subprocess.PIPE,
                stdout=self.stream,stderr=subprocess.STDOUT,text=True,bufsize=1)
        except Exception:
            self.stream.close(); raise

    def text(self):
        return self.log.read_text(encoding='utf-8',errors='replace')

    def send(self, text):
        require(self.p.poll() is None, f'server exited: {self.p.returncode}')
        self.p.stdin.write(text+'\n'); self.p.stdin.flush()

    def wait(self, pattern, start=0, timeout=120, command=None):
        end = time.monotonic()+timeout
        while time.monotonic() < end:
            segment = self.text()[start:]
            if command is not None:
                require(not re.search(self.COMMAND_ERROR,segment),
                        f'command failed: {command}\n{segment[-2000:]}')
            match = re.search(pattern,segment)
            if match:
                return match
            require(self.p.poll() is None,'server exited while waiting: '+pattern)
            time.sleep(0.5)
        raise TimeoutError(f'{command or pattern}: no positive acknowledgement')

    @staticmethod
    def marker_pattern(token):
        # Accept a server say response, not a command echoed in an error message.
        return r'(?m)^\[[^\r\n]*\bINFO\]: (?:\[Not Secure\] )?\[Server\] '+re.escape(token)+r'\r?$'

    def disable_random_ticks(self):
        command = 'execute in minecraft:overworld run gamerule minecraft:random_tick_speed 0'
        start = len(self.text()); self.send(command)
        self.wait(r'(?m)^\[[^\r\n]*\bINFO\]: Gamerule (?:minecraft:)?random_tick_speed is now set to: 0\r?$',
                  start,command=command)

    def locate(self, kind, target, x, z):
        command = f'execute in minecraft:overworld positioned {x} 200 {z} run locate {kind} {target}'
        start = len(self.text()); self.send(command)
        m = self.wait(re.escape(target)+r'.*?\[\s*(-?\d+)\s*,\s*(~|-?\d+)\s*,\s*(-?\d+)\s*\]',
                      start,command=command)
        return int(m.group(1)), int(m.group(3))

    def load(self, chunks, label, timeout=240):
        """Runtime barrier only. Saved FULL status is checked AFTER normal stop."""
        selected = sorted(set(map(tuple,chunks)))
        require(1 <= len(selected) <= 324 and all(len(p)==2 and all(type(v) is int for v in p)
                for p in selected),'invalid load request')
        for offset in range(0,len(selected),32):
            batch = selected[offset:offset+32]
            start = len(self.text()); probes = {}
            for cx,cz in batch:
                self.send(f'execute in minecraft:overworld run forceload add {cx*16} {cz*16}')
                self.token += 1
                token = f'TREE_LOADED_{self.token}_{cx}_{cz}'
                probes[token] = (cx,cz)
            pending = set(probes); deadline = time.monotonic()+timeout
            while pending and time.monotonic() < deadline:
                for token in sorted(pending):
                    cx,cz = probes[token]
                    self.send(f'execute in minecraft:overworld if loaded {cx*16} 0 {cz*16} run say {token}')
                time.sleep(1)
                segment = self.text()[start:]
                require(not re.search(self.COMMAND_ERROR,segment),f'{label}: load command failed\n{segment[-2000:]}')
                pending = {token for token in pending if not re.search(self.marker_pattern(token),segment)}
                require(self.p.poll() is None,f'{label}: server exited during load barrier')
            require(not pending,f'{label}: load barrier timed out: {sorted(pending)}')
            self.token += 1; token = f'TREE_RELEASED_{self.token}'
            start = len(self.text())
            command = 'execute in minecraft:overworld run forceload remove all'
            self.send(command); self.send('say '+token)
            self.wait(self.marker_pattern(token),start,command=command)
        print('LOADED (not yet saved-verified)',label,len(selected),flush=True)
        return [list(p) for p in selected]

    def stop(self):
        self.send('stop'); code=self.p.wait(timeout=150); self.stream.close()
        require(code == 0,'server failed normal stop'); return code

    def close(self):
        if self.p.poll() is None:
            self.p.terminate()
            try: self.p.wait(timeout=20)
            except subprocess.TimeoutExpired:
                self.p.kill(); self.p.wait(timeout=10)
        self.stream.close()


def stopped_roots(phase, region, chunks, nbt):
    """Never substitute an in-memory loaded marker for saved NBT evidence."""
    require(phase.get('normal_stop') is True and type(phase.get('process_exit_code')) is int
            and phase['process_exit_code'] == 0,'phase did not stop normally; no region reads')
    roots = {tuple(p):nbt.read_chunk_nbt(region,*p) for p in chunks}
    Volume(roots)  # Every requested chunk must be FULL with matching coordinates.
    return roots


def generate(root: Path, jar: Path, pack: Path, out: Path, nbt, source_sha=None):
    work = root/'.work/trees-villages-natural-r1'
    work.mkdir(parents=True,exist_ok=False)  # Never delete/adopt an existing world.
    (work/'world/datapacks').mkdir(parents=True)
    installed_pack = work/'world/datapacks/NeverOverworld.zip'
    shutil.copyfile(pack,installed_pack)
    (work/'eula.txt').write_text('eula=true\n')  # Disposable CI only, not an installer.
    (work/'server.properties').write_text(
        f'level-name=world\nlevel-seed={SEED}\n'
        'initial-enabled-packs=vanilla,file/NeverOverworld.zip\n'
        'online-mode=false\nenforce-secure-profile=false\nserver-ip=127.0.0.1\nserver-port=25596\n'
        'view-distance=2\nsimulation-distance=2\nspawn-protection=0\nenable-status=false\n'
        'pause-when-empty-seconds=-1\n',encoding='utf-8')
    region = work/'world/dimensions/minecraft/overworld/region'
    progress = {'schema':2,'seed':SEED,'source_sha':source_sha,'areas':[], 'normal_stop':False,
                'phases':[], 'jar_sha256':sha(jar),'pack_sha256':sha(pack)}
    progress_file = out/'tree-village-plan.json'
    write_json(progress_file,progress)

    def run_phase(name, action):
        # A phase is successful only after an explicit stop returns exit code 0.
        require(sha(jar)==progress['jar_sha256'] and sha(pack)==progress['pack_sha256']
                and sha(installed_pack)==progress['pack_sha256'],'test binaries changed between phases')
        phase = {'name':name,'normal_stop':False,'process_exit_code':None}
        progress['phases'].append(phase); write_json(progress_file,progress)
        log_name = 'tree-village-server.log' if len(progress['phases'])==1 else 'tree-village-restart.log'
        server = Server(jar,work,out/log_name)
        try:
            server.wait(r'Done \(',timeout=300)
            server.disable_random_ticks()
            action(server)
            phase['process_exit_code'] = server.stop()
            phase['normal_stop'] = True
        except Exception as error:
            phase['error'] = f'{type(error).__name__}: {error}'
            raise
        finally:
            server.close()
            write_json(progress_file,progress)
        return phase

    initial_villages = []

    def locate_and_load(server):
        for target, origin in zip(FORESTS,((0,0),(12000,0),(-12000,0))):
            x,z=server.locate('biome',target,*origin); cx,cz=x//16,z//16
            selected=[(a,b) for b in range(cz-2,cz+3) for a in range(cx-2,cx+3)]
            area={'kind':'forest','target':target,'located_xz':[x,z], 'chunks':server.load(selected,target)}
            progress['areas'].append(area); write_json(progress_file,progress)
        for target in VILLAGES:
            x,z=server.locate('structure',target,8192,8192); cx,cz=x//16,z//16
            initial=[(a,b) for b in range(cz-2,cz+3) for a in range(cx-2,cx+3)]
            initial_villages.append({'target':target,'located_xz':[x,z],
                                     'chunks':server.load(initial,target+' initial')})
        progress['initial_villages'] = initial_villages

    first = run_phase('locate-and-initial-chunks',locate_and_load)
    for area in progress['areas']:
        stopped_roots(first,region,area['chunks'],nbt)
    for initial in initial_villages:
        target = initial['target']; x,z = initial['located_xz']; cx,cz=x//16,z//16
        roots = stopped_roots(first,region,initial['chunks'],nbt)
        found = []
        for (a,b), doc in roots.items():
            raw=doc.get('structures',{}).get('starts',{}).get(target)
            if isinstance(raw,dict) and raw.get('id')==target:
                found.append(((a-cx)**2+(b-cz)**2,a,b,boxes_for_start(doc,target)))
        require(bool(found),'located village not persisted: '+target)
        _,a,b,boxes=min(found)
        progress['areas'].append({'kind':'village','target':target,'located_xz':[x,z],
            'start_chunk':[a,b],'piece_boxes':boxes,'chunks':[list(p) for p in coverage(boxes,margin=1)]})
    first['saved_initial_full_verified'] = True
    write_json(progress_file,progress)

    def complete_villages(server):
        for area in progress['areas']:
            if area['kind']=='village':
                server.load(area['chunks'],area['target']+' complete bbox')

    second = run_phase('complete-village-footprints',complete_villages)
    for area in progress['areas']:
        stopped_roots(second,region,area['chunks'],nbt)
    require(sha(jar)==progress['jar_sha256'] and sha(installed_pack)==progress['pack_sha256'],
            'test binaries changed before final audit')
    second['saved_all_full_verified'] = True
    progress['process_exit_code'] = second['process_exit_code']
    progress['normal_stop'] = True
    write_json(progress_file,progress)
    return progress,region


def audit(plan, region, out, nbt):
    require(plan.get('normal_stop') is True and type(plan.get('process_exit_code')) is int
            and plan['process_exit_code']==0,'world not stopped normally')
    phases = plan.get('phases',[])
    require(plan.get('schema') == 2 and len(phases)==2
            and [p.get('name') for p in phases]==['locate-and-initial-chunks','complete-village-footprints']
            and all(p.get('normal_stop') is True and type(p.get('process_exit_code')) is int
                    and p['process_exit_code']==0 for p in phases)
            and phases[0].get('saved_initial_full_verified') is True
            and phases[1].get('saved_all_full_verified') is True,'incomplete stopped-world phases')
    require(type(plan.get('seed')) is int and plan['seed']==SEED,'unexpected seed')
    targets=[(a.get('kind'),a.get('target')) for a in plan.get('areas',[])]
    expected=[('forest',x) for x in FORESTS]+[('village',x) for x in VILLAGES]
    require(len(targets)==len(expected) and set(targets)==set(expected),'incomplete/duplicate target coverage')
    result={'schema':2,'seed':SEED,'source_sha':plan['source_sha'], 'jar_sha256':plan['jar_sha256'],
            'pack_sha256':plan['pack_sha256'],'areas':[],'production_ready':False,
            'village_visual_review_required':True,'natural_observation_pass':False,
            'saved_evidence_after_normal_stops':True}
    submerged=0; unique=set()
    for area in plan['areas']:
        coordinates=[tuple(p) for p in area['chunks']]
        require(len(set(coordinates))==len(coordinates) and 1<=len(coordinates)<=324,'invalid area coverage')
        roots={p:nbt.read_chunk_nbt(region,*p) for p in coordinates}; volume=Volume(roots)
        unique.update(coordinates)
        entry={'kind':area['kind'],'target':area['target'],'chunks_full':len(roots)}
        if area['kind']=='forest':
            cx,cz=(v//16 for v in area['located_xz'])
            require(set(coordinates)=={(x,z) for x in range(cx-2,cx+3) for z in range(cz-2,cz+3)},'forest coverage differs')
            entry.update(observed_components(volume))
            submerged+=entry['counts']['wholly_submerged_components']
        else:
            start=tuple(area['start_chunk']); require(start in roots,'missing start chunk')
            boxes=boxes_for_start(roots[start],area['target'])
            require(boxes==area['piece_boxes'],'village boxes changed after generation')
            require(set(coordinates)==set(coverage(boxes,1)),'incomplete village bbox coverage')
            entry.update(village_plane(volume,boxes,out/(area['target'].split(':')[1]+'-y128.csv')))
        result['areas'].append(entry)
    result['unique_full_chunks']=len(unique)
    result['underwater_wood_leaf_components']=submerged
    result['natural_observation_pass']=submerged>0
    result['limitations']=['One fixed seed, three 5x5 forest areas, two village variants.',
        'Persisted components are not a before/after comparison and not individual tree identities.',
        'Exact two/three-block and fallen fixtures are separately tested by native smoke.',
        'No natural fallen-feature frequency, complete village-shape or migration acceptance.']
    write_json(out/'tree-village-natural.json',result)
    require(result['natural_observation_pass'],'sample has no complete underwater wood/leaf component; do not claim coverage')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--jar',type=Path,required=True)
    parser.add_argument('--pack',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--source-sha',required=True)
    args=parser.parse_args()
    require(re.fullmatch('[0-9a-f]{40}',args.source_sha) is not None,'full source SHA required')
    root=Path(__file__).resolve().parents[1]; out=args.output.resolve(); out.mkdir(parents=True,exist_ok=True)
    require(not (out/'tree-village-plan.json').exists(),'do not overwrite previous evidence')
    nbt=load_nbt(root)
    plan,region=generate(root,args.jar.resolve(),args.pack.resolve(),out,nbt,args.source_sha)
    report=audit(plan,region,out,nbt)
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    main()
