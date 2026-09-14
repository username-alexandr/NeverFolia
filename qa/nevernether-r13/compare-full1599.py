#!/usr/bin/env python3
"""Independent exact FULL-only comparison, never a replacement CARVERS/LIGHT PASS.

The untouched stage comparator still rejects this protocol. The original 1599
coordinates, runtime identity, frozen simulation and owning-FULL capture are
required. All block names/properties, fluids and air variants remain included.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


B=module('full_original_coverage',ROOT/'qa/nevernether-r13/broad1599.py')
C=module('full_snapshot_comparator',ROOT/'scripts/compare-never-nether-stages-r8.py')
PHASES=('full','settled')


def load(directory:Path)->dict:
    run=json.loads((directory/'run-evidence.json').read_text())
    if (run.get('schema')!=2 or run.get('stage')!='completed' or run.get('process_exit_code')!=0
        or run.get('forced_stop') is not False or run.get('runtime_unchanged') is not True
        or run.get('inputs_unchanged') is not True):
        raise ValueError('Not a successfully supervised, normally stopped run')
    inventory=json.loads((directory/'runtime-inventory.json').read_text())
    encoded=json.dumps(inventory['files'],sort_keys=True,separators=(',',':')).encode()
    if (not inventory['files'] or hashlib.sha256(encoded).hexdigest()!=run.get('runtime_payload_sha256')
        or inventory.get('payload_sha256')!=run['runtime_payload_sha256']
        or inventory.get('manifest_sha256')!=run.get('classpath_manifest_sha256')):
        raise ValueError('Runtime inventory integrity mismatch')
    for key in ('pack_sha256','qa_plugin_sha256','runtime_payload_sha256','classpath_manifest_sha256','java_executable_sha256'):
        h=run.get(key)
        if not isinstance(h,str) or len(h)!=64 or any(c not in '0123456789abcdef' for c in h):
            raise ValueError('Invalid input hash '+key)
    root=directory/'plugins/NN-STAGE-R8-QA'
    report=json.loads((root/'report.json').read_text())
    if report.get('schema')!=1 or report.get('probe')!='NN-FULL-R13' or report.get('stage')!='completed':
        raise ValueError('Wrong or incomplete FULL-only protocol')
    B.validate(report['plan'],report['seed'])
    if report['seed']!=run['seed'] or report.get('exact_r7_coverage_sha256')!=B.PLAN_SHA:
        raise ValueError('Original R7 coverage/seed identity mismatch')
    if report.get('simulation_frozen_before_probe') is not True or report.get('target_FULL_requests')!=B.COUNT*2:
        raise ValueError('Missing freeze or incorrect explicit FULL-request count')
    state_path=root/'states.json'
    if C.digest(state_path)!=report.get('state_dictionary_sha256'):
        raise ValueError('State dictionary checksum mismatch')
    raw=json.loads(state_path.read_text())
    if not raw or len(raw)!=len(set(raw.values())):
        raise ValueError('Invalid state dictionary')
    states={int(k):v for k,v in raw.items()}
    chunks=report['plan']['chunks'];coords=set(map(tuple,chunks));seen={}
    for row in report['observations']:
        phase=row['phase'];coord=(row['x'],row['z']);key=(phase,coord)
        if phase not in PHASES or coord not in coords or key in seen:
            raise ValueError('Unexpected/duplicate FULL-only observation')
        if (row.get('status')!='minecraft:full' or row.get('simulation_frozen') is not True
            or row.get('capture_protocol')!='immutable-section-copy-r11'
            or row.get('capture_status_before')!='minecraft:full'
            or row.get('capture_status_after')!='minecraft:full'):
            raise ValueError('Invalid FULL-only immutable capture')
        name=f'{phase}/{coord[0]}_{coord[1]}.bin.gz'
        path=root/name
        if (row.get('file')!=name or not path.is_file() or C.digest(path)!=row.get('sha256')
            or row.get('bytes')!=path.stat().st_size):
            raise ValueError('Snapshot path/checksum/size mismatch')
        meta=f'{phase}/{coord[0]}_{coord[1]}.substrate.nbt'
        if (row.get('metadata_file')!=meta or row.get('metadata_sections')!=64
            or not (root/meta).is_file() or C.digest(root/meta)!=row.get('metadata_sha256')):
            raise ValueError('Metadata snapshot identity mismatch')
        seen[key]=path
    if set(seen)!={(phase,c) for phase in PHASES for c in coords}:
        raise ValueError('Incomplete FULL-only coverage')
    return dict(root=root,report=report,run=run,states=states,chunks=chunks,files=seen)


def compare(left:Path,right:Path)->dict:
    a=load(left);b=load(right)
    if a['chunks']!=list(reversed(b['chunks'])):raise ValueError('Not exact opposite request orders')
    if a['states']!=b['states']:raise ValueError('Different native block-state dictionaries')
    for key in ('seed','pack_sha256','qa_plugin_sha256','classpath_manifest_sha256','runtime_payload_sha256','java_executable_sha256','jvm_flags'):
        if key not in a['run'] or a['run'][key]!=b['run'].get(key):raise ValueError('Different runtime/input '+key)
    cross={p:C.diff(a,b,p,p) for p in PHASES}
    late={'forward':C.diff(a,a,'full','settled'),'reverse':C.diff(b,b,'full','settled')}
    return dict(schema=1,comparison='NN-FULL-R13-original1599',seed=a['run']['seed'],
        exact_r7_coverage_sha256=B.PLAN_SHA,chunks=B.COUNT,range_y=[-128,895],
        all_block_states_included=True,simulation_frozen=True,cross_order=cross,late_changes=late,
        full_and_settled_equal=all(v['equal'] for v in cross.values()),
        settled_equal=cross['settled']['equal'],late_changes_absent=all(v['equal'] for v in late.values()),
        runtime_provenance={k:a['run'][k] for k in ('pack_sha256','qa_plugin_sha256','runtime_payload_sha256','classpath_manifest_sha256','java_executable_sha256','jvm_flags')},
        carvers_light_stage_gate='NOT_EVALUATED_BY_THIS_PROTOCOL',release_ready=False,
        scope='Independent owning-FULL frozen block comparison on exact original R7 coordinates. Does not turn failed CARVERS/LIGHT captures into successes or test dynamic fluids, entity simulation or walkability. Saved Anvil comparison is separate.')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('left','right','output'):p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args()
    if a.output.suffix!='.json' or any(a.output.resolve().is_relative_to(w.resolve()) for w in (a.left,a.right)):
        p.error('Output JSON must be outside both input worlds')
    try:r=compare(a.left,a.right)
    except (OSError,ValueError,KeyError,TypeError) as e:p.exit(2,f'Invalid FULL-only evidence: {e}\n')
    a.output.write_text(json.dumps(r,indent=2)+'\n')
    print({k:v['different_blocks'] for k,v in r['cross_order'].items()})
    return 0 if r['full_and_settled_equal'] and r['late_changes_absent'] else 2

if __name__=='__main__':raise SystemExit(main())
