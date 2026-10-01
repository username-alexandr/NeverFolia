#!/usr/bin/env python3
from pathlib import Path
import argparse,hashlib,importlib.util,io,json,struct,zipfile

ROOT=Path(__file__).resolve().parents[2]
R3931=ROOT/'qa/field-r3931/patch_pack.py'
CONDUIT='data/nova_structures/worldgen/structure/conduit_ruin.json'
TRIDENT='data/nova_structures/worldgen/structure/trident_trial_monument.json'
PROCESSOR='data/neverfolia/worldgen/processor_list/underwater_preserve_water.json'
FP_ROOT='neveroverworld-worldgen-fingerprint.json'
FP_RESOURCE='data/neverfolia/neveroverworld/worldgen_fingerprint.json'
TRIDENT_POOL_PREFIX='data/nova_structures/worldgen/template_pool/trident_monument/'
CONDUIT_POOL_PREFIX='data/nova_structures/worldgen/template_pool/conduit_ruin/'
TRIDENT_NBT_PREFIX='data/nova_structures/structure/trident_trials_monument/'
CONDUIT_NBT_PREFIX='data/nova_structures/structure/conduit_ruin/'
ANCIENT_CISTERN='data/neverfolia/structure/never_overworld/structures/ancient_cistern.nbt'

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    if spec is None or spec.loader is None: raise RuntimeError('cannot load '+str(path))
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

r31=load('r3931_patch_pack',R3931)

def sha(raw):return hashlib.sha256(raw).hexdigest()

def water_processor():
    return {
      "processors":[{
        "processor_type":"minecraft:rule",
        "rules":[
          {
            "input_predicate":{"block":"minecraft:air","predicate_type":"minecraft:block_match"},
            "location_predicate":{"block":"minecraft:water","predicate_type":"minecraft:block_match"},
            "output_state":{"Name":"minecraft:water"}
          },
          {
            "input_predicate":{"block":"minecraft:cave_air","predicate_type":"minecraft:block_match"},
            "location_predicate":{"block":"minecraft:water","predicate_type":"minecraft:block_match"},
            "output_state":{"Name":"minecraft:water"}
          }
        ]
      }]
    }

def patch_structure(files,path,*,heightmap,offset):
    d=json.loads(files[path])
    d['start_height']={'absolute':offset}
    d['project_start_to_heightmap']=heightmap
    d['terrain_adaptation']='none'
    files[path]=(json.dumps(d,ensure_ascii=False,indent=2)+'\n').encode()
    return d

def patch_trident_pools(files):
    changed=0
    pools=0
    for path in sorted(files):
        if not path.startswith(TRIDENT_POOL_PREFIX) or not path.endswith('.json'):continue
        d=json.loads(files[path]);dirty=False;pools+=1
        for row in d.get('elements',[]):
            el=row.get('element')
            if not isinstance(el,dict):continue
            loc=el.get('location')
            if isinstance(loc,str) and loc.startswith('nova_structures:trident_trials_monument/'):
                if el.get('processors')!='neverfolia:underwater_preserve_water':
                    el['processors']='neverfolia:underwater_preserve_water';dirty=True
                changed+=1
        if dirty:files[path]=(json.dumps(d,ensure_ascii=False,indent=2)+'\n').encode()
    if changed<300:raise ValueError('Too few Trident Monument pool elements patched: '+str(changed))
    return pools,changed

def audit_conduit_pools(files):
    checked=0
    bad=[]
    for path in sorted(files):
        if not path.startswith(CONDUIT_POOL_PREFIX) or not path.endswith('.json'):continue
        d=json.loads(files[path])
        for row in d.get('elements',[]):
            el=row.get('element')
            if not isinstance(el,dict):continue
            loc=el.get('location')
            if isinstance(loc,str) and loc.startswith('nova_structures:conduit_ruin/'):
                checked+=1
                if el.get('processors')!='nova_structures:conduit_ruin_degradation':
                    bad.append([path,loc,el.get('processors')])
    if bad:raise ValueError('Conduit Ruin element without water-preserving processor: '+repr(bad[:8]))
    if checked<40:raise ValueError('Too few Conduit Ruin structural elements audited: '+str(checked))
    return checked

def nbt_family(files,prefix):
    out={'files':0,'air':0,'cave_air':0,'water':0,'structure_void':0,'boundary_air':0}
    for path,raw in files.items():
        if not path.startswith(prefix) or not path.endswith('.nbt'):continue
        root=r31._nbt_parse(raw);size=root.get('size');palette=root.get('palette');blocks=root.get('blocks')
        if not isinstance(size,list) or len(size)!=3 or not isinstance(palette,list) or not isinstance(blocks,list):continue
        names=[p.get('Name') if isinstance(p,dict) else None for p in palette]
        out['files']+=1
        for b in blocks:
            if not isinstance(b,dict):continue
            idx=b.get('state');pos=b.get('pos')
            if not isinstance(idx,int) or idx<0 or idx>=len(names) or not isinstance(pos,list) or len(pos)!=3:continue
            name=names[idx]
            if name=='minecraft:air':
                out['air']+=1
                if pos[0] in (0,size[0]-1) or pos[1] in (0,size[1]-1) or pos[2] in (0,size[2]-1):out['boundary_air']+=1
            elif name=='minecraft:cave_air':
                out['cave_air']+=1
                if pos[0] in (0,size[0]-1) or pos[1] in (0,size[1]-1) or pos[2] in (0,size[2]-1):out['boundary_air']+=1
            elif name=='minecraft:water':out['water']+=1
            elif name=='minecraft:structure_void':out['structure_void']+=1
    return out

