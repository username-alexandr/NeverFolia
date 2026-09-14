#!/usr/bin/env python3
"""Exact CARVERS/LIGHT and settled snapshots with explicit tick-isolation evidence.

This diagnostic does not replace persisted full-world, biome, block-entity or
chunk-order acceptance. Every block name/property, fluid and air variant is kept.
"""
from __future__ import annotations
import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import struct
import numpy as np

PHASES = ('carvers','light','settled')
BOUNDS = (-128,1024)
CELLS = 256 * BOUNDS[1]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_snapshot(path: Path, coordinate: tuple[int,int]) -> np.ndarray:
    # Limit decompression, reject truncation/trailing data and wrong coordinates.
    with gzip.open(path,'rb') as f:
        raw=f.read(CELLS*4+25)
    if len(raw)!=CELLS*4+24: raise ValueError(f'Invalid snapshot length: {path}')
    header=struct.unpack('>6i',raw[:24])
    if header!=(0x4e4e5238,1,*coordinate,*BOUNDS): raise ValueError(f'Invalid snapshot header: {path}')
    return np.frombuffer(raw,dtype='>u4',offset=24)


def load(directory: Path, *, max_chunks: int = 512) -> dict:
    run=json.loads((directory/'run-evidence.json').read_text())
    if run.get('schema')!=2 or run.get('runtime_unchanged') is not True or run.get('inputs_unchanged') is not True or run.get('stage')!='completed' or run.get('process_exit_code')!=0 or run.get('forced_stop') is not False:
        raise ValueError('A failed/timed-out run is not passing stage evidence')
    inventory=json.loads((directory/'runtime-inventory.json').read_text())
    encoded=json.dumps(inventory['files'],sort_keys=True,separators=(',',':')).encode()
    if not inventory['files'] or hashlib.sha256(encoded).hexdigest()!=run.get('runtime_payload_sha256') or inventory.get('payload_sha256')!=run['runtime_payload_sha256'] or inventory.get('manifest_sha256')!=run.get('classpath_manifest_sha256'):
        raise ValueError('Runtime inventory mismatch')
    for key in ('pack_sha256','qa_plugin_sha256','runtime_payload_sha256','classpath_manifest_sha256','java_executable_sha256'):
        value=run.get(key)
        if not isinstance(value,str) or len(value)!=64 or any(c not in '0123456789abcdef' for c in value):raise ValueError('Invalid input identity: '+key)
    root=directory/'plugins/NN-STAGE-R8-QA'
    report=json.loads((root/'report.json').read_text())
    if report.get('stage')!='completed' or report.get('probe')!='NN-STAGE-R8' or report.get('schema')!=1:
        raise ValueError('Incomplete/unknown stage report')
    if report.get('simulation_frozen_before_probe') is not True or report.get('target_FULL_requests')!=0:
        raise ValueError('Missing tick isolation or unexpected FULL requests')
    if digest(root/'states.json')!=report.get('state_dictionary_sha256'):
        raise ValueError('State dictionary checksum mismatch')
    states=json.loads((root/'states.json').read_text())
    if not states or len(states)!=len(set(states.values())): raise ValueError('Invalid state dictionary')
    states={int(i):s for i,s in states.items()}
    chunks=report['plan']['chunks']
    if not chunks or len(chunks)>max_chunks or len(chunks)!=len({tuple(c) for c in chunks}):
        raise ValueError('Empty, duplicate or unbounded chunk plan')
    for c in chunks:
        if len(c)!=2 or any(type(n)!=int for n in c):raise ValueError('Invalid chunk coordinate')
    if report['seed']!=report['plan']['seed'] or run['seed']!=report['seed']:raise ValueError('Seed mismatch')
    seen={}
    for observation in report['observations']:
        phase=observation['phase'];c=(observation['x'],observation['z']);key=(phase,c)
        if phase not in PHASES or list(c) not in chunks or key in seen:raise ValueError('Unexpected/duplicate observation')
        if observation.get('simulation_frozen') is not True:raise ValueError('Unfrozen simulation')
        state=observation['status']
        if phase=='carvers' and state!='minecraft:carvers':raise ValueError('CARVERS snapshot contaminated')
        if phase=='light' and state not in ('minecraft:light','minecraft:spawn'):raise ValueError('First LIGHT snapshot contaminated')
        if phase=='settled' and state not in ('minecraft:light','minecraft:spawn','minecraft:full'):raise ValueError('Settled stage too early')
        if phase in ('carvers','light') and observation.get('class')!='net.minecraft.world.level.chunk.ProtoChunk':raise ValueError('First snapshot is not a protochunk')
        expected=f'{phase}/{c[0]}_{c[1]}.bin.gz'
        if observation['file']!=expected:raise ValueError('Unexpected snapshot path')
        path=root/expected
        if not path.is_file() or digest(path)!=observation['sha256']:raise ValueError('Snapshot checksum mismatch')
        if type(observation.get('bytes')) is not int or observation['bytes']!=path.stat().st_size:raise ValueError('Snapshot size mismatch')
        seen[key]=path
    if set(seen)!={(phase,tuple(c)) for phase in PHASES for c in chunks}:raise ValueError('Incomplete stage coverage')
    return dict(root=root,report=report,run=run,states=states,chunks=chunks,files=seen)


