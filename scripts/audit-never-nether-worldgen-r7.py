#!/usr/bin/env python3
"""Read-only acceptance observations from STOPPED disposable QA worlds.

No source/flowing lava normalization. Palette order is storage, not block state.
An overlap is a bounding-box policy finding, not proof of two solid walls colliding.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import importlib.util
import itertools
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = json.loads((ROOT / 'worldgen-spec/never-nether-structures.json').read_text())
EXPECTED = {s['id'] for g in SPEC['placement_groups'].values() for s in g['structures']}
MIN_Y, MAX_Y = -123, 378


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def nbt_plain(value):
    if isinstance(value, dict):
        if len(value) == 1 and next(iter(value)) in ('$int_array', '$long_array', '$byte_array'):
            return nbt_plain(next(iter(value.values())))
        return {k: nbt_plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [nbt_plain(v) for v in value]
    return value


def layout(value):
    return {k: nbt_plain(v) for k, v in value.items() if not k.startswith('observed_')}


def bbox(pieces):
    if not pieces:
        raise ValueError('Empty structure is not an accepted start')
    for p in pieces:
        b = p.get('BB')
        if (not isinstance(b, list) or len(b) != 6 or any(type(n) is not int for n in b)
                or any(b[i] > b[i + 3] for i in range(3))):
            raise ValueError('Malformed piece bounding box')
    return [min(p['BB'][i] for p in pieces) for i in range(3)] + [max(p['BB'][i] for p in pieces) for i in range(3, 6)]


def intersection(a, b):
    lo = [max(a[i], b[i]) for i in range(3)]
    hi = [min(a[i+3], b[i+3]) for i in range(3)]
    return lo + hi if all(lo[i] <= hi[i] for i in range(3)) else None


def quotas(elements):
    used, limits = Counter(), {}
    def visit(e):
        if e.get('element_type') == 'neverfolia:limited_single_pool_element':
            name, cap = e['name'], e['max_count']
            if not isinstance(name, str) or not name or type(cap) is not int or cap < 0:
                raise ValueError('Malformed named quota')
            used[name] += 1
            limits[name] = min(limits.get(name, cap), cap)
        elif e.get('element_type') == 'minecraft:list_pool_element':
            for child in e['elements']:
                visit(child)
    for e in elements:
        visit(e)
    return {k: {'used': used[k], 'limit': limits[k], 'passed': used[k] <= limits[k]} for k in sorted(used)}


def summarize(discovery):
    if discovery.get('status') != 'completed' or discovery.get('mode') != 'discover':
        raise ValueError('Requires a completed discovery probe, not a partial/error result')
    if discovery.get('forced_structure_placement') is not False:
        raise ValueError('Forced placement cannot be called natural generation')
    if type(discovery.get('seed')) is not int:
        raise ValueError('Missing numeric seed')
    found = discovery.get('first_natural_starts')
    if not isinstance(found, dict) or not found:
        raise ValueError('No natural starts observed')
    summaries = {}
    for sid, value in sorted(found.items()):
        if value.get('id') != sid:
            raise ValueError('Structure identifier mismatch')
        if (value.get('ChunkX'), value.get('ChunkZ')) != (value.get('observed_chunk_x'), value.get('observed_chunk_z')):
            raise ValueError('Structure start chunk differs from observed chunk')
        pieces = value['Children']; bounds = bbox(pieces)
        elements = [p.get('pool_element', {}) for p in pieces]
        q = quotas(elements)
        summaries[sid] = {
            'chunk': [value['ChunkX'], value['ChunkZ']], 'bbox': bounds,
            'piece_count': len(pieces), 'piece_types': dict(sorted(Counter(e.get('element_type', 'non_pool') for e in elements).items())),
            'body_bounds_passed': MIN_Y <= bounds[1] <= bounds[4] <= MAX_Y,
            'quotas': q, 'quotas_passed': all(x['passed'] for x in q.values()),
            'layout_sha256': digest(layout(value)),
            'gallery_present': any(e.get('location') == 'nova_structures:donjon/room/donjon_room_3x3x3_1' for e in elements),
        }
    overlaps = []
    for (a, x), (b, y) in itertools.combinations(summaries.items(), 2):
        box = intersection(x['bbox'], y['bbox'])
        if box:
            overlaps.append({'left': a, 'right': b, 'bbox': box, 'classification': 'bbox_policy_overlap_not_solid_collision_proof'})
    return {
        'schema': 1, 'gate': 'nevernether-worldgen-r7', 'seed': discovery['seed'],
        'candidate_requests': len(discovery.get('attempts', [])),
        'expected_count': len(EXPECTED), 'observed_approved_count': len(EXPECTED & summaries.keys()),
        'missing': sorted(EXPECTED - summaries.keys()), 'unexpected_custom': sorted(summaries.keys() - EXPECTED),
        'natural_starts_complete': EXPECTED <= summaries.keys(), 'structures': summaries,
        'bbox_policy_findings': overlaps, 'bbox_policy_passed': not overlaps,
        'source_stage_only': True, 'all_blocks_generated_verified': False,
        'walkability_tested': False, 'release_ready': False,
    }


def load_reader():
    spec = importlib.util.spec_from_file_location('nn_r7_reader', ROOT / 'scripts/hash-never-nether-chunks.py')
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


def verify_saved(report, discovery, region: Path, plan, allow_partial=False):
    """Exact selected Nether directory from a stopped-world copy; never load chunks."""
    if plan.get('seed') != report['seed']:
        raise ValueError('Plan seed mismatch')
    coords = [tuple(p) for p in plan['chunks']]
    if not coords or len(set(coords)) != len(coords):
        raise ValueError('Empty/duplicate FULL coverage plan')
    if any(len(p) != 2 or any(type(n) is not int for n in p) for p in coords):
        raise ValueError('Invalid chunk coordinates')
    reader = load_reader(); status_counts = Counter(); roots = {}
    start_coords = {tuple(v['chunk']) for v in report['structures'].values()}
    for coord in coords:
        chunk = reader.read_chunk_nbt(region, *coord)
        if (chunk.get('xPos'), chunk.get('zPos')) != coord:
            raise ValueError('Saved chunk position mismatch')
        status = chunk.get('Status'); status_counts[status] += 1
        if status not in ('full', 'minecraft:full'):
            raise ValueError(f'Coverage not FULL: {coord}, {status}')
        if coord in start_coords:
            roots[coord] = chunk
    for sid, s in report['structures'].items():
        b = s['bbox']; needed = {(x, z) for x in range(b[0]//16, b[3]//16+1) for z in range(b[2]//16, b[5]//16+1)}
        complete = needed <= set(coords)
        if not complete and not allow_partial:
            raise ValueError(f'Incomplete structure footprint: {sid}')
        s['footprint_complete'] = complete
        s['footprint_requested_chunks'] = len(needed & set(coords))
        root = roots.get(tuple(s['chunk']))
        if root is None:
            raise ValueError(f'Natural start not covered: {sid}')
        saved = root.get('structures', {}).get('starts', {}).get(sid)
        if saved is None or saved.get('id') != sid:
            raise ValueError(f'Natural start absent in saved FULL chunk: {sid}')
        s['saved_layout_sha256'] = digest(layout(saved))
        s['saved_layout_matches_discovery'] = s['saved_layout_sha256'] == s['layout_sha256']
        s['saved_piece_count'] = len(saved['Children'])
        s['footprint_full_chunks'] = len(needed)
    report['source_stage_only'] = False
    report['all_blocks_generated_verified'] = all(s['footprint_complete'] for s in report['structures'].values())
    report['complete_footprint_count'] = sum(s['footprint_complete'] for s in report['structures'].values())
    report['saved_full_chunks'] = len(coords)
    report['saved_status_counts'] = dict(status_counts)
    report['all_saved_layouts_match_discovery'] = all(s['saved_layout_matches_discovery'] for s in report['structures'].values())
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--discovery', required=True, type=Path)
    p.add_argument('--region-dir', type=Path)
    p.add_argument('--plan', type=Path)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--allow-partial-footprints', action='store_true', help='Record incomplete footprints explicitly; never mark them FULL-verified')
    args = p.parse_args()
    if bool(args.region_dir) != bool(args.plan): p.error('--region-dir and --plan must be supplied together')
    if args.output.suffix != '.json': p.error('Output must be a JSON report')
    if args.region_dir and args.output.resolve().is_relative_to(args.region_dir.resolve()): p.error('Output must be outside the audited region')
    discovery = json.loads(args.discovery.read_text())
    report = summarize(discovery)
    if args.region_dir: verify_saved(report, discovery, args.region_dir, json.loads(args.plan.read_text()), args.allow_partial_footprints)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False)+'\n')
    print(f"Natural starts {report['observed_approved_count']}/{report['expected_count']}; FULL verified={report['all_blocks_generated_verified']}; bbox findings={len(report['bbox_policy_findings'])}")
    return 0 if report['natural_starts_complete'] and report['bbox_policy_passed'] and report.get('all_saved_layouts_match_discovery', True) and all(s['body_bounds_passed'] and s['quotas_passed'] for s in report['structures'].values()) else 2

if __name__ == '__main__': raise SystemExit(main())
