#!/usr/bin/env python3
"""Exact R14 FULL-only observations; no earlier-protocol results are reused.

Verifies roof/padding directly in every captured block array, not just the
observer's summary counters. Frozen simulation does not test subsequent fluids.
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

MIN_Y=-128;HEIGHT=656;ROOF=512;CELLS=HEIGHT*256
PROFILE='NN-R14-SUBSTRATE-1-ROOF512'
IDENTITIES=('seed','pack_sha256','qa_plugin_sha256','classpath_manifest_sha256','runtime_payload_sha256','java_executable_sha256','jvm_flags')


def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def snapshot(path,coord):
    with gzip.open(path,'rb') as f:raw=f.read(24+CELLS*4+1)
    if len(raw)!=24+CELLS*4 or struct.unpack('>6i',raw[:24])!=(0x4e4e5238,1,*coord,MIN_Y,HEIGHT):
        raise ValueError('Invalid R14 snapshot bounds/coordinates/length: '+str(path))
    return np.frombuffer(raw,dtype='>u4',offset=24)


def load(directory):
    run=json.loads((directory/'run-evidence.json').read_text())
    if run.get('schema')!=2 or run.get('stage')!='completed' or run.get('process_exit_code')!=0 or run.get('forced_stop') is not False or run.get('runtime_unchanged') is not True or run.get('inputs_unchanged') is not True:
        raise ValueError('Failed, changed or forced run is not acceptable')
    inventory=json.loads((directory/'runtime-inventory.json').read_text())
    blob=json.dumps(inventory['files'],sort_keys=True,separators=(',',':')).encode()
    if not inventory['files'] or hashlib.sha256(blob).hexdigest()!=run.get('runtime_payload_sha256') or inventory.get('payload_sha256')!=run['runtime_payload_sha256'] or inventory.get('manifest_sha256')!=run.get('classpath_manifest_sha256'):
        raise ValueError('Runtime byte inventory mismatch')
    for k in IDENTITIES:
        if k not in run:raise ValueError('Missing run identity '+k)
        if k.endswith('sha256') and (not isinstance(run[k],str) or len(run[k])!=64 or any(c not in '0123456789abcdef' for c in run[k])):raise ValueError('Invalid hash '+k)
    root=directory/'plugins/NN-STAGE-R8-QA';report=json.loads((root/'report.json').read_text())
    if report.get('probe')!='NN-ROOF-R14' or report.get('schema')!=1 or report.get('stage')!='completed' or report.get('seed')!=run['seed'] or report.get('simulation_frozen_before_probe') is not True:
        raise ValueError('Wrong R14 protocol, seed, or simulation state')
    if report.get('boundary_failures')!=[]:raise ValueError('Boundary mutation assertions failed')
    plan=report['plan'];chunks=plan.get('chunks')
    if plan.get('seed')!=run['seed'] or not isinstance(chunks,list) or not 1<=len(chunks)<=2048:raise ValueError('Invalid explicit plan')
    for c in chunks:
        if not isinstance(c,list) or len(c)!=2 or any(type(n) is not int for n in c):raise ValueError('Invalid integer coordinates')
    coords=set(map(tuple,chunks))
    if len(coords)!=len(chunks):raise ValueError('Duplicate plan coordinates')
    coverage=hashlib.sha256(''.join(f'{x},{z}\n' for x,z in sorted(coords)).encode()).hexdigest()
    if report.get('coverage_sha256')!=coverage:raise ValueError('Coordinate-set hash mismatch')
    phases=('settled',) if plan.get('readback') is True else ('full','settled')
    if report.get('target_FULL_requests')!=len(chunks)*len(phases):raise ValueError('Wrong explicit FULL request count')
    if digest(root/'states.json')!=report['state_dictionary_sha256']:raise ValueError('Changed state dictionary')
    raw=json.loads((root/'states.json').read_text());states={int(k):v for k,v in raw.items()}
    if not states or len(states)!=len(set(states.values())) or any(not isinstance(v,str) for v in states.values()):raise ValueError('Invalid state dictionary')
    bedrock=[k for k,v in states.items() if v=='minecraft:bedrock']
    air={k for k,v in states.items() if v in ('minecraft:air','minecraft:cave_air','minecraft:void_air')}
    if len(bedrock)!=1 or not air:raise ValueError('Missing native roof states')
    observations={}
    for row in report['observations']:
        p=row['phase'];c=(row['x'],row['z']);key=(p,c)
        if c not in coords or p not in phases or key in observations:raise ValueError('Unexpected/duplicate observation')
        if row.get('status')!='minecraft:full' or row.get('capture_status_before')!='minecraft:full' or row.get('capture_status_after')!='minecraft:full' or row.get('capture_protocol')!='immutable-section-copy-r11' or row.get('simulation_frozen') is not True:
            raise ValueError('Invalid frozen FULL capture')
        name=f'{p}/{c[0]}_{c[1]}.bin.gz';path=root/name
        if row.get('file')!=name or digest(path)!=row.get('sha256') or path.stat().st_size!=row.get('bytes'):raise ValueError('Bad block snapshot')
        meta=f'{p}/{c[0]}_{c[1]}.substrate.nbt';m=root/meta
        if row.get('metadata_file')!=meta or row.get('metadata_sections')!=41 or digest(m)!=row.get('metadata_sha256') or m.stat().st_size!=row.get('metadata_bytes'):raise ValueError('Bad 41-section metadata snapshot')
        data=snapshot(path,c)
        if any(int(n) not in states for n in np.unique(data)):raise ValueError('Unregistered block state')
        if np.any(data[(ROOF-MIN_Y)*256:(ROOF-MIN_Y+1)*256]!=bedrock[0]):raise ValueError('Hole or non-bedrock at Y512 '+str(c))
        if any(int(v) not in air for v in np.unique(data[(ROOF-MIN_Y+1)*256:])):raise ValueError('Block present above Y512 '+str(c))
        if row.get('roof_non_bedrock')!=0 or row.get('padding_non_air')!=0:raise ValueError('Observer detected a ceiling violation')
        observations[key]=row
    if set(observations)!={(p,c) for p in phases for c in coords}:raise ValueError('Incomplete R14 observations')
    return dict(root=root,run=run,report=report,states=states,chunks=chunks,phases=phases,observations=observations,coverage=coverage)


def diff(a,b,left_phase,right_phase):
    pairs=Counter();bad=[];samples=[];different=0;metabad=[]
    for c in sorted(map(tuple,a['chunks'])):
        l=a['observations'][left_phase,c];r=b['observations'][right_phase,c]
        x=snapshot(a['root']/l['file'],c);y=snapshot(b['root']/r['file'],c)
        indices=np.flatnonzero(x!=y);n=len(indices);different+=n
        if n:
            bad.append({'chunk':list(c),'different_blocks':n})
            values,counts=np.unique(np.stack((x[indices],y[indices]),axis=1),axis=0,return_counts=True)
            for (v,w),k in zip(values,counts):pairs[a['states'][int(v)],b['states'][int(w)]]+=int(k)
            for i in indices[:max(0,30-len(samples))]:samples.append({'position':[16*c[0]+int(i)%16,MIN_Y+int(i)//256,16*c[1]+int(i)//16%16],'left':a['states'][int(x[i])],'right':b['states'][int(y[i])]})
        if (a['root']/l['metadata_file']).read_bytes()!=(b['root']/r['metadata_file']).read_bytes():metabad.append(list(c))
    return dict(left_phase=left_phase,right_phase=right_phase,compared_chunks=len(a['chunks']),compared_blocks=len(a['chunks'])*CELLS,
        different_blocks=different,different_chunks=len(bad),equal=different==0,mismatches=bad,samples=samples,
        state_pairs=[dict(left=l,right=r,count=c) for (l,r),c in pairs.most_common()],
        metadata_different_chunks=len(metabad),metadata_different_coordinates=metabad,
        metadata_note='Byte comparison of verified compressed snapshots; semantic profile validation is separate.')


def compare(left,right,relation='reverse'):
    a=load(left);b=load(right)
    if a['report']['plan'].get('test_mutations') or b['report']['plan'].get('test_mutations'):raise ValueError('Mutation QA worlds cannot pass a generation order gate')
    if a['chunks']!=(list(reversed(b['chunks'])) if relation=='reverse' else b['chunks']):raise ValueError('Wrong requested order')
    if a['states']!=b['states']:raise ValueError('Different native block states')
    for k in IDENTITIES:
        if a['run'][k]!=b['run'][k]:raise ValueError('Different runtime/input '+k)
    phases=set(a['phases'])&set(b['phases'])
    if not phases:raise ValueError('No common observations')
    cross={p:diff(a,b,p,p) for p in sorted(phases)}
    late={k:diff(d,d,'full','settled') for k,d in [('left',a),('right',b)] if 'full' in d['phases']}
    return dict(schema=1,comparison='NN-ROOF512-R14',profile=PROFILE,seed=a['run']['seed'],chunks=len(a['chunks']),coverage_sha256=a['coverage'],
        range_y=[MIN_Y,MIN_Y+HEIGHT-1],bedrock_roof_y=ROOF,all_block_states_included=True,roof_and_padding_pass=True,
        simulation_frozen=True,relation=relation,cross_order=cross,late_changes=late,
        block_equality=all(v['equal'] for v in cross.values()) and all(v['equal'] for v in late.values()),
        metadata_byte_equality=all(v['metadata_different_chunks']==0 for v in cross.values()) and all(v['metadata_different_chunks']==0 for v in late.values()),
        runtime_provenance={k:a['run'][k] for k in IDENTITIES},release_ready=False,
        scope='Explicit R14 frozen FULL-only coverage, exact blocks and compressed metadata. Not all game mechanics, dynamic fluids, client placement packets or complete dungeon traversal.')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('left','right','output'):p.add_argument('--'+k,type=Path,required=True)
    p.add_argument('--relation',choices=('reverse','same'),default='reverse');a=p.parse_args()
    if a.output.suffix!='.json' or any(a.output.resolve().is_relative_to(w.resolve()) for w in (a.left,a.right)):p.error('Write a JSON outside both worlds')
    try:report=compare(a.left,a.right,a.relation)
    except (OSError,ValueError,KeyError,TypeError) as e:p.exit(2,'R14 comparison invalid: '+str(e)+'\n')
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,indent=2)+'\n')
    print({k:v['different_blocks'] for k,v in report['cross_order'].items()})
    return 0 if report['block_equality'] and report['metadata_byte_equality'] else 2
if __name__=='__main__':raise SystemExit(main())
