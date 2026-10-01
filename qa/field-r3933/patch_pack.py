#!/usr/bin/env python3
from pathlib import Path
import argparse,hashlib,importlib.util,io,json,zipfile

ROOT=Path(__file__).resolve().parents[2]
R3931=ROOT/'qa/field-r3931/patch_pack.py'
R3932=ROOT/'qa/field-r3932/patch_pack.py'

TRIDENT='data/nova_structures/worldgen/structure/trident_trial_monument.json'
CONDUIT='data/nova_structures/worldgen/structure/conduit_ruin.json'
OCEAN_PILLAR='data/structory_towers/worldgen/structure/ocean_pillar.json'
OCEAN_PILLAR_POOL='data/structory_towers/worldgen/template_pool/ocean_pillar.json'
CONDUIT_PROCESSOR='data/nova_structures/worldgen/processor_list/conduit_ruin_degradation.json'
WATER_PROCESSOR='data/neverfolia/worldgen/processor_list/underwater_preserve_water.json'
FP_ROOT='neveroverworld-worldgen-fingerprint.json'
FP_RESOURCE='data/neverfolia/neveroverworld/worldgen_fingerprint.json'

def need(v,m):
    if not v: raise ValueError(m)

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    need(spec is not None and spec.loader is not None,'cannot load '+str(path))
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

r31=load('r3931_patch',R3931)
r32=load('r3932_patch',R3932)

def sha(raw): return hashlib.sha256(raw).hexdigest()

def is_water_preserve_rule(rule,block):
    try:
        return (
          rule['input_predicate']['predicate_type']=='minecraft:block_match'
          and rule['input_predicate']['block']==block
          and rule['location_predicate']['predicate_type']=='minecraft:block_match'
          and rule['location_predicate']['block']=='minecraft:water'
          and rule['output_state']['Name']=='minecraft:water'
        )
    except Exception:
        return False

def patch_conduit_water(files):
    d=json.loads(files[CONDUIT_PROCESSOR])
    need(isinstance(d.get('processors'),list) and d['processors'],'bad conduit processor list')
    rule_proc=None
    for p in d['processors']:
        if p.get('processor_type')=='minecraft:rule' and isinstance(p.get('rules'),list):
            if any(is_water_preserve_rule(x,'minecraft:air') for x in p['rules']):
                rule_proc=p;break
    need(rule_proc is not None,'conduit AIR->WATER rule processor missing')
    added=0
    for block in ('minecraft:air','minecraft:cave_air'):
        if not any(is_water_preserve_rule(x,block) for x in rule_proc['rules']):
            rule_proc['rules'].append({
              'input_predicate':{'block':block,'predicate_type':'minecraft:block_match'},
              'location_predicate':{'block':'minecraft:water','predicate_type':'minecraft:block_match'},
              'output_state':{'Name':'minecraft:water'}
            })
            added+=1
    files[CONDUIT_PROCESSOR]=(json.dumps(d,ensure_ascii=False,indent=2)+'\n').encode()
    return {'added_rules':added,'air':True,'cave_air':True}

def patch_ocean_pillar_water(files):
    d=json.loads(files[OCEAN_PILLAR_POOL])
    changed=0;seen=0
    for row in d.get('elements',[]):
        el=row.get('element')
        if not isinstance(el,dict): continue
        if el.get('location')=='structory_towers:ocean_pillar':
            seen+=1
            if el.get('processors')!='neverfolia:underwater_preserve_water':
                el['processors']='neverfolia:underwater_preserve_water';changed+=1
    need(seen==1,'unexpected ocean_pillar pool layout')
    files[OCEAN_PILLAR_POOL]=(json.dumps(d,ensure_ascii=False,indent=2)+'\n').encode()
    return {'elements':seen,'changed':changed}

def patch_trident_height(files):
    d=json.loads(files[TRIDENT])
    need(d.get('project_start_to_heightmap')=='OCEAN_FLOOR_WG','trident lost OCEAN_FLOOR_WG')
    need(d.get('terrain_adaptation')=='none','trident terrain adaptation must stay none')
    need(d.get('start_height')=={'absolute':0},'unexpected R39.32 trident start height '+repr(d.get('start_height')))
    d['start_height']={'absolute':-3}
    files[TRIDENT]=(json.dumps(d,ensure_ascii=False,indent=2)+'\n').encode()
    return d