def patch(raw):
    # Input is the already-built R39.31 candidate. Do not reapply its NBT
    # migration: ocean_pillar cave_air has already become structure_void.
    base=raw
    with zipfile.ZipFile(io.BytesIO(base)) as z:
        infos=z.infolist()
        files={i.filename:z.read(i.filename) for i in infos if not i.is_dir()}

    conduit=patch_structure(files,CONDUIT,heightmap='OCEAN_FLOOR_WG',offset=0)
    trident=patch_structure(files,TRIDENT,heightmap='OCEAN_FLOOR_WG',offset=0)
    files[PROCESSOR]=(json.dumps(water_processor(),ensure_ascii=False,indent=2)+'\n').encode()
    trident_pools,trident_elements=patch_trident_pools(files)
    conduit_elements=audit_conduit_pools(files)

    # Fingerprint must describe the final R39.32 bytes, not the intermediate R39.31 pack.
    fp=r31.content_fingerprint(files)
    for name in (FP_ROOT,FP_RESOURCE):
        d=json.loads(files[name]);d['content_sha256']=fp;d['entry_count_excluding_fingerprint']=len(files)-2
        files[name]=(json.dumps(d,ensure_ascii=False,indent=2)+'\n').encode()

    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as dst:
        known={i.filename:i for i in infos if not i.is_dir()}
        for name in [i.filename for i in infos if not i.is_dir()]:
            dst.writestr(known[name],files[name])
        if PROCESSOR not in known:
            dst.writestr(PROCESSOR,files[PROCESSOR])

    result=out.getvalue()
    return result,{
      'conduit':conduit,'trident':trident,
      'trident_template_pools':trident_pools,
      'trident_elements_water_preserved':trident_elements,
      'conduit_elements_water_preserved':conduit_elements,
      'content_fingerprint':fp
    }

def verify(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        if z.testzip() is not None:raise ValueError('Bad output ZIP')
        files={i.filename:z.read(i.filename) for i in z.infolist() if not i.is_dir()}
    for path in (CONDUIT,TRIDENT,PROCESSOR,FP_ROOT,FP_RESOURCE):
        if path not in files:raise ValueError('Missing '+path)
    conduit=json.loads(files[CONDUIT]);trident=json.loads(files[TRIDENT])
    for name,d in [('conduit',conduit),('trident',trident)]:
        if d.get('start_height')!={'absolute':0}:raise ValueError(name+' start_height not seabed-relative zero')
        if d.get('project_start_to_heightmap')!='OCEAN_FLOOR_WG':raise ValueError(name+' not projected to ocean floor')
        if d.get('terrain_adaptation')!='none':raise ValueError(name+' terrain adaptation must be none')
    proc=json.loads(files[PROCESSOR])
    rules=proc['processors'][0]['rules']
    inputs={r['input_predicate'].get('block') for r in rules}
    if inputs!={'minecraft:air','minecraft:cave_air'}:raise ValueError('underwater processor rule set drifted')
    pools,elements=patch_trident_pools(dict(files))
    conduit_elements=audit_conduit_pools(files)
    fp0=json.loads(files[FP_ROOT]);fp1=json.loads(files[FP_RESOURCE])
    if fp0!=fp1 or fp0.get('content_sha256')!=r31.content_fingerprint(files):raise ValueError('Fingerprint mismatch')

    ocean_pillar=r31._state_geometry(files['data/structory_towers/structure/ocean_pillar.nbt'],'minecraft:cave_air')
    ocean_void=r31._state_geometry(files['data/structory_towers/structure/ocean_pillar.nbt'],'minecraft:structure_void')
    if ocean_pillar['count']!=0 or ocean_void['count']!=8:raise ValueError('R39.31 ocean pillar repair lost')

    cistern_air=r31._state_geometry(files[ANCIENT_CISTERN],'minecraft:air')
    cistern_water=r31._state_geometry(files[ANCIENT_CISTERN],'minecraft:water')
    return {
      'conduit_definition':conduit,
      'trident_definition':trident,
      'trident_pool_elements':elements,
      'conduit_pool_elements':conduit_elements,
      'conduit_nbt':nbt_family(files,CONDUIT_NBT_PREFIX),
      'trident_nbt':nbt_family(files,TRIDENT_NBT_PREFIX),
      'ancient_cistern':{'air':cistern_air['count'],'water':cistern_water['count'],'open_ocean_policy':'blocked_by_R39.32_core'},
      'ocean_pillar':{'cave_air':ocean_pillar['count'],'structure_void':ocean_void['count']},
      'fingerprint':fp0.get('content_sha256')
    }

def main():
    ap=argparse.ArgumentParser();ap.add_argument('src',type=Path);ap.add_argument('dst',type=Path);a=ap.parse_args()
    raw=a.src.read_bytes();out,meta=patch(raw);report=verify(out)
    a.dst.parent.mkdir(parents=True,exist_ok=True);a.dst.write_bytes(out)
    print('R3932_PACK '+json.dumps({
      'input_sha256':sha(raw),'output_sha256':sha(out),**meta,'audit':report
    },ensure_ascii=False))

if __name__=='__main__':main()
