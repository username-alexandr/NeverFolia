#!/usr/bin/env python3
"""Review captured R395 evidence only: no server, world or pack modifications."""
from __future__ import annotations
import argparse
import collections
import gzip
import hashlib
import json
from pathlib import Path
import struct


def need(ok, message):
    if not ok:
        raise ValueError(message)


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read_masks(folder, run_id):
    result = {}
    for path in folder.glob('*.json'):
        row = json.loads(path.read_text())
        need(row['run_id'] == run_id and row['audit_revision'] == 'R395', 'Stale evidence')
        cx, cz = row['chunk_x'], row['chunk_z']
        need(path.stem == f'{cx}_{cz}', 'Wrong mask identity')
        need(row['mask_file'] == path.stem + '.water.gz', 'Invalid mask path')
        mask = folder / row['mask_file']
        need(digest(mask) == row['mask_sha256'], 'Mask SHA256 mismatch')
        raw = gzip.decompress(mask.read_bytes())
        magic, low, high = struct.unpack_from('>iii', raw)
        floors = struct.unpack_from('>256i', raw, 12)
        length = struct.unpack_from('>i', raw, 1036)[0]
        need(magic == 0x57415431 and (low, high) == (-511, 128), 'Invalid mask dimensions')
        need(length == (high-low+1)*256 and len(raw) == 1040+2*length, 'Invalid mask length')
        before, after = raw[1040:1040+length], raw[1040+length:]
        need(hashlib.sha256(before).hexdigest() == row['before_water_sha256'], 'Before hash differs')
        need(hashlib.sha256(after).hexdigest() == row['after_water_sha256'], 'After hash differs')
        need((cx,cz) not in result, 'Duplicate chunk mask')
        result[cx,cz] = (low, high, floors, before, after)
    return result


