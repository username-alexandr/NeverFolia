#!/usr/bin/env python3
"""Independent read-only Anvil review. Zero mask values are never assumed air."""
from __future__ import annotations
import argparse
import collections
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import zipfile
import review

ROOT=Path(__file__).resolve().parents[2]
AIR={'minecraft:air','minecraft:cave_air','minecraft:void_air'}
PLANTS={'minecraft:seagrass','minecraft:tall_seagrass','minecraft:kelp','minecraft:kelp_plant','minecraft:bubble_column'}


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def water_code(state):
    if state['Name']=='minecraft:water':return 1+int(state.get('Properties',{}).get('level','0'))
    if state.get('Properties',{}).get('waterlogged')=='true' or state['Name'] in PLANTS:return 1
    return 0


def direction_label(before,after,saved):
    pre,post,last=tuple(map(bool,before)),tuple(map(bool,after)),tuple(map(bool,saved))
    review.need(last[0]!=last[1],'Not a saved water/nonwater interface')
    if post!=last:return 'polarity_changed_after_LIGHT'
    if pre==post:return 'same_water_polarity_already_PRE_LIGHT'
    if pre[0]==pre[1]:return 'water_polarity_created_in_LIGHT'
    return 'water_polarity_reversed_in_LIGHT'


class Regions:
    def __init__(self,archive,prefix,nbt):self.archive,self.prefix,self.nbt,self.cache=archive,prefix,nbt,{}
    def chunk(self,cx,cz):
        name=f'{self.prefix}/r.{cx//32}.{cz//32}.mca'
        if name not in self.cache:
            review.need(self.archive.getinfo(name).file_size<=128*1024*1024,'Oversized region evidence')
            self.cache[name]=self.archive.read(name)
        raw=self.cache[name]
        index=(cx&31)+32*(cz&31)
        review.need(len(raw)>=8192,'Missing Anvil header')
        location=int.from_bytes(raw[4*index:4*index+4],'big')
        offset,count=location>>8,location&255
        review.need(offset>=2 and count>0,'Chunk not persisted')
        start=offset*4096
        review.need(start+5<=len(raw),'Truncated chunk header')
        size=int.from_bytes(raw[start:start+4],'big');kind=raw[start+4]
        review.need(size>=1 and size+4<=count*4096 and start+4+size<=len(raw),'Invalid sector bounds')
        payload=raw[start+5:start+4+size]
        if kind&128:payload=self.archive.read(f'{self.prefix}/c.{cx}.{cz}.mcc')
        root=self.nbt.parse_nbt(self.nbt.decompress_chunk(kind&127,payload))
        review.need((root.get('xPos'),root.get('zPos'))==(cx,cz),'Wrong persisted coordinates')
        return root


def signed32(n):return n-(1<<32) if n&(1<<31) else n


