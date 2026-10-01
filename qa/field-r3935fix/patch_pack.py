#!/usr/bin/env python3
from pathlib import Path
import argparse,gzip,hashlib,importlib.util,io,json,struct,zipfile

ROOT=Path(__file__).resolve().parents[2]
R3931=ROOT/'qa/field-r3931/patch_pack.py'
NBT='data/structory_towers/structure/ocean_pillar.nbt'
FP_ROOT='neveroverworld-worldgen-fingerprint.json'
FP_RESOURCE='data/neverfolia/neveroverworld/worldgen_fingerprint.json'

OLD_POOLS=(
    'structory_towers:waystones/desert_fwaystone',
    'structory_towers:waystones/sandy_waystone',
)
NEW_POOL='minecraft:empty'

def need(v,m):
    if not v: raise ValueError(m)

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    need(spec is not None and spec.loader is not None,'cannot load '+str(path))
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

r31=load('r3931_patch',R3931)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def replace_nbt_string_once(data:bytes,old_text:str,new_text:str)->bytes:
    old=old_text.encode('utf-8')
    new=new_text.encode('utf-8')
    needle=struct.pack('>H',len(old))+old
    replacement=struct.pack('>H',len(new))+new
    need(data.count(needle)==1,'unexpected NBT string occurrence count for '+old_text)
    return data.replace(needle,replacement,1)

def patch_ocean_pillar(raw:bytes)->tuple[bytes,dict]:
    root=r31._nbt_parse(raw)
    blocks=root.get('blocks')
    palette=root.get('palette')
    need(isinstance(blocks,list) and isinstance(palette,list),'malformed ocean_pillar NBT')

    jigsaw_states={i for i,p in enumerate(palette) if isinstance(p,dict) and p.get('Name')=='minecraft:jigsaw'}
    need(len(jigsaw_states)==1,'unexpected jigsaw palette state count')
    jstate=next(iter(jigsaw_states))

    before=[]
    for b in blocks:
        if not isinstance(b,dict) or b.get('state')!=jstate: continue
        nbt=b.get('nbt') or {}
        before.append({
            'pos':list(b.get('pos',[])),
            'pool':nbt.get('pool'),
            'final_state':nbt.get('final_state'),
            'name':nbt.get('name'),
            'target':nbt.get('target'),
        })

    need(len(before)==2,'expected two ocean_pillar jigsaw connectors')
    pools=sorted(x['pool'] for x in before)
    need(pools==sorted(OLD_POOLS),'unexpected ocean_pillar waystone pools: '+repr(pools))
    need(all(x['final_state']=='minecraft:dark_prismarine' for x in before),
         'ocean_pillar jigsaw final_state drifted')

    data=gzip.decompress(raw)
    for old in OLD_POOLS:
        data=replace_nbt_string_once(data,old,NEW_POOL)
    out=gzip.compress(data,compresslevel=9,mtime=0)

    after_root=r31._nbt_parse(out)
    after_blocks=after_root.get('blocks',[])
    after_palette=after_root.get('palette',[])
    after_jigsaw_states={i for i,p in enumerate(after_palette) if isinstance(p,dict) and p.get('Name')=='minecraft:jigsaw'}
    need(len(after_jigsaw_states)==1,'patched jigsaw palette state count changed')
    after_state=next(iter(after_jigsaw_states))

    after=[]
    for b in after_blocks:
        if not isinstance(b,dict) or b.get('state')!=after_state: continue
        nbt=b.get('nbt') or {}
        after.append({
            'pos':list(b.get('pos',[])),
            'pool':nbt.get('pool'),
            'final_state':nbt.get('final_state'),
        })

    need(len(after)==2,'patched ocean_pillar jigsaw count changed')
    need(all(x['pool']==NEW_POOL for x in after),'waystone pool survived')
    need(all(x['final_state']=='minecraft:dark_prismarine' for x in after),
         'jigsaw final_state changed')
    return out,{'before':before,'after':after}

def patch(raw:bytes)->tuple[bytes,dict]:
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        infos=z.infolist()
        files={i.filename:z.read(i.filename) for i in infos if not i.is_dir()}

    for p in (NBT,FP_ROOT,FP_RESOURCE):
        need(p in files,'missing '+p)

    old_sha=sha(files[NBT])
    files[NBT],jigsaw=patch_ocean_pillar(files[NBT])

    # Preserve the previous R39.34 cavity repair: detached cells are absent,
    # and the template contains neither structure_void blocks nor explicit water.
    void=r31._state_geometry(files[NBT],'minecraft:structure_void')
    water=r31._state_geometry(files[NBT],'minecraft:water')
    need(void['count']==0,'structure_void returned after waystone patch')
    need(water['count']==0,'explicit water returned after waystone patch')

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
      'ocean_pillar_nbt_before_sha256':old_sha,
      'ocean_pillar_nbt_after_sha256':sha(files[NBT]),
      'waystone_child_pools_before':list(OLD_POOLS),
      'waystone_child_pools_after':[NEW_POOL,NEW_POOL],
      'jigsaws':jigsaw,
      'structure_void_after':0,
      'explicit_water_after':0,
      'content_fingerprint':fp
    }

def verify(raw:bytes):
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        files={i.filename:z.read(i.filename) for i in z.infolist() if not i.is_dir()}
    root=r31._nbt_parse(files[NBT])
    names=[p.get('Name') if isinstance(p,dict) else None for p in root.get('palette',[])]
    jstate={i for i,n in enumerate(names) if n=='minecraft:jigsaw'}
    need(len(jstate)==1,'jigsaw palette missing')
    jstate=next(iter(jstate))
    js=[]
    for b in root.get('blocks',[]):
        if isinstance(b,dict) and b.get('state')==jstate:
            nbt=b.get('nbt') or {}
            js.append((tuple(b.get('pos',[])),nbt.get('pool'),nbt.get('final_state')))
    need(len(js)==2,'expected two jigsaws after patch')
    need(all(pool==NEW_POOL for _pos,pool,_final in js),'non-empty child pool survived')
    need(all(final=='minecraft:dark_prismarine' for _pos,_pool,final in js),'final_state drifted')

    fp0=json.loads(files[FP_ROOT]);fp1=json.loads(files[FP_RESOURCE])
    need(fp0==fp1,'fingerprint docs differ')
    need(fp0.get('content_sha256')==r31.content_fingerprint(files),'fingerprint mismatch')
    return {'jigsaws':js,'fingerprint':fp0.get('content_sha256')}

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
    print('R3935_PACK '+json.dumps({
      'input_sha256':sha(raw),
      'output_sha256':sha(out),
      **meta,
      'audit':report
    },ensure_ascii=False))

if __name__=='__main__':main()
