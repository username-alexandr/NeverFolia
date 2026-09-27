#!/usr/bin/env python3
"""Read only already retained real-world evidence. Does not rerun or modify a world."""
from pathlib import Path,PurePosixPath
import collections,hashlib,importlib.util,json,zipfile
ROOT=Path(__file__).resolve().parents[2]
E=ROOT/'evidence';OUT=ROOT/'review';OUT.mkdir(exist_ok=False)
WORK=ROOT/'.work/r395-review';WORK.mkdir(parents=True,exist_ok=False)

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

def save(path,value):path.write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n')

def extract(path,dest):
    dest.mkdir(exist_ok=False)
    with zipfile.ZipFile(path) as z:
        if z.testzip() is not None or len(z.namelist())!=len(set(z.namelist())):raise ValueError('Invalid evidence archive')
        for info in z.infolist():
            p=PurePosixPath(info.filename)
            if p.is_absolute() or '..' in p.parts or '\\' in info.filename:raise ValueError('Unsafe evidence path')
            if info.is_dir():continue
            target=dest.joinpath(*p.parts);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(z.read(info))

runtime=json.loads((E/'runtime.json').read_text())
if runtime['candidate_core_sha256']!='8b387b040b9b3b2a1412d364dbc9eaa0bbb763f69b249c7c213b19812da8a4d5':raise ValueError('Wrong failed candidate evidence')
if runtime['reverse_equal'] is not False:raise ValueError('Unexpected order test result')
observer=load('review_observer',ROOT/'scripts/probe-never-overworld-trees-villages-r1.py')
paired=load('review_paired',ROOT/'scripts/probe-never-overworld-paired-r12.py')
nbt=observer.load_nbt(ROOT)
phases={}
for name in ('baseline','candidate','restart','reverse'):
    archive=E/(name+'-saved-regions.zip');dest=WORK/name;extract(archive,dest)
    phase=json.loads((E/(name+'-phase.json')).read_text())
    if phase['exit_code']!=0 or phase['pass'] is not True:raise ValueError('Unsuccessful retained phase')
    targets=[(r['chunk_x'],r['chunk_z']) for r in phase['observed']['chunks']]
    volume=paired.saved_volume(observer,nbt,dest/'world/dimensions/minecraft/overworld/region',targets,{'normal_stop':True,'exit_code':0})
    phases[name]=(phase,volume)

report={'source_run':36324714489,'source_core_sha256':runtime['candidate_core_sha256'],'read_only':True,'differences':[],'proof_differences':[]}
changes=collections.Counter();limit=1000
for text in runtime['reverse_changed_chunks']:
    cx,cz=map(int,text.split(','));a=phases['candidate'][1];b=phases['reverse'][1];base=phases['baseline'][1]
    for sy in range(-32,32):
        left=a.section((cx,sy,cz));right=b.section((cx,sy,cz));old=base.section((cx,sy,cz))
        for i,(l,r) in enumerate(zip(left,right)):
            if l==r:continue
            x=cx*16+(i&15);y=sy*16+(i>>8);z=cz*16+((i>>4)&15)
            key=l['Name']+' => '+r['Name'];changes[key]+=1
            row={'position':[x,y,z],'chunk':[cx,cz],'forward':l,'reverse':r,'baseline_forward':old[i],
                 'chunk_face':(x&15) in (0,15) or (z&15) in (0,15),'in_water_hash_range':-511<=y<=128,
                 'neighbours':[]}
            for dx,dy,dz in ((1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1)):
                pos=(x+dx,y+dy,z+dz)
                def at(v):
                    try:return v.at(*pos)
                    except (KeyError,IndexError,ValueError):return None
                row['neighbours'].append({'position':pos,'forward':at(a),'reverse':at(b),'baseline_forward':at(base)})
            if len(report['differences'])<limit:report['differences'].append(row)
    for phase_name in ('candidate','reverse'):
        rows=[json.loads(p.read_text()) for p in (E/('proof-'+phase_name)).glob('*.json')]
        selected=[r for r in rows if (r['chunk_x'],r['chunk_z'])==(cx,cz)]
        report['proof_differences'].append({'phase':phase_name,'chunk':[cx,cz],'reports':selected})
    for phase_name in ('candidate','reverse','baseline'):
        root=phases[phase_name][1].roots[(cx,cz)]
        summary={'heightmaps':root.get('Heightmaps'),'structures':root.get('structures'),'ChunkBukkitValues':root.get('ChunkBukkitValues')}
        save(OUT/f'{phase_name}-{cx}-{cz}-metadata.json',summary)
report['difference_counts']=dict(changes);report['total_differences']=sum(changes.values());report['truncated']=sum(changes.values())>limit
report['isolated_air_examples']={}
report['ice_by_phase']={}
for name,(phase,volume) in phases.items():
    report['isolated_air_examples'][name]=[p for row in phase['observed']['chunks'] for p in row['air_examples']]
    report['ice_by_phase'][name]=[{'chunk':[row['chunk_x'],row['chunk_z']],'count':row['ice_blocks'],'isolated':row['single_ice_with_six_aquatic_neighbours'],'examples':row['ice_examples']} for row in phase['observed']['chunks'] if row['ice_blocks']]
report['enchantment_visibility']=phases['candidate'][0]['observed']['enchantment_visibility']
save(OUT/'difference-review.json',report)
print(json.dumps(report,indent=2,ensure_ascii=False),flush=True)