def patch(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        infos=z.infolist()
        files={i.filename:z.read(i.filename) for i in infos if not i.is_dir()}
    for p in (TRIDENT,CONDUIT,OCEAN_PILLAR,OCEAN_PILLAR_POOL,CONDUIT_PROCESSOR,WATER_PROCESSOR,FP_ROOT,FP_RESOURCE):
        need(p in files,'missing '+p)

    small_before={CONDUIT:files[CONDUIT],OCEAN_PILLAR:files[OCEAN_PILLAR]}
    trident=patch_trident_height(files)
    pillar_water=patch_ocean_pillar_water(files)
    conduit_water=patch_conduit_water(files)

    # Contract from the user: small ocean structures get water fixes only.
    for p,before in small_before.items():
        need(files[p]==before,'R39.33 changed small-structure placement: '+p)

    fp=r31.content_fingerprint(files)
    for p in (FP_ROOT,FP_RESOURCE):
        d=json.loads(files[p]);d['content_sha256']=fp;d['entry_count_excluding_fingerprint']=len(files)-2
        files[p]=(json.dumps(d,ensure_ascii=False,indent=2)+'\n').encode()

    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as dst:
        known={i.filename:i for i in infos if not i.is_dir()}
        for n in [i.filename for i in infos if not i.is_dir()]:
            dst.writestr(known[n],files[n])
    result=out.getvalue()
    return result,{
      'trident_start_offset':-3,
      'trident_heightmap':'OCEAN_FLOOR_WG',
      'trident_terrain_adaptation':'none',
      'small_structure_placement_unchanged':True,
      'ocean_pillar_water':pillar_water,
      'conduit_water':conduit_water,
      'content_fingerprint':fp
    }

def verify(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        need(z.testzip() is None,'bad output ZIP')
        files={i.filename:z.read(i.filename) for i in z.infolist() if not i.is_dir()}
    trident=json.loads(files[TRIDENT])
    conduit=json.loads(files[CONDUIT])
    pillar=json.loads(files[OCEAN_PILLAR])
    need(trident.get('start_height')=={'absolute':-3},'trident offset is not -3')
    need(trident.get('project_start_to_heightmap')=='OCEAN_FLOOR_WG','trident not seabed projected')
    need(trident.get('terrain_adaptation')=='none','trident may deform seabed')
    # Small structures remain at the R39.32 placement contract.
    need(conduit.get('start_height')=={'absolute':0},'conduit height changed')
    need(conduit.get('project_start_to_heightmap')=='OCEAN_FLOOR_WG','conduit floor anchor changed')
    need(conduit.get('terrain_adaptation')=='none','conduit terrain policy changed')
    need(pillar.get('start_height')=={'absolute':0},'ocean_pillar height changed')
    need(pillar.get('project_start_to_heightmap')=='OCEAN_FLOOR_WG','ocean_pillar floor anchor changed')
    need(pillar.get('terrain_adaptation')=='none','ocean_pillar terrain policy changed')

    pool=json.loads(files[OCEAN_PILLAR_POOL])
    elems=[x.get('element',{}) for x in pool.get('elements',[]) if isinstance(x,dict)]
    target=[e for e in elems if e.get('location')=='structory_towers:ocean_pillar']
    need(len(target)==1 and target[0].get('processors')=='neverfolia:underwater_preserve_water','ocean_pillar water processor missing')

    cp=json.loads(files[CONDUIT_PROCESSOR])
    rules=[]
    for p in cp.get('processors',[]):
        if p.get('processor_type')=='minecraft:rule': rules.extend(p.get('rules',[]))
    need(any(is_water_preserve_rule(x,'minecraft:air') for x in rules),'conduit AIR water guard missing')
    need(any(is_water_preserve_rule(x,'minecraft:cave_air') for x in rules),'conduit CAVE_AIR water guard missing')

    generic=json.loads(files[WATER_PROCESSOR])
    grules=generic['processors'][0]['rules']
    need(any(is_water_preserve_rule(x,'minecraft:air') for x in grules),'generic AIR water guard missing')
    need(any(is_water_preserve_rule(x,'minecraft:cave_air') for x in grules),'generic CAVE_AIR water guard missing')

    fp0=json.loads(files[FP_ROOT]);fp1=json.loads(files[FP_RESOURCE])
    need(fp0==fp1,'fingerprint documents differ')
    need(fp0.get('content_sha256')==r31.content_fingerprint(files),'fingerprint mismatch')

    _pools,trident_elements=r32.patch_trident_pools(dict(files))
    conduit_elements=r32.audit_conduit_pools(files)
    pillar_air=r31._state_geometry(files['data/structory_towers/structure/ocean_pillar.nbt'],'minecraft:cave_air')
    pillar_void=r31._state_geometry(files['data/structory_towers/structure/ocean_pillar.nbt'],'minecraft:structure_void')
    need(pillar_air['count']==0 and pillar_void['count']==8,'R39.31 ocean_pillar NBT repair regressed')
    return {
      'trident_definition':trident,
      'conduit_definition':conduit,
      'ocean_pillar_definition':pillar,
      'trident_pool_elements':trident_elements,
      'conduit_pool_elements':conduit_elements,
      'ocean_pillar':{'cave_air':pillar_air['count'],'structure_void':pillar_void['count']},
      'small_structure_water_guards':{
        'ocean_pillar_pool':'neverfolia:underwater_preserve_water',
        'conduit_air':True,
        'conduit_cave_air':True
      },
      'fingerprint':fp0.get('content_sha256')
    }

def main():
    ap=argparse.ArgumentParser();ap.add_argument('src',type=Path);ap.add_argument('dst',type=Path);a=ap.parse_args()
    raw=a.src.read_bytes();out,meta=patch(raw);report=verify(out)
    a.dst.parent.mkdir(parents=True,exist_ok=True);a.dst.write_bytes(out)
    print('R3933_PACK '+json.dumps({'input_sha256':sha(raw),'output_sha256':sha(out),**meta,'audit':report},ensure_ascii=False))

if __name__=='__main__':main()
