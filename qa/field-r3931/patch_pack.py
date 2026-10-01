#!/usr/bin/env python3
from pathlib import Path
import argparse,hashlib,io,json,zipfile,struct

TARGET='data/minecraft/worldgen/noise_settings/overworld.json'
OCEAN_PILLAR='data/structory_towers/worldgen/structure/ocean_pillar.json'
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

def patch(raw:bytes)->bytes:
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        files={info.filename:z.read(info.filename) for info in z.infolist() if not info.is_dir()}
        if TARGET not in files:raise ValueError('NeverOverworld noise settings missing')
        if OCEAN_PILLAR not in files:raise ValueError('Structory ocean_pillar structure settings missing')
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
        root=json.loads(z.read(FP_ROOT))
        resource=json.loads(z.read(FP_RESOURCE))
        files={info.filename:z.read(info.filename) for info in z.infolist() if not info.is_dir()}
    assert data['sea_level']==128
    assert pillar['project_start_to_heightmap']=='OCEAN_FLOOR_WG'
    assert pillar['terrain_adaptation']=='none'
    assert root==resource
    assert root['entry_count_excluding_fingerprint']==len(files)-2
    assert root['content_sha256']==content_fingerprint(files)
    print('R3931_PACK',json.dumps({
        'input_sha256':sha(raw),
        'output_sha256':sha(out),
        'sea_level':128,
        'ocean_pillar_heightmap':'OCEAN_FLOOR_WG',
        'ocean_pillar_terrain_adaptation':'none',
        'content_fingerprint':root['content_sha256'],
        'entry_count':root['entry_count_excluding_fingerprint']
    }))

if __name__=='__main__':main()
