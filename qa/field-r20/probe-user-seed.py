#!/usr/bin/env python3
"""FIELD-R22 targeted regression for user-reported seed/chunk seam artifacts."""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
from collections import deque
from pathlib import Path
import shutil

SEED = -2815737126961128793
AIR = {'minecraft:air', 'minecraft:cave_air', 'minecraft:void_air'}
WATER_TARGETS = (
    (230, -838),
    (229, -836),
    (221, -837),
    (-302, -517),
    (-441, -515),
    (-424, -489),
)
VILLAGE_TARGETS = ((-425, -508), (-426, -509))
MAX_WATER_AIR_SEAM_FACES = 192
MAX_OCEAN_CONNECTED_AIR_CELLS = 64
EXTERNAL_STRUCTURE_NAMESPACES = (
    'nova_structures:', 'explorify:', 'structory_towers:',
    'repurposed_structures:', 'betteroceanmonuments:',
)

def require(ok, message):
    if not ok:
        raise ValueError(message)

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    require(spec is not None and spec.loader is not None, 'missing module: '+str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def sha(path):
    import hashlib
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def runtime_seam_debug(log_path):
    text=Path(log_path).read_text(encoding='utf-8',errors='replace')
    pattern=re.compile(r'\\[NeverFolia\\]\\[R22Seam\\] chunk=(-?\\d+),(-?\\d+) seeds=(\\d+),(\\d+),(\\d+),(\\d+) total=(\\d+) changed=(\\d+)')
    rows=[]
    for match in pattern.finditer(text):
        rows.append({
            'chunk':[int(match.group(1)),int(match.group(2))],
            'west':int(match.group(3)),'east':int(match.group(4)),
            'north':int(match.group(5)),'south':int(match.group(6)),
            'total':int(match.group(7)),'changed':int(match.group(8)),
        })
    return rows

def imported_structure_parse_errors(log_path):
    text=Path(log_path).read_text(encoding='utf-8',errors='replace')
    bad=[]
    for line in text.splitlines():
        if "Couldn't parse data file" not in line and "Missing tag" not in line:
            continue
        if any(ns in line for ns in EXTERNAL_STRUCTURE_NAMESPACES):
            bad.append(line.strip())
    return bad[:100]


def expanded_targets():
    chunks=set()
    for cx,cz in WATER_TARGETS:
        for dx in range(-1,2):
            for dz in range(-1,2):
                chunks.add((cx+dx,cz+dz))
    for cx,cz in VILLAGE_TARGETS:
        for dx in range(-2,3):
            for dz in range(-2,3):
                chunks.add((cx+dx,cz+dz))
    require(len(chunks) <= 128, 'target sample unexpectedly large')
    return sorted(chunks)

def is_water(state):
    return state is not None and state.get('Name') == 'minecraft:water'

def is_air(state):
    return state is not None and state.get('Name') in AIR

def seam_audit(volume, chunks):
    selected=set(chunks)
    findings=[]
    max_faces=0
    total_faces=0
    for cx,cz in sorted(selected):
        for axis,nbr in (('x',(cx+1,cz)),('z',(cx,cz+1))):
            if nbr not in selected:
                continue
            faces=0
            examples=[]
            if axis == 'x':
                x1=cx*16+15; x2=x1+1
                for z in range(cz*16,cz*16+16):
                    for y in range(-64,128):
                        a=volume.at(x1,y,z); b=volume.at(x2,y,z)
                        if (is_water(a) and is_air(b)) or (is_air(a) and is_water(b)):
                            faces+=1
                            if len(examples)<12:
                                examples.append([x1,y,z,a['Name'],x2,y,z,b['Name']])
            else:
                z1=cz*16+15; z2=z1+1
                for x in range(cx*16,cx*16+16):
                    for y in range(-64,128):
                        a=volume.at(x,y,z1); b=volume.at(x,y,z2)
                        if (is_water(a) and is_air(b)) or (is_air(a) and is_water(b)):
                            faces+=1
                            if len(examples)<12:
                                examples.append([x,y,z1,a['Name'],x,y,z2,b['Name']])
            if faces:
                findings.append({'chunk':[cx,cz],'axis':axis,'neighbor':list(nbr),
                                 'water_air_faces':faces,'examples':examples})
                max_faces=max(max_faces,faces)
                total_faces+=faces
    return {'max_boundary_water_air_faces':max_faces,
            'total_boundary_water_air_faces':total_faces,
            'boundaries':findings,
            'threshold':MAX_WATER_AIR_SEAM_FACES,
            'pass':max_faces <= MAX_WATER_AIR_SEAM_FACES}

def ocean_void_audit(volume, targets):
    """Reject large AIR pockets directly exposed to the Y128-connected ocean.

    Each reported target gets a 3x3 loaded safety envelope. WATER connectivity
    is traced from Y=128 through saved WATER blocks; only AIR cells inside the
    center target chunk are counted, so unknown sample edges cannot create a
    false positive. Lava-adjacent AIR is ignored because lava is an intentional
    NeverOverworld flood barrier.
    """
    per_target=[]
    global_max=0
    total=0
    sides=((1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1))
    for cx,cz in targets:
        minx=(cx-1)*16; maxx=(cx+2)*16-1
        minz=(cz-1)*16; maxz=(cz+2)*16-1
        center_minx=cx*16; center_maxx=center_minx+15
        center_minz=cz*16; center_maxz=center_minz+15

        connected=set()
        queue=deque()
        for x in range(minx,maxx+1):
            for z in range(minz,maxz+1):
                if is_water(volume.at(x,128,z)):
                    p=(x,128,z); connected.add(p); queue.append(p)

        while queue:
            x,y,z=queue.popleft()
            for dx,dy,dz in sides:
                nx,ny,nz=x+dx,y+dy,z+dz
                if nx<minx or nx>maxx or nz<minz or nz>maxz or ny<-64 or ny>128:
                    continue
                p=(nx,ny,nz)
                if p in connected or not is_water(volume.at(nx,ny,nz)):
                    continue
                connected.add(p); queue.append(p)

        exposed_air=set()
        examples=[]
        for x,y,z in connected:
            if y>=128:
                continue
            for dx,dy,dz in sides:
                ax,ay,az=x+dx,y+dy,z+dz
                if ay>=128 or ax<center_minx or ax>center_maxx or az<center_minz or az>center_maxz:
                    continue
                state=volume.at(ax,ay,az)
                if not is_air(state):
                    continue
                lava_adjacent=False
                for ldx,ldy,ldz in sides:
                    near=volume.at(ax+ldx,ay+ldy,az+ldz)
                    if near is not None and near.get('Name')=='minecraft:lava':
                        lava_adjacent=True; break
                if lava_adjacent:
                    continue
                pos=(ax,ay,az)
                if pos in exposed_air:
                    continue
                exposed_air.add(pos)
                if len(examples)<16:
                    examples.append(list(pos))

        count=len(exposed_air)
        global_max=max(global_max,count); total+=count
        per_target.append({'chunk':[cx,cz],'ocean_connected_air_cells':count,'examples':examples})

    return {
        'max_ocean_connected_air_cells':global_max,
        'total_ocean_connected_air_cells':total,
        'threshold':MAX_OCEAN_CONNECTED_AIR_CELLS,
        'targets':per_target,
        'pass':global_max <= MAX_OCEAN_CONNECTED_AIR_CELLS,
    }


def village_starts(roots):
    found=[]
    seen=set()
    for (cx,cz),root in roots.items():
        starts=root.get('structures',{}).get('starts',{})
        if not isinstance(starts,dict):
            continue
        for _,start in starts.items():
            if not isinstance(start,dict):
                continue
            sid=start.get('id')
            if not isinstance(sid,str) or not sid.startswith('minecraft:village_'):
                continue
            children=start.get('Children',[])
            boxes=[]
            for child in children:
                if not isinstance(child,dict):
                    continue
                box=child.get('BB')
                if isinstance(box,dict):
                    box=box.get('$int_array')
                if isinstance(box,list) and len(box)==6:
                    boxes.append(box)
            marker=(sid,tuple(tuple(x) for x in boxes))
            if marker in seen:
                continue
            seen.add(marker)
            found.append({'id':sid,'owner_chunk':[cx,cz],'piece_count':len(boxes),
                          'boxes':boxes[:80]})
    return found

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--jar',type=Path,required=True)
    p.add_argument('--overworld',type=Path,required=True)
    p.add_argument('--nether',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--source-sha',required=True)
    a=p.parse_args()

    root=Path(__file__).resolve().parents[2]
    observer=load('field_r20_observer',root/'scripts/probe-never-overworld-trees-villages-r1.py')
    paired=load('field_r20_paired',root/'scripts/probe-never-overworld-paired-r12.py')
    nbt=observer.load_nbt(root)
    Server=paired.make_server(observer)

    out=a.output.resolve()
    out.mkdir(parents=True,exist_ok=True)
    work=root/'.work/field-r20-user-seed'
    work.mkdir(parents=True,exist_ok=False)
    packs=work/'world/datapacks'
    packs.mkdir(parents=True)
    shutil.copyfile(a.overworld,packs/'NeverOverworld.zip')
    shutil.copyfile(a.nether,packs/'NeverNether.zip')
    (work/'eula.txt').write_text('eula=true\n')
    (work/'server.properties').write_text(
        f'level-name=world\nlevel-seed={SEED}\n'
        'initial-enabled-packs=vanilla,file/NeverOverworld.zip,file/NeverNether.zip\n'
        'online-mode=false\nenforce-secure-profile=false\nserver-ip=127.0.0.1\nserver-port=25597\n'
        'view-distance=2\nsimulation-distance=2\nspawn-protection=0\nenable-status=false\n'
        'pause-when-empty-seconds=-1\n',encoding='utf-8')

    chunks=expanded_targets()
    log=out/'field-r20-user-seed-server.log'
    server=Server(a.jar.resolve(),work,log,java_args=['-Dneverfolia.debugFloodSeams=true'])
    normal=False
    try:
        server.wait(r'Done \(',timeout=300)
        server.disable_random_ticks()
        server.load_dimension(chunks,'minecraft:overworld',dwell=6,serial_generation=False)
        code=server.stop()
        require(code==0,'target seed server stop failed')
        normal=True
    finally:
        if not normal:
            server.close()

    parse_errors=imported_structure_parse_errors(log)
    seam_runtime=runtime_seam_debug(log)
    region=work/'world/dimensions/minecraft/overworld/region'
    roots={p:nbt.read_chunk_nbt(region,*p) for p in chunks}
    volume=observer.Volume(roots)
    seam=seam_audit(volume,chunks)
    ocean_voids=ocean_void_audit(volume,WATER_TARGETS)
    villages=village_starts(roots)
    village_target_pass=len(villages)==0
    report={
        'schema':1,'profile':'FIELD-R22-USER-SEED-3','source_sha':a.source_sha,
        'seed':SEED,'jar_sha256':sha(a.jar),'overworld_sha256':sha(a.overworld),
        'nether_sha256':sha(a.nether),'chunks':[list(p) for p in chunks],
        'water_seam':seam,'ocean_voids':ocean_voids,
        'village_starts':villages,'village_target_pass':village_target_pass,
        'external_structure_parse_errors':parse_errors,
        'external_structure_parse_pass':len(parse_errors)==0,
        'runtime_seam_reconciliation':seam_runtime,
        'pass':seam['pass'] and ocean_voids['pass'] and village_target_pass and len(parse_errors)==0,
        'notes':[
            'Target chunks come from user screenshots for seed -2815737126961128793.',
            'Large WATER<->AIR planes exactly on horizontal chunk seams are gated.',
            'Large AIR pockets directly exposed to Y128-connected ocean water are gated inside reported chunks.',
            'The two user-reported cliff-village target areas must contain no persisted vanilla village start.',
            'Imported Overworld structure namespaces must load without datapack parse/tag errors.',
        ],
    }
    target=out/'field-r20-user-seed.json'
    target.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    require(report['pass'],
            'FIELD-R22 user-seed water/village regression failed; see field-r20-user-seed.json')

if __name__=='__main__':
    main()
