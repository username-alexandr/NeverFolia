#!/usr/bin/env python3
"""Run the existing live harness on 129 chunks; preserve failures and raw evidence.
The test agent changes only the read-only observer. No gameplay JAR is rewritten.
"""
from __future__ import annotations
import argparse
import collections
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import sys
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[2]
CORE = '411f628603ae531216c173fde1dbd8c702effb170889f72e5f2c0f1af81b6a32'
PACK = 'a5fb99cd0b15efc2ec78a1f155c763112f3e3d2669c1519aae69e468de7902be'
NETHER = '5e47f953cadbd5451b04d1682642417c9a40c726cf06e935c02cecdcb5eb2a10'
HARNESS_BLOB = 'd0d209d6817caa8bd5809cdbfcf548ebbfb3ea4a'
LOW, HIGH = -511, 128
REMOTE_CENTER = (-3217 // 16, -3398 // 16)
REMOTE = {(REMOTE_CENTER[0] + dx, REMOTE_CENTER[1] + dz) for dx in range(-4, 5) for dz in range(-4, 5)}
OLD_TARGETS = ((0, 0), (-4, 3), (0, -1), (3, 0), (2, 3), (12, 4))
OLD = {(cx + dx, cz + dz) for cx, cz in OLD_TARGETS for dx in (-1, 0, 1) for dz in (-1, 0, 1)}
CHUNKS = sorted(OLD | REMOTE)
COUNTERS = ('native_water', 'preserved_native_water', 'removed_native_water', 'changed_native_water_state',
            'explicit_dry_mine_changes', 'new_water', 'below_native_surface_additions')


def need(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n')


def mask_data(payload):
    raw = gzip.decompress(payload)
    need(len(raw) >= 1040, 'Truncated water mask')
    magic, low, high = struct.unpack_from('>iii', raw)
    need((magic, low, high) == (0x57415431, LOW, HIGH), 'Unexpected mask format/height')
    floors = struct.unpack_from('>256i', raw, 12)
    size = struct.unpack_from('>i', raw, 1036)[0]
    need(size == (HIGH - LOW + 1) * 256 and len(raw) == 1040 + 2 * size, 'Incomplete/overlong water mask')
    before, after = raw[1040:1040 + size], raw[1040 + size:]
    need(max(before + after) <= 16, 'Invalid encoded fluid state')
    return floors, before, after


def verify_row(folder, path, run_id):
    row = json.loads(path.read_text())
    cx, cz = row['chunk_x'], row['chunk_z']
    need(type(cx) is int and type(cz) is int, 'Invalid chunk coordinates')
    need(path.stem == f'{cx}_{cz}', 'Misnamed audit row')
    need(row.get('audit_revision') == 'R395' and row.get('run_id') == run_id, 'Stale or wrong audit revision')
    need(row.get('mask_file') == path.stem + '.water.gz', 'Unexpected mask path')
    mask = folder / row['mask_file']
    need(sha(mask) == row['mask_sha256'], 'Mask digest mismatch')
    floors, before, after = mask_data(mask.read_bytes())
    need(hashlib.sha256(before).hexdigest() == row['before_water_sha256'], 'Before mask mismatch')
    need(hashlib.sha256(after).hexdigest() == row['after_water_sha256'], 'After mask mismatch')
    observed = collections.Counter()
    for i, (old, new) in enumerate(zip(before, after)):
        if old:
            observed['native_water'] += 1
            if old == new:
                observed['preserved_native_water'] += 1
            else:
                observed['all_native_changes'] += 1
        elif new:
            observed['new_water'] += 1
            floor = floors[i & 255]
            if LOW + (i >> 8) <= floor or floor >= 128:
                observed['below_native_surface_additions'] += 1
    for key in ('native_water', 'preserved_native_water', 'new_water', 'below_native_surface_additions'):
        need(observed[key] == row[key], 'Counter/mask inconsistency: ' + key)
    need(observed['all_native_changes'] == sum(row[k] for k in ('removed_native_water', 'changed_native_water_state', 'explicit_dry_mine_changes')), 'Native-change accounting mismatch')
    for key in COUNTERS:
        need(type(row[key]) is int and row[key] >= 0, 'Invalid audit counter')
    expected_pass = all(row[k] == 0 for k in ('removed_native_water', 'changed_native_water_state', 'below_native_surface_additions'))
    need(row.get('pass') is expected_pass, 'Contradictory audit pass value')
    return (cx, cz), row, (floors, before, after)


def audit_folder(folder, run_id):
    rows, masks, failures = {}, {}, []
    for path in sorted(folder.glob('*.json')):
        try:
            key, row, mask = verify_row(folder, path, run_id)
            need(key not in rows, 'Duplicate chunk evidence')
            rows[key], masks[key] = row, mask
        except Exception as error:
            failures.append({'path': path.name, 'error': repr(error)})
    missing = sorted(set(CHUNKS) - rows.keys())
    need(len(OLD) == 48 and len(REMOTE) == 81 and len(CHUNKS) == 129, 'Sample plan changed')
    def totals(positions):
        selected = [rows[key] for key in positions if key in rows]
        return {'chunks': len(selected), **{k: sum(r[k] for r in selected) for k in COUNTERS}}
    summary = {'pass': bool(rows) and not failures and not missing and all(r['pass'] for r in rows.values()),
               'missing_target_chunks': missing, 'invalid_records': failures,
               'original_targets': totals(OLD), 'remote_targets': totals(REMOTE),
               'all_targets': totals(CHUNKS), 'all_audited_including_halo': totals(rows),
               'failing_chunks': [r for r in rows.values() if not r['pass']]}
    return summary, rows, masks


def seam_provenance(masks):
    """Zero fluid code is NOT proof of air; these are water/non-water interfaces.
    Saved block states, below, identify actual water/air faces.
    """
    counts = collections.Counter()
    examples = []
    for cx, cz in sorted(REMOTE):
        if (cx, cz) not in masks:
            continue
        for axis, neighbor in (('x', (cx + 1, cz)), ('z', (cx, cz + 1))):
            if neighbor not in REMOTE or neighbor not in masks:
                continue
            left, right = masks[(cx, cz)], masks[neighbor]
            for y in range(LOW, HIGH + 1):
                for edge in range(16):
                    a = ((y - LOW) << 8) | ((edge << 4) | 15 if axis == 'x' else (15 << 4) | edge)
                    b = ((y - LOW) << 8) | ((edge << 4) if axis == 'x' else edge)
                    pre = bool(left[1][a]) != bool(right[1][b])
                    post = bool(left[2][a]) != bool(right[2][b])
                    counts['pre_light_water_nonwater_faces'] += int(pre)
                    counts['post_light_water_nonwater_faces'] += int(post)
                    if post:
                        label = 'preexisting_interface' if pre else 'created_in_light_chain'
                        counts[label] += 1
                        if len(examples) < 30 and not pre:
                            examples.append({'chunk': [cx, cz], 'neighbor': list(neighbor), 'axis': axis, 'y': y, 'edge_offset': edge,
                                             'before': [left[1][a], right[1][b]], 'after': [left[2][a], right[2][b]]})
    return {'scope': 'Water/non-water mask contacts, NOT automatically water/air defects', 'counts': dict(counts), 'examples': examples}


def saved_inventory(work, out, live_report):
    observer = load('r395_saved_observer', ROOT / 'scripts/probe-never-overworld-trees-villages-r1.py')
    paired = load('r395_saved_paired', ROOT / 'scripts/probe-never-overworld-paired-r12.py')
    nbt = observer.load_nbt(ROOT)
    inventory = {'scope': 'Read-only persisted remote chunks after normal stop; no player activation or dungeon-completeness claim', 'phases': {}}
    # trial directory now contains post-restart bytes; never mislabel it first-pass evidence.
    selected = [('r38-restart', 'trial'), ('r38-reverse-water', 'reverse')]
    if not live_report.get('phases', {}).get('r38-restart', {}).get('normal_stop'):
        selected[0] = ('r38-trial-water', 'trial')
    for phase_name, subfolder in selected:
        phase = live_report.get('phases', {}).get(phase_name, {})
        if not phase.get('normal_stop') or phase.get('exit_code') != 0:
            inventory['phases'][phase_name] = {'read': False, 'reason': 'No confirmed normal stop'}
            continue
        try:
            region = work / subfolder / 'world/dimensions/minecraft/overworld/region'
            volume = paired.saved_volume(observer, nbt, region, sorted(REMOTE), phase)
            starts, spawners, types = [], [], collections.Counter()
            for (cx, cz), root in volume.roots.items():
                for key, start in root.get('structures', {}).get('starts', {}).items():
                    if isinstance(start, dict) and start.get('id') not in (None, 'INVALID', 'minecraft:invalid'):
                        starts.append({'chunk': [cx, cz], 'key': key, 'data': start})
                for entity in root.get('block_entities', []):
                    types[entity.get('id', 'unknown')] += 1
                    if entity.get('id') in ('minecraft:spawner', 'minecraft:trial_spawner', 'minecraft:vault'):
                        spawners.append(entity)
            air = {'minecraft:air', 'minecraft:cave_air', 'minecraft:void_air'}
            def water(state):
                return state['Name'] == 'minecraft:water' or state.get('Properties', {}).get('waterlogged') == 'true' or state['Name'] in {'minecraft:seagrass','minecraft:tall_seagrass','minecraft:kelp','minecraft:kelp_plant','minecraft:bubble_column'}
            boundaries = []
            for cx, cz in sorted(REMOTE):
                for axis, neighbor in (('x', (cx + 1, cz)), ('z', (cx, cz + 1))):
                    if neighbor not in REMOTE:
                        continue
                    points = []
                    for y in range(-64, 129):
                        for edge in range(16):
                            x, z = (cx * 16 + 15, cz * 16 + edge) if axis == 'x' else (cx * 16 + edge, cz * 16 + 15)
                            a = volume.at(x, y, z)
                            b = volume.at(x + (axis == 'x'), y, z + (axis == 'z'))
                            need(isinstance(a, dict) and isinstance(b, dict), 'Unreadable boundary cell')
                            if (water(a) and b['Name'] in air) or (water(b) and a['Name'] in air):
                                points.append([x, y, z])
                    if points:
                        boundaries.append({'chunk': [cx, cz], 'neighbor': list(neighbor), 'axis': axis,
                                           'water_air_faces': len(points), 'positions': points})
            boundaries.sort(key=lambda r: r['water_air_faces'], reverse=True)
            inventory['phases'][phase_name] = {'read': True, 'chunks': len(volume.roots), 'structure_starts': starts,
                'block_entity_counts': dict(types), 'spawners_and_vaults': spawners,
                'camera_samples_diagnostic_only': [{'pos': list(p), 'state': volume.at(*p)} for p in ((-3217,46,-3398),(-3259,46,-3397))],
                'boundary_scope': 'actual water/air faces y=-64..128; not every interface is a defect',
                'water_air_faces': sum(r['water_air_faces'] for r in boundaries), 'boundaries': boundaries}
        except (Exception, SystemExit) as error:
            inventory['phases'][phase_name] = {'read': False, 'error': repr(error)}
    save(out / 'remote-saved-inventory.json', inventory)
    return inventory


def launch_command(jar, agent, run_id, extra):
    need(isinstance(run_id, str) and str(uuid.UUID(run_id)) == run_id, 'Invalid diagnostic run UUID')
    need(all(isinstance(v, str) and v.startswith('-D') for v in extra), 'Extra QA flags must remain system properties')
    need(not any(v.startswith('-Dneverfolia.waterAuditRunId') for v in extra), 'Duplicate run identity')
    return ['java', '-Xms1G', '-Xmx4G', '-XX:ActiveProcessorCount=4', '-DPaper.WorkerThreadCount=1',
            '-javaagent:' + str(agent), '-Dneverfolia.waterAuditRunId=' + run_id, *extra, '-jar', str(jar), '--nogui']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('candidate', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    candidate, out = args.candidate.resolve(), args.output.resolve()
    expected = {'server.jar': CORE, 'NeverOverworld.zip': PACK, 'NeverNether.zip': NETHER}
    for name, value in expected.items():
        need(sha(candidate / name) == value, 'Wrong exact candidate: ' + name)
    agent = out / 'NeverFolia-R395-Observer-CI-ONLY.jar'
    build = json.loads((out / 'observer-build.json').read_text())
    need(sha(agent) == build['agent_sha256'], 'Observer agent changed')
    source = ROOT / 'qa/field-r38/run-live.py'
    raw = source.read_bytes()
    need(hashlib.sha1(f'blob {len(raw)}\0'.encode() + raw).hexdigest() == HARNESS_BLOB, 'Baseline harness changed')
    live = out / 'live'
    live.mkdir(parents=True, exist_ok=False)
    work = ROOT / '.work/r395-live-worlds'
    need(not work.exists(), 'Refusing reused world directory')
    run_id = str(uuid.uuid4())
    save(out / 'plan.json', {'run_id': run_id, 'seed': -4651369264513492755, 'inputs': expected,
        'target_chunks': CHUNKS, 'remote_chunks': sorted(REMOTE), 'original_chunks': sorted(OLD),
        'observer_only_agent_sha256': sha(agent), 'gameplay_mutations': False, 'production_accepted': False})
    harness = load('r395_live_harness', source)
    harness.CHUNKS = CHUNKS
    original_load, original_save = harness.load, harness.save
    def revised_load(name, path):
        module = original_load(name, path)
        if Path(path).name == 'probe-never-overworld-paired-r12.py':
            original_factory = module.make_server
            def factory(observer):
                base = original_factory(observer)
                class InstrumentedServer(base):
                    def __init__(self, jar, folder, log, java_args=None):
                        # Keep the original supervisor and commands unchanged. Only this
                        # diagnostic subclass can launch this exact already-verified agent.
                        need(sha(jar) == CORE and sha(agent) == build['agent_sha256'], 'Unreviewed JVM input')
                        command = launch_command(jar, agent, run_id, list(java_args or []))
                        self.log = log
                        self.stream = log.open('x', encoding='utf-8')
                        self.token = 0
                        try:
                            self.p = subprocess.Popen(command, cwd=folder, stdin=subprocess.PIPE,
                                stdout=self.stream, stderr=subprocess.STDOUT, text=True, bufsize=1)
                        except Exception:
                            self.stream.close()
                            raise
                return InstrumentedServer
            module.make_server = factory
        return module
    def revised_save(path, data):
        if Path(path).name == 'r38-live-qa.json':
            data['scope'] = '129 saved targets: original 48 and remote 81; existing trial fixtures, restart, reverse-order generation. Observer class instrumented only. No proof of player activation inside remote dungeon.'
            data['run_id'] = run_id
            data['target_chunks'] = CHUNKS
            data['production_accepted'] = False
        original_save(path, data)
    harness.load, harness.save = revised_load, revised_save
    sys.argv = ['run-live.py', '--jar', str(candidate / 'server.jar'), '--overworld', str(candidate / 'NeverOverworld.zip'),
        '--nether', str(candidate / 'NeverNether.zip'), '--controller-plugin', str(ROOT / '.work/r395-plugins/R37DungeonQa.jar'),
        '--trial-plugin', str(ROOT / '.work/r395-plugins/R38TrialQa.jar'), '--output', str(live), '--work', str(work),
        '--source-sha', __import__('os').environ.get('GITHUB_SHA', 'unknown')]
    report = {'pass': False, 'run_id': run_id, 'production_accepted': False}
    try:
        harness.main()
    except (Exception, SystemExit) as error:
        report['harness_error'] = repr(error)
    try:
        base_report = json.loads((live / 'r38-live-qa.json').read_text())
        report['harness_pass'] = base_report.get('pass') is True
        report['phases'] = {k: {a: b for a, b in v.items() if a in ('pass','error','normal_stop','exit_code','seams')} for k, v in base_report.get('phases', {}).items()}
        for folder_name in ('r38-water-audit', 'r38-reverse-audit'):
            summary, rows, masks = audit_folder(live / folder_name, run_id)
            report[folder_name] = summary
            save(out / (folder_name + '-mask-boundaries.json'), seam_provenance(masks))
        logs = sorted(live.glob('*.log'))
        markers = {p.name: {'applied': p.read_text(errors='replace').count('NL_R395_AUDIT_AGENT_APPLIED'),
                           'rejected': 'NL_R395_AUDIT_AGENT_REJECTED' in p.read_text(errors='replace')} for p in logs}
        report['agent_application'] = markers
        report['saved_inventory'] = {k: {'read': v.get('read'), 'chunks': v.get('chunks'),
            'starts': len(v.get('structure_starts', [])), 'spawners_and_vaults': len(v.get('spawners_and_vaults', [])),
            'water_air_faces': v.get('water_air_faces'), 'error': v.get('error')} for k, v in saved_inventory(work, out, base_report)['phases'].items()}
        report['gameplay_files_unchanged'] = all(sha(candidate / n) == h for n, h in expected.items())
        report['pass'] = report['harness_pass'] and report['r38-water-audit']['pass'] and report['r38-reverse-audit']['pass'] and report['gameplay_files_unchanged'] and len(markers) == 4 and all(v['applied'] == 1 and not v['rejected'] for v in markers.values()) and all(v['read'] for v in report['saved_inventory'].values())
    except (Exception, SystemExit) as error:
        report['verification_error'] = repr(error)
    save(out / 'r395-water-result.json', report)
    print(json.dumps(report, indent=2), flush=True)
    # Retain real region/entity chunks for independent review, even on assertion failure.
    with zipfile.ZipFile(out / 'saved-worlds-evidence.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        for subfolder in ('trial', 'reverse'):
            root = work / subfolder / 'world'
            if root.exists():
                for path in root.rglob('*'):
                    if path.is_file() and (path.suffix in ('.mca', '.mcc') or path.name in ('level.dat', 'level.dat_old')):
                        archive.write(path, path.relative_to(work).as_posix())
    return 0 if report['pass'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
