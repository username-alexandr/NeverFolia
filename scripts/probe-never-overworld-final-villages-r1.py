#!/usr/bin/env python3
"""Finalize observational village geometry ONLY inside saved FULL coverage.

The first stopped snapshot plans the load, not an immutable list of final pieces.
Keep both snapshots. Final geometry outside the verified area is an error, never
an excuse to assume unseen chunks are empty or dry. No world files are written.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import re

VILLAGES = {'minecraft:village_plains', 'minecraft:village_desert'}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def coverage(boxes):
    require(isinstance(boxes, list) and 1 <= len(boxes) <= 1000, 'invalid saved piece list')
    for box in boxes:
        require(isinstance(box, list) and len(box) == 6 and all(type(v) is int for v in box)
                and all(box[i] <= box[i+3] for i in range(3))
                and -512 <= box[1] <= box[4] <= 511, 'invalid saved piece box')
    x0, z0 = min(b[0] for b in boxes)-1, min(b[2] for b in boxes)-1
    x1, z1 = max(b[3] for b in boxes)+1, max(b[5] for b in boxes)+1
    require(x1-x0 <= 256 and z1-z0 <= 256, 'unbounded village coverage')
    result = {(x, z) for x in range(x0//16, x1//16+1) for z in range(z0//16, z1//16+1)}
    require(len(result) <= 324, 'too many village chunks')
    return result


def points(values):
    require(isinstance(values, list) and 1 <= len(values) <= 324
            and all(isinstance(p, list) and len(p) == 2 and all(type(v) is int for v in p)
                    for p in values), 'invalid verified chunk list')
    result = {tuple(p) for p in values}
    require(len(result) == len(values), 'duplicate verified chunk')
    return result


def full_root(root, point):
    require(isinstance(root, dict) and root.get('Status') == 'minecraft:full', 'saved chunk not FULL: '+str(point))
    require(type(root.get('xPos')) is int and type(root.get('zPos')) is int
            and (root['xPos'], root['zPos']) == point, 'saved coordinate mismatch')


def final_boxes(root, target):
    start = root.get('structures', {}).get('starts', {}).get(target)
    require(isinstance(start, dict) and start.get('id') == target, 'saved village start missing: '+target)
    children = start.get('Children')
    require(isinstance(children, list) and bool(children), 'saved village pieces missing')
    boxes = []
    for child in children:
        require(isinstance(child, dict), 'invalid saved child')
        value = child.get('BB')
        boxes.append(value.get('$int_array') if isinstance(value, dict) else value)
    coverage(boxes)
    return boxes


def geometry_change(before, after):
    a = Counter(map(tuple, before)); b = Counter(map(tuple, after))
    axz = Counter((v[0], v[2], v[3], v[5]) for v in before)
    bxz = Counter((v[0], v[2], v[3], v[5]) for v in after)
    return {'ordered_boxes_equal': before == after, 'box_multisets_equal': a == b,
            'xz_multisets_equal': axz == bxz,
            'initial_piece_count': len(before), 'final_piece_count': len(after),
            'removed_box_instances': [list(v) for v in (a-b).elements()],
            'added_box_instances': [list(v) for v in (b-a).elements()]}


def reconcile(plan, read_chunk, diagnostic):
    """Return a new evidence plan; do not mutate caller state, regions, or locks."""
    diagnostic.update({'schema': 1, 'source_sha': plan.get('source_sha'), 'villages': [],
                       'final_saved_geometry_covered': False,
                       'policy': 'final stopped snapshot; no reads outside verified FULL coverage',
                       'visual_shape_accepted': False})
    require(type(plan.get('schema')) is int and plan['schema'] == 2, 'unexpected plan schema')
    require(plan.get('normal_stop') is True and type(plan.get('process_exit_code')) is int
            and plan['process_exit_code'] == 0, 'world not stopped normally')
    phases = plan.get('phases', [])
    require(len(phases) == 2 and [p.get('name') for p in phases] ==
            ['locate-and-initial-chunks', 'complete-village-footprints']
            and all(p.get('normal_stop') is True and type(p.get('process_exit_code')) is int
                    and p['process_exit_code'] == 0 for p in phases)
            and phases[0].get('saved_initial_full_verified') is True
            and phases[1].get('saved_all_full_verified') is True, 'unverified stopped phases')
    villages = [a for a in plan.get('areas', []) if a.get('kind') == 'village']
    require(len(villages) == 2 and {a.get('target') for a in villages} == VILLAGES, 'village targets incomplete')
    result = deepcopy(plan)
    for area in result['areas']:
        if area['kind'] != 'village':
            continue
        target = area['target']; initial = area['piece_boxes']; verified = points(area['chunks'])
        require(verified == coverage(initial), 'planning coverage differs from initial boxes')
        require(isinstance(area.get('start_chunk'), list) and len(area['start_chunk']) == 2
                and all(type(v) is int for v in area['start_chunk']), 'invalid start chunk')
        start = tuple(area['start_chunk']); require(start in verified, 'start outside verified area')
        root = read_chunk(*start); full_root(root, start)
        final = final_boxes(root, target); needed = coverage(final)
        item = {'target': target, 'start_chunk': list(start),
                'initial_piece_boxes': deepcopy(initial), 'final_piece_boxes': deepcopy(final),
                'verified_chunks': [list(p) for p in sorted(verified)],
                'final_required_chunks': [list(p) for p in sorted(needed)],
                'unverified_required_chunks': [list(p) for p in sorted(needed-verified)],
                **geometry_change(initial, final)}
        diagnostic['villages'].append(item)
        require(not needed-verified, 'final village expands beyond verified FULL coverage: '+target)
        require(start in needed, 'final bounds exclude their saved start chunk')
        for point in sorted(verified):
            saved = root if point == start else read_chunk(*point)
            full_root(saved, point)
        area['planning_piece_boxes'] = deepcopy(initial)
        area['planning_chunks'] = deepcopy(area['chunks'])
        area['piece_boxes'] = deepcopy(final)
        area['chunks'] = [list(p) for p in sorted(needed)]
        area['geometry_snapshot'] = 'final stopped world; original planning boxes retained'
    diagnostic['final_saved_geometry_covered'] = True
    result['final_village_geometry_verified'] = True
    return result


def write_json(path, value, mode='w'):
    with path.open(mode, encoding='utf-8') as out:
        json.dump(value, out, ensure_ascii=False, indent=2); out.write('\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--jar', type=Path, required=True)
    parser.add_argument('--pack', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source-sha', required=True)
    args = parser.parse_args()
    require(re.fullmatch('[0-9a-f]{40}', args.source_sha) is not None, 'full SHA required')
    root = Path(__file__).resolve().parents[1]; out = args.output.resolve(); out.mkdir(parents=True, exist_ok=True)
    for name in ('tree-village-plan.json', 'tree-village-initial-plan.json', 'tree-village-geometry.json',
                 'tree-village-natural.json'):
        require(not (out/name).exists(), 'do not overwrite existing observation: '+name)
    spec = importlib.util.spec_from_file_location('tree_observer', root/'scripts/probe-never-overworld-trees-villages-r1.py')
    observer = importlib.util.module_from_spec(spec); spec.loader.exec_module(observer)
    nbt = observer.load_nbt(root)
    plan, region = observer.generate(root, args.jar.resolve(), args.pack.resolve(), out, nbt, args.source_sha)
    write_json(out/'tree-village-initial-plan.json', plan, 'x')
    diagnostic = {}
    try:
        final = reconcile(plan, lambda x,z: nbt.read_chunk_nbt(region,x,z), diagnostic)
    except Exception as error:
        diagnostic['error'] = f'{type(error).__name__}: {error}'
        raise
    finally:
        write_json(out/'tree-village-geometry.json', diagnostic, 'x')
    write_json(out/'tree-village-plan.json', final)
    report = observer.audit(final, region, out, nbt)
    report['final_village_geometry_verified'] = True
    report['geometry_evidence'] = 'tree-village-geometry.json'
    report['initial_planning_evidence'] = 'tree-village-initial-plan.json'
    write_json(out/'tree-village-natural.json', report)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
