#!/usr/bin/env python3
from pathlib import Path
import argparse,gzip,hashlib,io,json,zipfile,struct

TARGET='data/minecraft/worldgen/noise_settings/overworld.json'
OCEAN_PILLAR='data/structory_towers/worldgen/structure/ocean_pillar.json'
OCEAN_PILLAR_NBT='data/structory_towers/structure/ocean_pillar.nbt'
FP_ROOT='neveroverworld-worldgen-fingerprint.json'
FP_RESOURCE='data/neverfolia/neveroverworld/worldgen_fingerprint.json'

def sha(raw):return hashlib.sha256(raw).hexdigest()

def content_fingerprint(files:dict[str,bytes])->str:
    h=hashlib.sha256()
    for name in sorted(n for n in files if n not in (FP_ROOT,FP_RESOURCE)):
        nb=name.replace('\\','/').encode('utf-8')
        payload=files[name]
        h.update(struct.pack('>i',len(nb)))
        h.update(nb)
        h.update(struct.pack('>q',len(payload)))
        h.update(payload)
    return h.hexdigest()

def _nbt_parse(raw:bytes):
    data=gzip.decompress(raw)
    f=io.BytesIO(data)
    def need(n):
        b=f.read(n)
        if len(b)!=n: raise ValueError('Truncated NBT')
        return b
    def u1():return struct.unpack('>B',need(1))[0]
    def i1():return struct.unpack('>b',need(1))[0]
    def i2():return struct.unpack('>h',need(2))[0]
    def i4():return struct.unpack('>i',need(4))[0]
    def i8():return struct.unpack('>q',need(8))[0]
    def flt():return struct.unpack('>f',need(4))[0]
    def dbl():return struct.unpack('>d',need(8))[0]
    def string():
        n=struct.unpack('>H',need(2))[0]
        return need(n).decode('utf-8')
    def payload(t):
        if t==1:return i1()
        if t==2:return i2()
        if t==3:return i4()
        if t==4:return i8()
        if t==5:return flt()
        if t==6:return dbl()
        if t==7:return need(i4())
        if t==8:return string()
        if t==9:
            element=u1();count=i4()
            if count<0:raise ValueError('Negative NBT list')
            if element==0:
                if count!=0:raise ValueError('Non-empty TAG_End list')
                return []
            return [payload(element) for _ in range(count)]
        if t==10:
            out={}
            while True:
                child=u1()
                if child==0:return out
                name=string()
                out[name]=payload(child)
        if t==11:
            count=i4()
            if count<0:raise ValueError('Negative NBT int array')
            return [i4() for _ in range(count)]
        if t==12:
            count=i4()
            if count<0:raise ValueError('Negative NBT long array')
            return [i8() for _ in range(count)]
        raise ValueError('Unsupported NBT tag '+str(t))
    root_type=u1()
    if root_type!=10:raise ValueError('Structure NBT root is not a compound')
    string() # root name
    root=payload(root_type)
    if f.read(1):raise ValueError('Trailing structure NBT data')
    return root

def _state_geometry(raw:bytes,name:str):
    root=_nbt_parse(raw)
    palette=root.get('palette')
    blocks=root.get('blocks')
    if not isinstance(palette,list) or not isinstance(blocks,list):
        raise ValueError('Malformed structure NBT')
    states={i for i,p in enumerate(palette) if isinstance(p,dict) and p.get('Name')==name}
    pos=[tuple(b['pos']) for b in blocks if isinstance(b,dict) and b.get('state') in states]
    if not pos:return {'count':0,'bbox':None,'positions':[]}
    xs=[p[0] for p in pos];ys=[p[1] for p in pos];zs=[p[2] for p in pos]
    return {'count':len(pos),'bbox':[min(xs),max(xs),min(ys),max(ys),min(zs),max(zs)],'positions':[list(p) for p in pos]}

def patch_ocean_pillar_nbt(raw:bytes)->bytes:
    before=_state_geometry(raw,'minecraft:cave_air')
    if before['count']!=8 or before['bbox']!=[10,10,21,23,5,7]:
        raise ValueError('Unexpected ocean_pillar cave_air geometry: '+repr(before))
    # All eight cave-air cells are on x=10, the outer face of the 11-block-wide
    # template. They are not an interior room; preserving the existing world
    # block is the correct underwater behavior.
    old_name=b'minecraft:cave_air'
    new_name=b'minecraft:structure_void'
    data=gzip.decompress(raw)
    old=struct.pack('>H',len(old_name))+old_name
    new=struct.pack('>H',len(new_name))+new_name
    if data.count(old)!=1:
        raise ValueError('Unexpected cave_air palette occurrence count')
    data=data.replace(old,new,1)
    out=gzip.compress(data,compresslevel=9,mtime=0)
    after_air=_state_geometry(out,'minecraft:cave_air')
    after_void=_state_geometry(out,'minecraft:structure_void')
    if after_air['count']!=0 or after_void['count']!=8 or after_void['bbox']!=before['bbox']:
        raise ValueError('ocean_pillar NBT replacement failed')
    return out

