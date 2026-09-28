#!/usr/bin/env python3
"""Independent stopped-Anvil verification, not the Java snapshot assertion.
Requires a positive natural ice-sheet regression and preserves registered pieces,
block entities and PDC. Never edits region files or invents missing sections.
"""
from pathlib import Path
import collections,importlib.util,json,re
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'artifacts';PHASES=OUT/'r3913-phases'
def need(ok,msg):
    if not ok:raise ValueError(msg)
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
nbt=load('ice_saved_nbt',ROOT/'scripts/hash-never-nether-chunks.py')
decode=load('ice_section_reader',ROOT/'scripts/probe-never-overworld-trees-villages-r1.py')
runtime=load('ice_snapshot_reader',ROOT/'qa/field-r3913/runtime.py')
WATER=('minecraft:water',(('level','0'),));ICE={'minecraft:ice','minecraft:packed_ice','minecraft:blue_ice'}
WITNESS={(x,62,z) for x,z in ((-3014,-3558),(-3013,-3558),(-3014,-3557),(-3012,-3558),(-3013,-3557),(-3014,-3556),(-3012,-3557),(-3013,-3556),(-3015,-3556),(-3014,-3555),(-3012,-3556),(-3013,-3555),(-3015,-3555),(-3014,-3554),(-3011,-3556),(-3012,-3555),(-3013,-3554),(-3011,-3555),(-3012,-3554))}
def region(phase):
    values=list((PHASES/phase/'saved').rglob('overworld/region'));need(len(values)==1,'No unique saved Overworld for '+phase);return values[0]
def root(phase,cx,cz,full=True):
    value=nbt.read_chunk_nbt(region(phase),cx,cz)
    need((value.get('xPos'),value.get('zPos'))==(cx,cz),'Mismatched saved coordinates')
    if full:need(value.get('Status')=='minecraft:full','Target is not FULL')
    return value

def states(value):
    sections={}
    for s in value.get('sections',[]):
        if 'block_states' not in s:continue
        sy=s['Y'];need(sy not in sections,'Duplicate section');sections[sy]=s
    need(all(sy in sections for sy in range(-32,32)),'Missing section cannot be treated as air')
    result=[]
    for sy in range(-32,32):
        result.extend((s['Name'],tuple(sorted(s.get('Properties',{}).items()))) for s in decode.unpack_section(sections[sy]))
    need(len(result)==262144,'Incomplete saved volume');return result

def metadata(value):
    need('block_entities' in value and 'structures' in value,'Missing saved metadata section')
    entities=value['block_entities'];need(isinstance(entities,list),'Invalid block entities')
    return {'block_entities':sorted(entities,key=lambda v:json.dumps(v,sort_keys=True)),
            'structures':value['structures'],
            'pdc':{k:v for k,v in value.items() if 'bukkit' in k.lower() or 'persistent' in k.lower()}}

def saved_boxes(phase,value):
    def unpack(v):
        need(isinstance(v,dict) and isinstance(v.get('$int_array'),list),'Bad box encoding');b=v['$int_array']
        need(len(b)==6 and all(type(i) is int for i in b),'Bad box values')
        need(all(b[i]<=b[i+3] for i in range(3)),'Inverted box');return b
    structure=value['structures'];sources=[];boxes=[]
    for s in structure.get('starts',{}).values():
        if s.get('id')!='INVALID':sources.append(s)
    for key,values in structure.get('References',{}).items():
        need(isinstance(values.get('$long_array'),list),'Bad reference array')
        for packed in values['$long_array']:
            cx=packed&0xffffffff;cz=(packed>>32)&0xffffffff
            if cx>=2**31:cx-=2**32
            if cz>=2**31:cz-=2**32
            other=root(phase,cx,cz,False);s=other.get('structures',{}).get('starts',{}).get(key)
            need(s is not None and s.get('id')!='INVALID','Unresolved saved structure protecting a changed chunk');sources.append(s)
    for start in sources:
        pieces=start.get('Children');need(isinstance(pieces,list) and len(pieces)>0,'Missing saved pieces')
        for p in pieces:boxes.append(unpack(p.get('BB')))
    def mine_records(v):
        if isinstance(v,dict):
            for k,child in v.items():
                if k=='neverfolia:dry_mines_r12':
                    a=child.get('$int_array');need(isinstance(a,list) and len(a)>=2 and a[0]==1 and 1<=a[1]<=4096 and len(a)==2+6*a[1],'Bad mine PDC')
                    for off in range(2,len(a),6):boxes.append(unpack({'$int_array':a[off:off+6]}))
                else:mine_records(child)
        elif isinstance(v,list):
            for child in v:mine_records(child)
    mine_records(metadata(value)['pdc']);return boxes