def diff(a: dict,b: dict,phase_a: str,phase_b: str) -> dict:
    counts=Counter();bad=[];samples=[];total=0
    for c in sorted(map(tuple,a['chunks'])):
        x=read_snapshot(a['files'][phase_a,c],c);y=read_snapshot(b['files'][phase_b,c],c)
        if any(int(v) not in a['states'] for v in np.unique(x)) or any(int(v) not in b['states'] for v in np.unique(y)):
            raise ValueError('Unregistered block-state index')
        mismatch=np.flatnonzero(x!=y)
        if not len(mismatch):continue
        total+=len(mismatch);bad.append({'chunk':list(c),'different_blocks':len(mismatch)})
        pairs,n=np.unique(np.stack((x[mismatch],y[mismatch]),axis=1),axis=0,return_counts=True)
        for (l,r),count in zip(pairs,n):counts[a['states'][int(l)],b['states'][int(r)]]+=int(count)
        for i in mismatch[:max(0,20-len(samples))]:
            samples.append({'position':[c[0]*16+int(i)%16,BOUNDS[0]+int(i)//256,c[1]*16+(int(i)//16)%16],
                            'left':a['states'][int(x[i])],'right':b['states'][int(y[i])]})
    return {'left_phase':phase_a,'right_phase':phase_b,'compared_chunks':len(a['chunks']),
            'compared_blocks':len(a['chunks'])*CELLS,'different_chunks':len(bad),'different_blocks':total,
            'equal':total==0,'mismatches':bad,'state_pairs':[{'left':l,'right':r,'count':n} for (l,r),n in counts.most_common()],
            'samples':samples}


def compare(left: Path,right: Path,relation: str='reverse', *, max_chunks: int = 512) -> dict:
    a=load(left,max_chunks=max_chunks);b=load(right,max_chunks=max_chunks)
    if relation not in ('reverse','same'):raise ValueError('Unknown request-order relation')
    if a['chunks']!=(list(reversed(b['chunks'])) if relation=='reverse' else b['chunks']):
        raise ValueError('Request order does not match declared relation')
    if a['states']!=b['states']:raise ValueError('Exact native state dictionaries differ')
    for key in ('seed','pack_sha256','qa_plugin_sha256','classpath_manifest_sha256','runtime_payload_sha256','java_executable_sha256','jvm_flags'):
        if a['run'].get(key)!=b['run'].get(key) or key not in a['run']:raise ValueError('Runtime/input mismatch: '+key)
    result={'schema':1,'audit':'NN-STAGE-R8','seed':a['report']['seed'],'request_order_relation':relation,
            'range_y':[-128,895],'all_states_included':True,'simulation_frozen':True,'release_ready':False,
            'cross_order':{p:diff(a,b,p,p) for p in PHASES},
            'late_changes':{'left':diff(a,a,'light','settled'),'right':diff(b,b,'light','settled')},
            'runtime_provenance':{k:a['run'][k] for k in ('pack_sha256','qa_plugin_sha256','classpath_manifest_sha256','runtime_payload_sha256','java_executable_sha256','jvm_flags')},
            'scope':'Bounded frozen-simulation CARVERS and post-FEATURES snapshots. Not a replacement for the full persisted-world gate. No fluid/air/plant normalization.'}
    result['generation_stage_equal']=all(v['equal'] for v in result['cross_order'].values())
    return result


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--left',type=Path,required=True);p.add_argument('--right',type=Path,required=True)
    p.add_argument('--relation',choices=('same','reverse'),default='reverse');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    try:result=compare(a.left,a.right,a.relation)
    except (OSError,ValueError,KeyError,TypeError) as e:p.exit(2,f'Stage comparison invalid: {e}\n')
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2)+'\n')
    print({p:v['different_blocks'] for p,v in result['cross_order'].items()})
    return 0 if result['generation_stage_equal'] else 2
if __name__=='__main__':raise SystemExit(main())