def cell(masks, pos):
    x,y,z = pos
    row = masks.get((x//16,z//16))
    if row is None or y < row[0] or y > row[1]:
        return None
    column = ((z&15)<<4)|(x&15)
    index = ((y-row[0])<<8)|column
    return row[3][index], row[4][index], row[2][column]


def components(positions, axis):
    pending = {(z if axis == 'x' else x, y) for x,y,z in positions}
    out = []
    while pending:
        first = min(pending)
        pending.remove(first)
        stack, points = [first], []
        while stack:
            point = stack.pop()
            points.append(point)
            for other in ((point[0]-1,point[1]),(point[0]+1,point[1]),(point[0],point[1]-1),(point[0],point[1]+1)):
                if other in pending:
                    pending.remove(other)
                    stack.append(other)
        lo = [min(p[i] for p in points) for i in range(2)]
        hi = [max(p[i] for p in points) for i in range(2)]
        width,height = hi[0]-lo[0]+1,hi[1]-lo[1]+1
        out.append({'faces':len(points),'horizontal_extent':[lo[0],hi[0]],'height_extent':[lo[1],hi[1]],
                    'width':width,'height':height,'rectangle_occupancy':len(points)/(width*height)})
    return sorted(out,key=lambda r:r['faces'],reverse=True)


def array(value):
    return value.get('$int_array') if isinstance(value,dict) else value


def compact_structure(row):
    data = row['data']
    children = data.get('Children',[])
    boxes = [array(c.get('BB')) for c in children]
    valid = [b for b in boxes if isinstance(b,list) and len(b)==6]
    bounds = None if not valid else [min(b[i] for b in valid) for i in range(3)]+[max(b[i] for b in valid) for i in range(3,6)]
    templates = collections.Counter()
    def walk(obj):
        if isinstance(obj,dict):
            if isinstance(obj.get('location'),str):templates[obj['location']]+=1
            for v in obj.values():walk(v)
        elif isinstance(obj,list):
            for v in obj:walk(v)
    walk(children)
    cameras={}
    for pos in ((-3217,46,-3398),(-3259,46,-3397)):
        cameras[str(pos)] = sum(all(b[i]<=pos[i]<=b[i+3] for i in range(3)) for b in valid)
    return {'key':row['key'],'start_chunk':row['chunk'],'pieces':len(children),'bounds':bounds,
            'pieces_containing_camera':cameras,'template_counts':dict(templates)}


def review(root):
    plan=json.loads((root/'plan.json').read_text())
    need(len(plan['target_chunks'])==129 and len(plan['remote_chunks'])==81, 'Wrong sample plan')
    result=json.loads((root/'r395-water-result.json').read_text())
    need(result['run_id']==plan['run_id'],'Mismatched run identities')
    sums=json.loads((root/'SHA256SUMS.json').read_text())
    checked=0
    for name,expected in sums.items():
        path=root/name
        need(path.resolve().is_relative_to(root.resolve()), 'Unsafe manifest path')
        need(path.is_file() and digest(path)==expected,'Evidence checksum differs: '+name)
        checked+=1
    inventory=json.loads((root/'remote-saved-inventory.json').read_text())
    report={'run_id':plan['run_id'],'verified_evidence_members':checked,'source_inputs':plan['inputs'],
            'bounded_test_pass':result.get('pass'),'production_accepted':False,'phases':{},
            'scope':'Read-only saved water/air interfaces attributed to PRE_LIGHT/post_LIGHT fluid masks. PRE_LIGHT nonwater is not necessarily air; snapshot provenance alone is not defect classification.'}
    for phase,info in inventory['phases'].items():
        if not info.get('read'):
            report['phases'][phase]=info
            continue
        folder='r38-reverse-audit' if phase=='r38-reverse-water' else 'r38-water-audit'
        masks=read_masks(root/'live'/folder,plan['run_id'])
        boundaries=[]
        total=collections.Counter()
        for boundary in info['boundaries']:
            counts=collections.Counter()
            samples=[]
            axis=boundary['axis']
            for pos in boundary['positions']:
                other=(pos[0]+(axis=='x'),pos[1],pos[2]+(axis=='z'))
                a,b=cell(masks,pos),cell(masks,other)
                if a is None or b is None:
                    counts['no_stage_evidence']+=1
                    continue
                if bool(a[1])==bool(b[1]):
                    label='water_asymmetry_appeared_after_light'
                elif bool(a[0])==bool(b[0]):
                    label='water_asymmetry_created_during_light'
                elif (bool(a[0]),bool(b[0]))==(bool(a[1]),bool(b[1])):
                    label='water_asymmetry_already_before_light'
                else:
                    label='water_asymmetry_reversed_during_light'
                counts[label]+=1
                if len(samples)<4:
                    samples.append({'position':pos,'other':list(other),'before':[a[0],b[0]],'after':[a[1],b[1]],'floors':[a[2],b[2]],'stage':label})
            total.update(counts)
            boundaries.append({k:v for k,v in boundary.items() if k!='positions'}|{'attribution':dict(counts),
                               'components':components(boundary['positions'],axis)[:5],'examples':samples})
        spawners=[{k:v for k,v in row.items() if k not in ('Items','items')} for row in info['spawners_and_vaults']]
        report['phases'][phase]={'read':True,'chunks':info['chunks'],'water_air_faces':info['water_air_faces'],
            'stage_attribution':dict(total),'largest_boundaries':boundaries[:12],
            'structures':[compact_structure(row) for row in info['structure_starts']],
            'spawners_and_vaults':spawners,'block_entity_counts':info['block_entity_counts'],
            'camera_samples':info['camera_samples_diagnostic_only']}
    live=json.loads((root/'live/r38-live-qa.json').read_text())
    report['restart_same_water']=live.get('restart_same_water')
    report['generation_order']=live.get('generation_order')
    report['live_phase_results']={k:{a:b for a,b in v.items() if a in ('pass','error','normal_stop','exit_code','seams','targeted_console_errors')} for k,v in live.get('phases',{}).items()}
    report['water_audits']={key:result.get(key) for key in ('r38-water-audit','r38-reverse-audit')}
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    report=review(args.evidence.resolve())
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps(report,indent=2,ensure_ascii=False),flush=True)


if __name__=='__main__':
    main()
