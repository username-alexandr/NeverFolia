#!/usr/bin/env python3
from pathlib import Path
import argparse,gzip,hashlib,importlib.util,io,json,struct,zipfile

ROOT=Path(__file__).resolve().parents[2]
R3931=ROOT/'qa/field-r3931/patch_pack.py'
NBT='data/structory_towers/structure/ocean_pillar.nbt'
FP_ROOT='neveroverworld-worldgen-fingerprint.json'
FP_RESOURCE='data/neverfolia/neveroverworld/worldgen_fingerprint.json'

def need(v,m):
    if not v: raise ValueError(m)

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    need(spec is not None and spec.loader is not None,'cannot load '+str(path))
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

r31=load('r3931_patch',R3931)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def replace_palette_name(raw:bytes,old_name:bytes,new_name:bytes)->bytes:
    data=gzip.decompress(raw)
    old=struct.pack('>H',len(old_name))+old_name
    new=struct.pack('>H',len(new_name))+new_name
    need(data.count(old)==1,'unexpected '+old_name.decode()+' palette occurrence count')
    data=data.replace(old,new,1)
    return gzip.compress(data,compresslevel=9,mtime=0)

def patch(raw:bytes)->tuple[bytes,dict]:
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        infos=z.infolist()
        files={i.filename:z.read(i.filename) for i in infos if not i.is_dir()}

    for p in (NBT,FP_ROOT,FP_RESOURCE):
        need(p in files,'missing '+p)

    before_void=r31._state_geometry(files[NBT],'minecraft:structure_void')
    before_water=r31._state_geometry(files[NBT],'minecraft:water')
    before_air=r31._state_geometry(files[NBT],'minecraft:cave_air')

    need(before_void['count']==8,'expected exactly 8 ocean_pillar structure_void cells')
    need(before_void['bbox']==[10,10,21,23,5,7],'unexpected ocean_pillar structure_void geometry')
    need(before_water['count']==0,'ocean_pillar unexpectedly already contains explicit water')
    need(before_air['count']==0,'ocean_pillar cave_air regression returned')

    files[NBT]=replace_palette_name(
        files[NBT],
        b'minecraft:structure_void',
        b'minecraft:water'
    )

    after_void=r31._state_geometry(files[NBT],'minecraft:structure_void')
    after_water=r31._state_geometry(files[NBT],'minecraft:water')
    need(after_void['count']==0,'ocean_pillar still contains structure_void')
    need(after_water['count']==8,'ocean_pillar water replacement count mismatch')
    need(after_water['bbox']==[10,10,21,23,5,7],'ocean_pillar water geometry changed')

    fp=r31.content_fingerprint(files)
    for p in (FP_ROOT,FP_RESOURCE):
        d=json.loads(files[p])
        d['content_sha256']=fp
        d['entry_count_excluding_fingerprint']=len(files)-2
        files[p]=(json.dumps(d,ensure_ascii=False,indent=2)+'\n').encode()

    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as dst:
        known={i.filename:i for i in infos if not i.is_dir()}
        for name in [i.filename for i in infos if not i.is_dir()]:
            dst.writestr(known[name],files[name])

    result=out.getvalue()
    return result,{
      'ocean_pillar_structure_void_before':8,
      'ocean_pillar_structure_void_after':0,
      'ocean_pillar_water_after':8,
      'ocean_pillar_water_bbox':[10,10,21,23,5,7],
      'content_fingerprint':fp
    }

def verify(raw:bytes):
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        files={i.filename:z.read(i.filename) for i in z.infolist() if not i.is_dir()}
    void=r31._state_geometry(files[NBT],'minecraft:structure_void')
    water=r31._state_geometry(files[NBT],'minecraft:water')
    need(void['count']==0,'structure_void survived in ocean_pillar')
    need(water['count']==8 and water['bbox']==[10,10,21,23,5,7],'ocean_pillar water repair missing')
    fp0=json.loads(files[FP_ROOT]);fp1=json.loads(files[FP_RESOURCE])
    need(fp0==fp1,'fingerprint docs differ')
    need(fp0.get('content_sha256')==r31.content_fingerprint(files),'fingerprint mismatch')
    return {'structure_void':void,'water':water,'fingerprint':fp0.get('content_sha256')}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('src',type=Path)
    ap.add_argument('dst',type=Path)
    a=ap.parse_args()
    raw=a.src.read_bytes()
    out,meta=patch(raw)
    report=verify(out)
    a.dst.parent.mkdir(parents=True,exist_ok=True)
    a.dst.write_bytes(out)
    print('R3934_PACK '+json.dumps({
      'input_sha256':sha(raw),
      'output_sha256':sha(out),
      **meta,
      'audit':report
    }))

if __name__=='__main__':main()
