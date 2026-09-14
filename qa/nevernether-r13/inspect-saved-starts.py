#!/usr/bin/env python3
"""Read-only summary of the pinned original 20 start chunks in stopped QA worlds.

This reads real persisted NBT. It does not construct a fake live-discovery report,
place structures, load game chunks or claim walkability. FULL footprint coverage
is checked separately by the persisted 1599-chunk comparator.
"""
import argparse
from collections import Counter
import importlib.util
import json
from pathlib import Path
import zipfile


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def summarize(source, world, plan_path, pack):
    audit = load('saved_start_audit', source/'scripts/audit-never-nether-worldgen-r7.py')
    broad = load('saved_start_coverage', source/'qa/nevernether-r13/broad1599.py')
    plan = broad.validate(json.loads(plan_path.read_text()), 7270913)
    evidence = json.loads((world/'run-evidence.json').read_text())
    if not (evidence.get('stage') == 'completed' and evidence.get('process_exit_code') == 0
            and evidence.get('forced_stop') is False and evidence.get('runtime_unchanged') is True
            and evidence.get('inputs_unchanged') is True and evidence.get('seed') == plan['seed']):
        raise ValueError('The world must be a normally stopped, accepted disposable probe')
    if broad.RUNNER.sha(pack) != evidence['pack_sha256']:
        raise ValueError('Pack identity mismatch')
    with zipfile.ZipFile(pack) as z:
        manifest = json.loads(z.read('nevernether-structure-integration-manifest.json'))
    approved = {entry['id'] for entry in manifest['approved_structures']}
    if approved != audit.EXPECTED or len(approved) != 20:
        raise ValueError('Unexpected approved structure inventory')
    coverage = set(map(tuple, plan['chunks']))
    reader = audit.load_reader()
    region = world/'world/dimensions/minecraft/the_nether/region'
    found = {}
    for coord in map(tuple, broad.original_plan()['chunks'][:20]):
        root = reader.read_chunk_nbt(region, *coord)
        if (root.get('xPos'), root.get('zPos')) != coord or root.get('Status') != 'minecraft:full':
            raise ValueError('Expected saved FULL start chunk at '+str(coord))
        for sid, raw in root.get('structures', {}).get('starts', {}).items():
            if sid not in approved or raw.get('id') != sid:
                continue
            if sid in found:
                raise ValueError('Duplicate selected approved start '+sid)
            value = audit.nbt_plain(raw)
            if (value.get('ChunkX'), value.get('ChunkZ')) != coord:
                raise ValueError('Saved start coordinates do not match chunk')
            pieces = value.get('Children', [])
            box = audit.bbox(pieces)
            elements = [p.get('pool_element', {}) for p in pieces]
            quota = audit.quotas(elements)
            needed = {(x, z) for x in range(box[0]//16, box[3]//16+1)
                      for z in range(box[2]//16, box[5]//16+1)}
            found[sid] = dict(chunk=list(coord), bbox=box, piece_count=len(pieces),
                layout_sha256=audit.digest(audit.layout(value)),
                body_bounds_passed=audit.MIN_Y <= box[1] <= box[4] <= audit.MAX_Y,
                quotas=quota, quotas_passed=all(q['passed'] for q in quota.values()),
                footprint_in_pinned_plan=needed <= coverage, footprint_chunks=len(needed),
                missing_footprint_chunks=[list(c) for c in sorted(needed-coverage)],
                gallery_present=any(e.get('location') == 'nova_structures:donjon/room/donjon_room_3x3x3_1' for e in elements),
                element_types=dict(Counter(e.get('element_type', 'non_pool') for e in elements)))
    return dict(schema=1, gate='R13-persisted-approved-starts', seed=plan['seed'],
        coverage_sha256=broad.PLAN_SHA, pack_sha256=evidence['pack_sha256'],
        expected_count=len(approved), found_count=len(found), missing=sorted(approved-found.keys()),
        complete=approved == found.keys(), structures=dict(sorted(found.items())),
        all_body_bounds_passed=all(s['body_bounds_passed'] for s in found.values()),
        all_quotas_passed=all(s['quotas_passed'] for s in found.values()),
        all_footprints_in_plan=all(s['footprint_in_pinned_plan'] for s in found.values()),
        walkability_tested=False, release_ready=False,
        scope='Actual saved start NBT at original R7 start coordinates; no forced placement. A piece is not necessarily a room. FULL footprint coverage requires the separate persisted-chunk comparison.')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('source','world','plan','pack','output'):
        p.add_argument('--'+key, type=Path, required=True)
    a=p.parse_args()
    if a.output.resolve().is_relative_to(a.world.resolve()):
        p.error('Write the report outside the input world')
    r=summarize(a.source,a.world,a.plan,a.pack)
    a.output.write_text(json.dumps(r,indent=2)+'\n')
    print({k:v for k,v in r.items() if k!='structures'})
    return 0 if r['complete'] and r['all_body_bounds_passed'] and r['all_quotas_passed'] and r['all_footprints_in_plan'] else 2

if __name__=='__main__':raise SystemExit(main())
