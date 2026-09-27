#!/usr/bin/env python3
"""Read existing evidence; do not run a server or change generation results."""
from __future__ import annotations
import collections
import hashlib
import json
from pathlib import Path
import sys
import zipfile
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'qa/review-r395'))
import review
import verify_saved as saved


def inspect(root):
    plan=json.loads((root/'plan.json').read_text())
    result=json.loads((root/'r395-water-result.json').read_text())
    live=json.loads((root/'live/r38-live-qa.json').read_text())
    expected={tuple(p) for p in plan['target_chunks']}
    report={'run_id':plan['run_id'],'inputs':plan['inputs'],'production_accepted':False,
            'source_result':{k:v for k,v in result.items() if k not in ('r38-water-audit','r38-reverse-audit','phases')},
            'scope':'Read-only localization of existing failed R395 evidence, not a new game run'}
    first=live['phases']['r38-trial-water']['water_hashes']
    reverse=live['phases']['r38-reverse-water']['water_hashes']
    report['saved_hash_difference_chunks']=[k for k in sorted(first.keys()|reverse.keys()) if first.get(k)!=reverse.get(k)]
    report['phase_hash_counts']={k:len(v.get('water_hashes',{})) for k,v in live['phases'].items()}
    nbt=saved.load('r395_details_observer',ROOT/'scripts/probe-never-overworld-trees-villages-r1.py').load_nbt(ROOT)
    observer=saved.load('r395_details_volume',ROOT/'scripts/probe-never-overworld-trees-villages-r1.py')
    masks={key:review.read_masks(root/'live'/folder,plan['run_id']) for key,folder in (('trial','r38-water-audit'),('reverse','r38-reverse-audit'))}
    failures={key:result[folder]['failing_chunks'] for key,folder in (('trial','r38-water-audit'),('reverse','r38-reverse-audit'))}
    with zipfile.ZipFile(root/'saved-worlds-evidence.zip') as archive:
        regions={key:saved.Regions(archive,key+'/world/dimensions/minecraft/overworld/region',nbt) for key in ('trial','reverse')}
        report['failed_columns']={}
        for key,rows in failures.items():
            reports=[]
            for row in rows:
                pos=(row['chunk_x'],row['chunk_z'])
                low,high,floors,before,after=masks[key][pos]
                details=[];columns=collections.Counter();heights=collections.Counter();states=collections.Counter()
                try:
                    actual=regions[key].chunk(*pos)
                    volume=observer.Volume({pos:actual})
                    full=actual.get('Status')=='minecraft:full'
                except (Exception,SystemExit) as error:
                    full=False;volume=None;actual={};read_error=repr(error)
                for i,(a,b) in enumerate(zip(before,after)):
                    y=low+(i>>8);floor=floors[i&255]
                    if not a and b and (y<=floor or floor>=128):
                        x,z=pos[0]*16+(i&15),pos[1]*16+((i>>4)&15)
                        state=volume.at(x,y,z) if volume else None
                        states[str(state)]+=1;columns[(x,z,floor)]+=1;heights[y]+=1
                        if len(details)<12:details.append({'pos':[x,y,z],'floor_before_LIGHT':floor,'before_code':a,'after_code':b,'saved_state':state})
                reports.append({'chunk':list(pos),'is_requested_target':pos in expected,'counters':{k:row[k] for k in ('native_water','preserved_native_water','removed_native_water','changed_native_water_state','new_water','below_native_surface_additions')},'saved_FULL':full,'saved_status':actual.get('Status'),'column_ranges':[{'x':x,'z':z,'floor':floor,'new_below_floor':count} for (x,z,floor),count in columns.items()],'height_counts':dict(heights),'state_counts':dict(states),'examples':details})
            report['failed_columns'][key]=reports
        differences=[]
        for coord in report['saved_hash_difference_chunks']:
            cx,cz=map(int,coord.split(','));pos=(cx,cz)
            a,b=regions['trial'].chunk(cx,cz),regions['reverse'].chunk(cx,cz)
            va,vb=observer.Volume({pos:a}),observer.Volume({pos:b})
            count=0;examples=[];types=collections.Counter();height=collections.Counter();fluidticks={}
            for y in range(-511,129):
                for z in range(16):
                    for x in range(16):
                        point=(cx*16+x,y,cz*16+z);sa,sb=va.at(*point),vb.at(*point)
                        if saved.water_code(sa)!=saved.water_code(sb):
                            count+=1;types[str(sa)+' -> '+str(sb)]+=1;height[y]+=1
                            if len(examples)<12:
                                ma,mb=review.cell(masks['trial'],point),review.cell(masks['reverse'],point)
                                examples.append({'pos':point,'saved_forward':sa,'saved_reverse':sb,'before_after_floor_forward':ma,'before_after_floor_reverse':mb})
            for label,doc in (('trial',a),('reverse',b)):
                fluidticks[label]={'status':doc.get('Status'),'inhabited_time':doc.get('InhabitedTime'),'last_update':doc.get('LastUpdate'),'fluid_tick_count':len(doc.get('fluid_ticks',[])),'fluid_ticks':doc.get('fluid_ticks',[])[:12]}
            differences.append({'chunk':pos,'different_fluid_cells':count,'state_transitions':dict(types),'heights':dict(height),'examples':examples,'saved_time_and_ticks':fluidticks})
        report['persisted_differences']=differences
        report['remote_block_entity_inventory']={}
        for label in ('trial','reverse'):
            entities=[]
            for cx,cz in plan['remote_chunks']:
                for entity in regions[label].chunk(cx,cz).get('block_entities',[]):
                    if entity.get('id') in ('minecraft:mob_spawner','minecraft:spawner','minecraft:trial_spawner','minecraft:vault'):
                        entities.append(entity)
            report['remote_block_entity_inventory'][label]=entities
    return report


def main():
    root=Path(sys.argv[1]).resolve();out=Path(sys.argv[2]).resolve();out.mkdir(parents=True,exist_ok=True)
    data=inspect(root)
    (out/'details.json').write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n')
    print('NL_R395_DETAILS\n'+json.dumps(data,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