def patch(raw:bytes)->bytes:
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        files={info.filename:z.read(info.filename) for info in z.infolist() if not info.is_dir()}
        if TARGET not in files:raise ValueError('NeverOverworld noise settings missing')
        if OCEAN_PILLAR not in files:raise ValueError('Structory ocean_pillar structure settings missing')
        if OCEAN_PILLAR_NBT not in files:raise ValueError('Structory ocean_pillar NBT missing')
        if FP_ROOT not in files or FP_RESOURCE not in files:raise ValueError('NeverOverworld fingerprint documents missing')

        data=json.loads(files[TARGET])
        if data.get('sea_level') not in (63,128):
            raise ValueError('Unexpected existing sea_level: '+repr(data.get('sea_level')))
        data['sea_level']=128
        files[TARGET]=(json.dumps(data,ensure_ascii=False,indent=2)+'\n').encode()

        pillar=json.loads(files[OCEAN_PILLAR])
        if pillar.get('project_start_to_heightmap')!='OCEAN_FLOOR_WG':
            raise ValueError('Unexpected ocean_pillar heightmap: '+repr(pillar.get('project_start_to_heightmap')))
        if pillar.get('terrain_adaptation') not in ('beard_thin','none'):
            raise ValueError('Unexpected ocean_pillar terrain adaptation: '+repr(pillar.get('terrain_adaptation')))
        pillar['terrain_adaptation']='none'
        files[OCEAN_PILLAR]=(json.dumps(pillar,ensure_ascii=False,indent=2)+'\n').encode()

        files[OCEAN_PILLAR_NBT]=patch_ocean_pillar_nbt(files[OCEAN_PILLAR_NBT])

        fp=content_fingerprint(files)
        for name in (FP_ROOT,FP_RESOURCE):
            doc=json.loads(files[name])
            doc['content_sha256']=fp
            doc['entry_count_excluding_fingerprint']=len(files)-2
            files[name]=(json.dumps(doc,ensure_ascii=False,indent=2)+'\n').encode()

        out=io.BytesIO()
        with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as dst:
            for info in z.infolist():
                if info.is_dir():continue
                dst.writestr(info,files[info.filename])
        return out.getvalue()

def main():
    ap=argparse.ArgumentParser();ap.add_argument('src',type=Path);ap.add_argument('dst',type=Path);a=ap.parse_args()
    raw=a.src.read_bytes();out=patch(raw);a.dst.parent.mkdir(parents=True,exist_ok=True);a.dst.write_bytes(out)
    with zipfile.ZipFile(io.BytesIO(out)) as z:
        data=json.loads(z.read(TARGET))
        pillar=json.loads(z.read(OCEAN_PILLAR))
        pillar_nbt=z.read(OCEAN_PILLAR_NBT)
        root=json.loads(z.read(FP_ROOT))
        resource=json.loads(z.read(FP_RESOURCE))
        files={info.filename:z.read(info.filename) for info in z.infolist() if not info.is_dir()}
    air=_state_geometry(pillar_nbt,'minecraft:cave_air')
    void=_state_geometry(pillar_nbt,'minecraft:structure_void')
    assert data['sea_level']==128
    assert pillar['project_start_to_heightmap']=='OCEAN_FLOOR_WG'
    assert pillar['terrain_adaptation']=='none'
    assert air['count']==0
    assert void['count']==8 and void['bbox']==[10,10,21,23,5,7]
    assert root==resource
    assert root['entry_count_excluding_fingerprint']==len(files)-2
    assert root['content_sha256']==content_fingerprint(files)
    print('R3931_PACK',json.dumps({
        'input_sha256':sha(raw),
        'output_sha256':sha(out),
        'sea_level':128,
        'ocean_pillar_heightmap':'OCEAN_FLOOR_WG',
        'ocean_pillar_terrain_adaptation':'none',
        'ocean_pillar_cave_air':air['count'],
        'ocean_pillar_structure_void':void['count'],
        'ocean_pillar_void_bbox':void['bbox'],
        'content_fingerprint':root['content_sha256'],
        'entry_count':root['entry_count_excluding_fingerprint']
    }))

if __name__=='__main__':main()
