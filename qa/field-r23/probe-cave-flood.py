#!/usr/bin/env python3
"""FIELD-R23 regression for manual cave-flood failure seed.

Seed and chunks come from the user's F3 screenshots. The probe loads a safety
envelope, then checks persisted FULL chunks after a normal stop. Large deep
WATER components that are not connected through WATER to the Y=128 ocean plane
are rejected in the screenshot chunks.
"""
from __future__ import annotations
import argparse, importlib.util, json, re, shutil
from collections import deque
from pathlib import Path

SEED=-4193070274438815849
SCREENSHOT_CHUNKS=((-143,-91),(-144,-90),(-142,-91))
Y_MIN=-64
Y_MAX=128
DEEP_MAX_Y=120
MAX_DISCONNECTED_COMPONENT_AUDIT_CELLS=768
AIR={'minecraft:air','minecraft:cave_air','minecraft:void_air'}

def require(ok,msg):
    if not ok: raise ValueError("[FIELD-R23 cave flood] "+msg)

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    require(spec is not None and spec.loader is not None,"missing module: "+str(path))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

def is_water(state):
    return state is not None and state.get('Name')=='minecraft:water'

def load_chunks():
    chunks=set()
    for cx,cz in SCREENSHOT_CHUNKS:
        for dx in range(-2,3):
            for dz in range(-2,3):
                chunks.add((cx+dx,cz+dz))
    return sorted(chunks)

def audit_chunks():
    chunks=set()
    for cx,cz in SCREENSHOT_CHUNKS:
        for dx in range(-1,2):
            for dz in range(-1,2):
                chunks.add((cx+dx,cz+dz))
    return sorted(chunks)

