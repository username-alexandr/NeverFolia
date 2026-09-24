#!/usr/bin/env python3
"""FIELD-R20 targeted regression for user-reported seed/chunk seam artifacts."""
from __future__ import annotations

import argparse
import importlib.util
import json
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
    server=Server(a.jar.resolve(),work,log)
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

    region=work/'world/dimensions/minecraft/overworld/region'
    roots={p:nbt.read_chunk_nbt(region,*p) for p in chunks}
    volume=observer.Volume(roots)
    seam=seam_audit(volume,chunks)
    villages=village_starts(roots)
    report={
        'schema':1,'profile':'FIELD-R20-USER-SEED-1','source_sha':a.source_sha,
        'seed':SEED,'jar_sha256':sha(a.jar),'overworld_sha256':sha(a.overworld),
        'nether_sha256':sha(a.nether),'chunks':[list(p) for p in chunks],
        'water_seam':seam,'village_starts':villages,
        'pass':seam['pass'],
        'notes':[
            'Target chunks come from user screenshots for seed -2815737126961128793.',
            'Only large WATER<->AIR planes exactly on horizontal chunk seams are gated.',
            'Village starts are persisted as diagnostics; steep-piece rejection is enforced by FieldR20Smoke/runtime admission.',
        ],
    }
    target=out/'field-r20-user-seed.json'
    target.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    require(report['pass'],
            'FIELD-R20 user-seed seam regression failed; see field-r20-user-seed.json')

if __name__=='__main__':
    main()