def inspect(evidence):
    plan=json.loads((evidence/'plan.json').read_text());live=json.loads((evidence/'live/r38-live-qa.json').read_text())
    report={'scope':'Actual stopped Anvil blocks, exact water hashes, side-aware PRE_LIGHT/post_LIGHT comparison. No remote player activation or all-world acceptance.','run_id':plan['run_id'],'phases':{},'production_accepted':False}
    observer=load('r395_actual_saved_observer',ROOT/'scripts/probe-never-overworld-trees-villages-r1.py')
    nbt=observer.load_nbt(ROOT);remote=set(map(tuple,plan['remote_chunks']))
    original=json.loads((evidence/'remote-saved-inventory.json').read_text())
    with zipfile.ZipFile(evidence/'saved-worlds-evidence.zip') as archive:
        review.need(len(archive.namelist())==len(set(archive.namelist())),'Duplicate world evidence paths')
        for phase,prior in original['phases'].items():
            if not prior.get('read'):
                report['phases'][phase]={'read':False,'reason':prior};continue
            p=live['phases'][phase]
            review.need(p.get('normal_stop') is True and p.get('exit_code')==0,'No confirmed normal stop')
            sub='reverse' if phase=='r38-reverse-water' else 'trial'
            regions=Regions(archive,sub+'/world/dimensions/minecraft/overworld/region',nbt)
            roots={point:regions.chunk(*point) for point in sorted(remote)}
            for point,root in roots.items():
                sections={s['Y']:s for s in root['sections']}
                review.need(root.get('Status')=='minecraft:full' and all(y in sections and 'block_states' in sections[y] for y in range(-32,32)),'Incomplete FULL evidence')
            volume=observer.Volume(roots)
            masks=review.read_masks(evidence/'live'/('r38-reverse-audit' if sub=='reverse' else 'r38-water-audit'),plan['run_id'])
            hashes={}
            for cx,cz in sorted(remote):
                h=hashlib.sha256()
                for y in range(-511,129):
                    h.update(bytes(water_code(volume.at(cx*16+x,y,cz*16+z)) for z in range(16) for x in range(16)))
                hashes[f'{cx},{cz}']=h.hexdigest()
            mismatches=[key for key,value in hashes.items() if p.get('water_hashes',{}).get(key)!=value]
            review.need(not mismatches,'Original saved-hash evidence does not match preserved Anvil')
            stages=collections.Counter();polarity_examples=[];boundaries=[]
            for boundary in prior['boundaries']:
                counts=collections.Counter()
                for pos in boundary['positions']:
                    axis=boundary['axis'];other=(pos[0]+(axis=='x'),pos[1],pos[2]+(axis=='z'))
                    sa,sb=volume.at(*pos),volume.at(*other)
                    ca,cb=water_code(sa),water_code(sb)
                    review.need((ca and sb['Name'] in AIR) or (cb and sa['Name'] in AIR),'Reported interface is not actual saved water/air')
                    a,b=review.cell(masks,pos),review.cell(masks,other)
                    review.need(a is not None and b is not None,'No stage evidence for reported face')
                    label=direction_label((a[0],b[0]),(a[1],b[1]),(ca,cb));counts[label]+=1
                    if len(polarity_examples)<16:
                        polarity_examples.append({'position':pos,'other':list(other),'saved':[sa,sb],'before_codes':[a[0],b[0]],'after_codes':[a[1],b[1]],'floors':[a[2],b[2]],'label':label})
                stages.update(counts)
                boundaries.append({'chunk':boundary['chunk'],'neighbor':boundary['neighbor'],'axis':boundary['axis'],'faces':boundary['water_air_faces'],'stages':dict(counts),'components':review.components(boundary['positions'],boundary['axis'])[:3]})
            origins=set(roots)
            for root in roots.values():
                for values in root.get('structures',{}).get('References',root.get('structures',{}).get('references',{})).values():
                    for value in values.get('$long_array',[]) if isinstance(values,dict) else values:
                        value&=(1<<64)-1;origins.add((signed32(value&0xffffffff),signed32(value>>32)))
            starts=[];unreadable=[]
            for point in sorted(origins):
                try:root=roots.get(point) or regions.chunk(*point)
                except (Exception,SystemExit) as error:
                    unreadable.append({'origin':point,'error':repr(error)});continue
                for key,data in root.get('structures',{}).get('starts',{}).items():
                    if isinstance(data,dict) and data.get('id') not in (None,'INVALID','minecraft:invalid'):
                        starts.append(review.compact_structure({'chunk':list(point),'key':key,'data':data}))
            report['phases'][phase]={'read':True,'actual_chunk_hashes_verified':len(hashes),'water_air_faces':sum(stages.values()),'side_verified_stages':dict(stages),'largest_boundaries':boundaries[:8],'actual_block_examples':polarity_examples,
                'structures_including_readable_reference_origins':starts,'unreadable_reference_origins':unreadable,'spawner_counts':collections.Counter(e.get('id') for root in roots.values() for e in root.get('block_entities',[]) if e.get('id') in ('minecraft:spawner','minecraft:trial_spawner','minecraft:vault'))}
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--evidence',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    r=inspect(a.evidence.resolve());a.output.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2),flush=True)

if __name__=='__main__':main()