def water_audit(volume,loaded,audit):
    min_cx=min(x for x,z in loaded);max_cx=max(x for x,z in loaded)
    min_cz=min(z for x,z in loaded);max_cz=max(z for x,z in loaded)
    minx=min_cx*16;maxx=(max_cx+1)*16-1
    minz=min_cz*16;maxz=(max_cz+1)*16-1
    width=maxx-minx+1;depth=maxz-minz+1;layers=Y_MAX-Y_MIN+1
    capacity=width*depth*layers
    connected=bytearray(capacity)
    component_seen=bytearray(capacity)

    def idx(x,y,z):
        return ((y-Y_MIN)*depth+(z-minz))*width+(x-minx)

    def inside(x,y,z):
        return minx<=x<=maxx and minz<=z<=maxz and Y_MIN<=y<=Y_MAX

    q=deque()
    for z in range(minz,maxz+1):
        for x in range(minx,maxx+1):
            if is_water(volume.at(x,Y_MAX,z)):
                e=idx(x,Y_MAX,z);connected[e]=1;q.append((x,Y_MAX,z))

    sides=((1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1))
    while q:
        x,y,z=q.popleft()
        for dx,dy,dz in sides:
            nx,ny,nz=x+dx,y+dy,z+dz
            if not inside(nx,ny,nz): continue
            e=idx(nx,ny,nz)
            if connected[e] or not is_water(volume.at(nx,ny,nz)): continue
            connected[e]=1;q.append((nx,ny,nz))

    audit_set=set(audit)
    components=[]
    disconnected_audit_cells=0
    for cx,cz in audit:
        for z in range(cz*16,cz*16+16):
            for x in range(cx*16,cx*16+16):
                for y in range(Y_MIN,DEEP_MAX_Y+1):
                    e=idx(x,y,z)
                    if connected[e] or component_seen[e] or not is_water(volume.at(x,y,z)):
                        continue
                    cq=deque([(x,y,z)]);component_seen[e]=1
                    total=0;audit_cells=0;min_y=y;max_y=y;touches_outer=False
                    examples=[]
                    while cq:
                        px,py,pz=cq.popleft();total+=1
                        min_y=min(min_y,py);max_y=max(max_y,py)
                        if (px//16,pz//16) in audit_set:
                            audit_cells+=1
                            if len(examples)<12: examples.append([px,py,pz])
                        if px in (minx,maxx) or pz in (minz,maxz):
                            touches_outer=True
                        for dx,dy,dz in sides:
                            nx,ny,nz=px+dx,py+dy,pz+dz
                            if not inside(nx,ny,nz): continue
                            ne=idx(nx,ny,nz)
                            if connected[ne] or component_seen[ne] or not is_water(volume.at(nx,ny,nz)):
                                continue
                            component_seen[ne]=1;cq.append((nx,ny,nz))
                    disconnected_audit_cells+=audit_cells
                    components.append({
                        'total_loaded_cells':total,
                        'audit_cells':audit_cells,
                        'min_y':min_y,'max_y':max_y,
                        'vertical_span':max_y-min_y+1,
                        'touches_outer_envelope':touches_outer,
                        'examples':examples,
                    })

    components.sort(key=lambda row:row['audit_cells'],reverse=True)
    largest=components[0]['audit_cells'] if components else 0
    return {
        'surface_connected_water_cells':int(sum(connected)),
        'disconnected_deep_water_audit_cells':disconnected_audit_cells,
        'largest_disconnected_component_audit_cells':largest,
        'threshold':MAX_DISCONNECTED_COMPONENT_AUDIT_CELLS,
        'components':components[:20],
        'pass':largest<=MAX_DISCONNECTED_COMPONENT_AUDIT_CELLS,
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--jar',type=Path,required=True)
    p.add_argument('--overworld',type=Path,required=True)
    p.add_argument('--nether',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--source-sha',required=True)
    a=p.parse_args()

    root=Path(__file__).resolve().parents[2]
    observer=load('field_r23_observer',root/'scripts/probe-never-overworld-trees-villages-r1.py')
    paired=load('field_r23_paired',root/'scripts/probe-never-overworld-paired-r12.py')
    nbt=observer.load_nbt(root);Server=paired.make_server(observer)

    out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
    work=root/'.work/field-r23-cave-seed';work.mkdir(parents=True,exist_ok=False)
    packs=work/'world/datapacks';packs.mkdir(parents=True)
    shutil.copyfile(a.overworld,packs/'NeverOverworld.zip')
    shutil.copyfile(a.nether,packs/'NeverNether.zip')
    (work/'eula.txt').write_text('eula=true\n')
    (work/'server.properties').write_text(
        f'level-name=world\nlevel-seed={SEED}\n'
        'initial-enabled-packs=vanilla,file/NeverOverworld.zip,file/NeverNether.zip\n'
        'online-mode=false\nenforce-secure-profile=false\nserver-ip=127.0.0.1\nserver-port=25598\n'
        'view-distance=2\nsimulation-distance=2\nspawn-protection=0\nenable-status=false\n'
        'pause-when-empty-seconds=-1\n',encoding='utf-8')

    loaded=load_chunks();audited=audit_chunks()
    log=out/'field-r23-cave-seed-server.log'
    server=Server(a.jar.resolve(),work,log,java_args=['-Dneverfolia.debugFloodSeams=true'])
    normal=False
    try:
        server.wait(r'Done \(',timeout=300)
        server.disable_random_ticks()
        server.load_dimension(loaded,'minecraft:overworld',dwell=8,serial_generation=False)
        code=server.stop();require(code==0,'server stop failed');normal=True
    finally:
        if not normal: server.close()

    region=work/'world/dimensions/minecraft/overworld/region'
    roots={p:nbt.read_chunk_nbt(region,*p) for p in loaded}
    volume=observer.Volume(roots)
    water=water_audit(volume,loaded,audited)
    text=log.read_text(encoding='utf-8',errors='replace')
    proximity_rows=len(re.findall(r'\[NeverFolia\]\[R22ProximityFlood\]',text))
    dry_rows=len(re.findall(r'\[NeverFolia\]\[R23DrySeam\]',text))
    report={
        'schema':1,'profile':'FIELD-R23-CAVE-FLOOD-1',
        'seed':SEED,'source_sha':a.source_sha,
        'screenshot_chunks':[list(p) for p in SCREENSHOT_CHUNKS],
        'loaded_chunks':[list(p) for p in loaded],
        'audited_chunks':[list(p) for p in audited],
        'water':water,
        'runtime_r22_proximity_flood_rows':proximity_rows,
        'runtime_r23_dry_seam_rows':dry_rows,
        'pass':water['pass'] and proximity_rows==0,
        'notes':[
            'Screenshot coordinates include approximately X=-2283..-2271 Z=-1444..-1437.',
            'Only large deep WATER components not WATER-connected to Y128 are rejected.',
            'R23 forbids proximity-only flood admission; actual surface-ocean connectivity is still allowed.',
        ],
    }
    target=out/'field-r23-cave-flood.json'
    target.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print('[FIELD-R23 cave flood] '+json.dumps({
        'seed':SEED,'pass':report['pass'],
        'largest_disconnected_component_audit_cells':water['largest_disconnected_component_audit_cells'],
        'disconnected_deep_water_audit_cells':water['disconnected_deep_water_audit_cells'],
        'r22_proximity_rows':proximity_rows,'r23_dry_rows':dry_rows,
    },sort_keys=True),flush=True)
    require(report['pass'],'new user-seed cave flooding regression failed; see field-r23-cave-flood.json')

if __name__=='__main__':
    main()
