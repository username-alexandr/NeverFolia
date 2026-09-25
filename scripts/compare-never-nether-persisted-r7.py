#!/usr/bin/env python3
"""Exact semantic snapshots of selected FULL chunks in STOPPED test-world copies.

Palette storage order is ignored, but no block/fluid state is removed or changed.
This does not assert identical elapsed ticks, entity simulation or the whole world.
"""
from __future__ import annotations
import argparse
from array import array
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
def module(name,file):
    spec=importlib.util.spec_from_file_location(name,ROOT/'scripts'/file)
    obj=importlib.util.module_from_spec(spec);spec.loader.exec_module(obj);return obj
D=module('r7_decode','diff-never-nether-chunks.py')
A=module('r7_structure_audit','audit-never-nether-worldgen-r7.py')


def semantic_container(container,entries,min_bits):
    values,_=D.decode_paletted_container(container,entry_count=entries,min_bits=min_bits)
    identities=sorted(set(values));lookup={v:i for i,v in enumerate(identities)}
    indices=array('H',(lookup[v] for v in values))
    if sys.byteorder!='little':indices.byteswap()
    return hashlib.sha256(A.canonical(identities)+b'\0'+indices.tobytes()).hexdigest()


def chunk_components(root,coord):
    if (root.get('xPos'),root.get('zPos'))!=coord or root.get('Status') not in ('full','minecraft:full'):
        raise ValueError('Expected exact FULL chunk at '+str(coord))
    sections=root.get('sections');seen=set();blocks={};biomes={}
    if not isinstance(sections,list):raise ValueError('Missing sections')
    for section in sections:
        if not isinstance(section,dict) or type(section.get('Y')) is not int:raise ValueError('Invalid section')
        y=section['Y']
        if y in seen:raise ValueError('Duplicate section')
        seen.add(y)
        if 'block_states' in section:blocks[y]=semantic_container(section['block_states'],4096,4)
        if 'biomes' in section:biomes[y]=semantic_container(section['biomes'],64,1)
    # Selected Nether volume: 64 sections, body and roof. A missing section is
    # not silently interpreted as all air; identical coverage is compared too.
    if not blocks or not biomes:raise ValueError('No decoded blocks or biomes')
    starts=root.get('structures',{}).get('starts',{})
    starts={sid:A.layout(start) for sid,start in starts.items()}
    return {'blocks':A.digest(blocks),'biomes':A.digest(biomes),'structures':A.digest(starts),
        'heightmaps':A.digest(root.get('Heightmaps',{})),
        'block_entities':A.digest(sorted(root.get('block_entities',[]),key=lambda v:(v.get('x',0),v.get('y',0),v.get('z',0)))),
        'section_block_hashes':blocks,'section_biome_hashes':biomes}


def compare(left,right,coords):
    if not coords or len(coords)!=len(set(coords)):raise ValueError('Empty/duplicate sample')
    records=[];count={key:0 for key in ('blocks','biomes','structures','heightmaps','block_entities')}
    for coord in coords:
        l=chunk_components(D.HASHER.read_chunk_nbt(left,*coord),coord)
        r=chunk_components(D.HASHER.read_chunk_nbt(right,*coord),coord)
        changed=[k for k in count if l[k]!=r[k]]
        for k in changed:count[k]+=1
        records.append({'chunk':list(coord),'changed_components':changed,
            'left':{k:l[k] for k in count},'right':{k:r[k] for k in count},
            'different_block_sections':sorted(y for y in l['section_block_hashes'].keys()|r['section_block_hashes'].keys() if l['section_block_hashes'].get(y)!=r['section_block_hashes'].get(y))})
    return {'schema':1,'comparison':'NN-R7-exact-persisted','chunks':len(coords),
        'block_and_fluid_states_normalized':False,'palette_order_ignored':True,
        'changed_chunk_counts':count,'exact_sample_match':all(n==0 for n in count.values()),
        'records':records,'release_ready':False,
        'scope':'Selected saved FULL chunks only. Dynamic entity simulation and elapsed-tick equivalence are not established.'}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--left',required=True,type=Path);p.add_argument('--right',required=True,type=Path)
    p.add_argument('--plan',required=True,type=Path);p.add_argument('--output',required=True,type=Path)
    a=p.parse_args()
    if a.output.suffix!='.json' or any(a.output.resolve().is_relative_to(x.resolve()) for x in (a.left,a.right)):
        p.error('Output JSON must be outside both region directories')
    coords=[tuple(c) for c in json.loads(a.plan.read_text())['chunks']]
    result=compare(a.left,a.right,coords);a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='records'},indent=2))
    return 0 if result['exact_sample_match'] else 2
if __name__=='__main__':raise SystemExit(main())