def covered(p,boxes):
    return any(all(b[k]-1<=p[k]<=b[k+3]+1 for k in range(3)) for b in boxes)

def main():
    r={'pass':False,'all_ice_fixed':False,'target_chunks':len(runtime.TARGETS),'comparisons':{},'observed_to_saved_differences':0,'protected_changes':0,'witness_expected':len(WITNESS)}
    total=collections.Counter();transitions=collections.Counter();witness=set();negative_ice=collections.Counter();pdc_fields=set();cache={};changes=[]
    try:
        for cx,cz in runtime.TARGETS:
            roots={p:root(p,cx,cz) for p in ('parent','off','candidate','restart')}
            data={p:states(v) for p,v in roots.items()};meta={p:metadata(v) for p,v in roots.items()}
            for p,v in meta.items():pdc_fields.update(v['pdc'])
            for p in roots:
                snapshot=runtime.blocks(PHASES/p/'observed'/f'{cx}_{cz}.blocks.gz',(cx,cz));canonical=[]
                for text in snapshot:
                    if text not in cache:
                        m=re.fullmatch(r'Block\{([^}]+)\}(?:\[(.*)\])?',text);need(m is not None,'Unknown snapshot state '+text)
                        props=tuple(sorted(tuple(s.split('=',1)) for s in m[2].split(','))) if m[2] else ()
                        cache[text]=(m[1],props)
                    canonical.append(cache[text])
                mismatch=sum(a!=b for a,b in zip(canonical,data[p]));r['observed_to_saved_differences']+=mismatch
                need(mismatch==0,'Live observation differs from persisted state: '+p+f' {cx},{cz}')
                negative_ice[p]+=sum(s[0] in ICE for s in data[p][:(512<<8)])
            for label,left,right,allow in (('parent_vs_off','parent','off',False),('off_vs_candidate','off','candidate',True),('candidate_vs_restart','candidate','restart',False)):
                need(meta[left]==meta[right],'Saved PDC/structure/block-entity change: '+label+f' {cx},{cz}')
                boxes=None
                for i,(a,b) in enumerate(zip(data[left],data[right])):
                    if a==b:continue
                    total[label]+=1;point=(cx*16+(i&15),-512+(i>>8),cz*16+((i>>4)&15))
                    need(allow and a[0] in ICE and b==WATER,'Unexpected saved block mutation '+str((label,point,a,b)))
                    if boxes is None:boxes=saved_boxes(left,roots[left])
                    need(not covered(point,boxes),'Changed ice inside actual saved structure/mine envelope')
                    changes.append({'point':point,'before':a,'after':b});transitions[a[0]+' -> minecraft:water[level=0]']+=1
                    if point in WITNESS:witness.add(point)
            if (cx,cz)==(-189,-223):
                for x,y,z in WITNESS:
                    i=((y+512)<<8)|((z&15)<<4)|(x&15)
                    need(data['off'][i][0] in ICE,'Natural ice witness no longer reproduced')
                    need(data['candidate'][i]==WATER and data['restart'][i]==WATER,'Witness ice not removed/persisted')
            print('SAVED_ICE_CHUNK',cx,cz,'verified',flush=True)
        need(pdc_fields,'No actual persisted PDC fields inspected')
        need(witness==WITNESS,'Did not fix the complete natural sheet')
        need(len(set(negative_ice.values()))==1,'Changed below-zero ice decoration')
        need(total['off_vs_candidate']>0,'A no-op cannot pass field regression')
        r.update({'pass':True,'comparisons':{label:total[label] for label in ('parent_vs_off','off_vs_candidate','candidate_vs_restart')},
            'transitions':dict(transitions),'natural_witness_fixed':len(witness),'changed_positions':changes,
            'below_zero_ice_preserved':dict(negative_ice),'pdc_fields':sorted(pdc_fields),
            'states_per_comparison':len(runtime.TARGETS)*262144,'block_entity_pdc_structure_equal':True})
    except Exception as e:r['error']=repr(e)
    finally:(OUT/'r3913-saved-verification.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n')
    print('R3913_SAVED_CHECK '+json.dumps({k:v for k,v in r.items() if k!='changed_positions'}),flush=True)
    need(r['pass'],'Independent saved-world regression failed')
if __name__=='__main__':main()
