#!/usr/bin/env python3
"""Verify detached R11 observation files and compare exact metadata and blocks.

Can compare a full probe with a saved before-restart observation directory. This
is not whole-world/biome/entity acceptance; a separate startup gate is required.
"""
from __future__ import annotations
import argparse
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('r11_nbt',ROOT/'scripts/hash-never-nether-chunks.py')
NBT=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(NBT)

PROFILES = {
    'r11': 'NN-R11-SUBSTRATE-1-REMOTE-R10-PRIORITY',
    'r12-local': 'NN-R12-SUBSTRATE-1-NATURAL-PROPOSALS',
    'r12-remote': 'NN-R12-SUBSTRATE-1-DECORATION-PROPOSALS',
    'r13': 'NN-R13-SUBSTRATE-1-RECONCILED-NATURAL',
}

def profile_id(profile: str) -> str:
    if profile not in PROFILES: raise ValueError('Unknown explicit metadata profile: '+str(profile))
    return PROFILES[profile]

def sha(path:Path)->str:return hashlib.sha256(path.read_bytes()).hexdigest()

def observations(root:Path,phase:str|None=None,profile:str='r11')->dict:
    expected_profile=profile_id(profile)
    report=json.loads((root/'report.json').read_text())
    if report.get('stage')!='completed' or report.get('simulation_frozen_before_probe') is not True:
        raise ValueError('Incomplete/unfrozen observation set')
    if sha(root/'states.json')!=report.get('state_dictionary_sha256'):raise ValueError('State dictionary identity mismatch')
    pairs={tuple(p) for p in report['plan']['chunks']}
    if not pairs or len(pairs)!=len(report['plan']['chunks']):raise ValueError('Invalid chunk plan')
    result={}
    for item in report['observations']:
        p=item['phase'];c=(item['x'],item['z'])
        if phase is not None and p!=phase:continue
        if p not in {'carvers','light','settled'} or c not in pairs or (p,c) in result:raise ValueError('Invalid observation coverage')
        if item.get('capture_protocol')!='immutable-section-copy-r11' or item.get('capture_status_before')!=item['status'] or item.get('capture_status_after')!=item['status'] or item.get('simulation_frozen') is not True:
            raise ValueError('Missing coherent capture evidence')
        if p=='carvers' and item['status']!='minecraft:carvers':raise ValueError('CARVERS stage contaminated')
        if p=='light' and item['status'] not in {'minecraft:light','minecraft:spawn'}:raise ValueError('Initial post-feature stage contaminated')
        if p in {'carvers','light'} and item['class']!='net.minecraft.world.level.chunk.ProtoChunk':raise ValueError('Initial snapshot not ProtoChunk')
        if p=='settled' and item['status'] not in {'minecraft:light','minecraft:spawn','minecraft:full'}:raise ValueError('Settled snapshot too early')
        b=root/f'{p}/{c[0]}_{c[1]}.bin.gz';m=root/f'{p}/{c[0]}_{c[1]}.substrate.nbt'
        if item['file']!=b.relative_to(root).as_posix() or item.get('metadata_file')!=m.relative_to(root).as_posix():raise ValueError('Unexpected path')
        if sha(b)!=item['sha256'] or sha(m)!=item['metadata_sha256'] or b.stat().st_size!=item['bytes'] or m.stat().st_size!=item['metadata_bytes']:raise ValueError('Changed observation bytes')
        with gzip.open(m,'rb') as f:raw=f.read(16*1024*1024+1)
        if len(raw)>16*1024*1024:raise ValueError('Oversized metadata sample')
        metadata=NBT.parse_nbt(raw);sections=metadata.get('Substrate')
        if not isinstance(sections,list) or len(sections)!=64 or item.get('metadata_sections')!=64:raise ValueError('Missing substrate coverage')
        for y,s in enumerate(sections,-8):
            if (s['ChunkX'],s['SectionY'],s['ChunkZ'])!=(c[0],y,c[1]) or s['Seed']!=report['seed'] or s['Schema']!=1 or s['Profile']!=expected_profile:raise ValueError('Metadata world identity mismatch')
        result[p,c]={'block_sha256':sha(b),'metadata_sha256':sha(m),'metadata_bytes':m.stat().st_size}
    phases={key[0] for key in result}
    if not phases or set(result)!={(p,c) for p in phases for c in pairs}:raise ValueError('Incomplete selected-phase coverage')
    return {'report':report,'records':result}

def compare(left:Path,right:Path,phase:str|None=None,profile:str='r11')->dict:
    a=observations(left,phase,profile);b=observations(right,phase,profile)
    if a['report']['seed']!=b['report']['seed'] or a['report']['state_dictionary_sha256']!=b['report']['state_dictionary_sha256'] or set(a['records'])!=set(b['records']):raise ValueError('Observation identity/coverage mismatch')
    differences=[]
    for key in sorted(a['records']):
        x,y=a['records'][key],b['records'][key]
        if x['block_sha256']!=y['block_sha256'] or x['metadata_sha256']!=y['metadata_sha256']:
            differences.append({'phase':key[0],'chunk':list(key[1]),'blocks_equal':x['block_sha256']==y['block_sha256'],'metadata_equal':x['metadata_sha256']==y['metadata_sha256']})
    return {'schema':1,'gate':'exact-block-and-substrate-observations','expected_profile':profile_id(profile),'observations':len(a['records']),'sections':len(a['records'])*64,'differences':differences,'passed':not differences,'release_ready':False,'scope':'Exact checked block and metadata snapshot bytes, not every chunk/entity or proof of identical request history.'}

def main()->int:
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--left-observations',type=Path,required=True);p.add_argument('--right-observations',type=Path,required=True);p.add_argument('--phase',choices=('carvers','light','settled'));p.add_argument('--output',type=Path,required=True);p.add_argument('--profile',choices=tuple(PROFILES),default='r11');a=p.parse_args()
    try:r=compare(a.left_observations,a.right_observations,a.phase,a.profile)
    except (OSError,ValueError,TypeError,KeyError) as e:p.exit(2,str(e)+'\n')
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r));return 0 if r['passed'] else 2
if __name__=='__main__':raise SystemExit(main())
