#!/usr/bin/env python3
"""FIELD-R13/R16 natural acceptance for flooded Overworld and lava-ocean Nether.

The historical binary is only a density/tree reference and uses its compatible
R15 Nether pack. Two independent R13/R16 candidates must repeat exactly and
pass dry-mine, ecology, fluid-contact and R16 lava-ocean cavity audits.
"""
from __future__ import annotations

import argparse
from collections import Counter, deque
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import zipfile

PROFILE = 'FIELD-R13-R16-NATURAL-1'
R16_PROFILE = 'NN-R16-LAVA-OCEAN-CLEANUP-1'
HEIGHT_PROFILE = 'NN-R14-SUBSTRATE-1-ROOF512'
ROLES = ('historical', 'candidate-a', 'candidate-b')
PHASES = ('initial', 'complete', 'restart')
PACKS = {'NeverOverworld.zip', 'NeverNether.zip'}
MARKERS = (
    'FieldPolicyR12Test', 'FieldR12Smoke', 'TreePreservationSmoke',
    'UpperOreLightR12Smoke', 'VillageFoundationSmoke', 'FloodBoundarySmoke',
    'DesertR1Smoke', 'SandstormR1Smoke', 'NeverOverworldEcologyR13Smoke',
    'NeverNetherFieldCleanupR15Smoke', 'NeverNetherFieldCleanupR16Smoke',
)
AIR = {'minecraft:air', 'minecraft:cave_air', 'minecraft:void_air'}
HEIGHT_GATED = {
    'minecraft:brown_mushroom', 'minecraft:red_mushroom',
    'minecraft:brown_mushroom_block', 'minecraft:red_mushroom_block',
    'minecraft:mushroom_stem', 'minecraft:pumpkin',
    'minecraft:bamboo', 'minecraft:bamboo_sapling',
    'minecraft:moss_carpet', 'minecraft:pale_moss_carpet',
}
SHORE_PLANTS = {
    'minecraft:short_grass', 'minecraft:tall_grass', 'minecraft:fern', 'minecraft:large_fern',
    'minecraft:short_dry_grass', 'minecraft:tall_dry_grass', 'minecraft:dead_bush',
    'minecraft:bush', 'minecraft:firefly_bush', 'minecraft:leaf_litter',
    'minecraft:dandelion', 'minecraft:poppy', 'minecraft:blue_orchid', 'minecraft:allium',
    'minecraft:azure_bluet', 'minecraft:red_tulip', 'minecraft:orange_tulip',
    'minecraft:white_tulip', 'minecraft:pink_tulip', 'minecraft:oxeye_daisy',
    'minecraft:cornflower', 'minecraft:lily_of_the_valley', 'minecraft:wither_rose',
    'minecraft:torchflower', 'minecraft:pitcher_plant', 'minecraft:pink_petals',
    'minecraft:wildflowers', 'minecraft:cactus_flower',
    'minecraft:closed_eyeblossom', 'minecraft:open_eyeblossom',
    'minecraft:sunflower', 'minecraft:lilac', 'minecraft:rose_bush', 'minecraft:peony',
}
NETHER_ROCK = {
    'minecraft:netherrack', 'minecraft:basalt', 'minecraft:smooth_basalt',
    'minecraft:blackstone', 'minecraft:magma_block', 'minecraft:soul_sand',
    'minecraft:soul_soil', 'minecraft:crimson_nylium', 'minecraft:warped_nylium',
    'minecraft:nether_quartz_ore', 'minecraft:nether_gold_ore',
    'minecraft:ancient_debris', 'minecraft:gravel', 'minecraft:bedrock',
}
DIRECTIONS = ((1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1))


def require(ok, message):
    if not ok:
        raise ValueError(message)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    require(spec is not None and spec.loader is not None, 'missing module: '+str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')


def normal_phases(run):
    phases = run.get('phases', [])
    return (tuple(p.get('name') for p in phases) == PHASES
            and all(p.get('normal_stop') is True and type(p.get('exit_code')) is int
                    and p['exit_code'] == 0 for p in phases))


def unchanged_phases(run):
    transitions = run.get('ore_transitions', [])
    return (len(transitions) == 2
            and all(type(d.get('changed_positions')) is int and d['changed_positions'] == 0
                    for d in transitions))


def mines_pass(run, targets):
    mines = [v for v in run.get('observations', []) if 'fluid_examples' in v]
    return (len(mines) == len(targets) and {v['target'] for v in mines} == set(targets)
            and all(v.get('metadata_checked') is True
                    and v['counts'].get('fluid_cells', 0) == 0
                    and v['counts'].get('air_cells', 0) >= 20 for v in mines))


def submerged(run):
    return sum(x.get('counts', {}).get('wholly_submerged_components', 0)
               for x in run.get('observations', []))


def water(state):
    return (isinstance(state, dict)
            and (state.get('Name') == 'minecraft:water'
                 or state.get('Properties', {}).get('waterlogged') == 'true'))


def source_lava(state):
    if not isinstance(state, dict) or state.get('Name') != 'minecraft:lava':
        return False
    return state.get('Properties', {}).get('level', '0') == '0'


def collect_overworld(observer, nbt, world, plan):
    region = world/'dimensions/minecraft/overworld/region'
    require(region.is_dir(), 'candidate Overworld region missing')
    chunks = {tuple(p) for area in plan.get('areas', []) for p in area.get('chunks', [])}
    require(75 <= len(chunks) <= 1200, 'unexpected R13 natural chunk coverage')
    roots = {p: nbt.read_chunk_nbt(region, *p) for p in sorted(chunks)}
    for p, doc in roots.items():
        require(doc.get('Status') == 'minecraft:full'
                and (doc.get('xPos'), doc.get('zPos')) == p, 'non-FULL Overworld chunk: '+str(p))
    return observer.Volume(roots), len(chunks)


def ecology_audit(observer, nbt, world, plan):
    volume, chunk_count = collect_overworld(observer, nbt, world, plan)
    counts = Counter()
    examples = {'height_gated_below_y126': [], 'shoreline_plant_water_contact': [],
                'lava_water_face_contact': []}
    lava_faces = set()
    for (cx, sy, cz), section in sorted(volume.sections.items()):
        palette = section['block_states'].get('palette', [])
        names = {s.get('Name') for s in palette if isinstance(s, dict)}
        low = sy*16
        need_height = low < 126 and bool(names & HEIGHT_GATED)
        need_shore = low <= 130 and bool(names & SHORE_PLANTS)
        need_lava = 'minecraft:lava' in names
        if not (need_height or need_shore or need_lava):
            continue
        for i, state in enumerate(volume.section((cx, sy, cz))):
            name = state.get('Name')
            if name not in HEIGHT_GATED and name not in SHORE_PLANTS and name != 'minecraft:lava':
                continue
            x = cx*16 + (i & 15)
            y = sy*16 + (i >> 8)
            z = cz*16 + ((i >> 4) & 15)
            pos = (x, y, z)
            counts['relevant_blocks_scanned'] += 1
            if name in HEIGHT_GATED and y < 126:
                counts['height_gated_below_y126'] += 1
                if len(examples['height_gated_below_y126']) < 40:
                    examples['height_gated_below_y126'].append({'position': list(pos), 'block': name})
            if name in SHORE_PLANTS and y <= 130:
                own = water(state)
                above = volume.at(x, y+1, z)
                below = volume.at(x, y-1, z)
                if own or water(above) or water(below):
                    counts['shoreline_plant_water_contact'] += 1
                    if len(examples['shoreline_plant_water_contact']) < 40:
                        examples['shoreline_plant_water_contact'].append({
                            'position': list(pos), 'block': name, 'waterlogged': own,
                            'above': None if above is None else above.get('Name'),
                            'below': None if below is None else below.get('Name'),
                        })
            if name == 'minecraft:lava':
                for dx, dy, dz in DIRECTIONS:
                    other = (x+dx, y+dy, z+dz)
                    adjacent = volume.at(*other)
                    if adjacent is None or not water(adjacent):
                        continue
                    edge = tuple(sorted((pos, other)))
                    if edge in lava_faces:
                        continue
                    lava_faces.add(edge)
                    counts['lava_water_face_contact'] += 1
                    if len(examples['lava_water_face_contact']) < 40:
                        examples['lava_water_face_contact'].append({
                            'lava': list(pos), 'water': list(other), 'water_state': adjacent,
                        })
    for key in examples:
        counts.setdefault(key, 0)
    passed = all(counts[key] == 0 for key in examples)
    return {
        'schema': 1, 'audit': 'neveroverworld-field-r13-ecology-r1', 'chunk_count': chunk_count,
        'ocean_y': 128, 'min_height_gated_y': 126, 'water_support_scan_max_y': 130,
        'counts': dict(counts), 'examples': examples, 'pass': passed,
        'scope': 'Saved FULL chunks selected by the repeatable forest+mine natural protocol; read-only.',
    }


def r16_lava_ocean_audit(observer, nbt, world):
    region = world/'dimensions/minecraft/the_nether/region'
    require(region.is_dir(), 'candidate Nether region missing')
    selected = {(x, z) for x in range(-196, -193) for z in range(-394, -391)}
    roots = {p: nbt.read_chunk_nbt(region, *p) for p in sorted(selected)}
    for p, doc in roots.items():
        require(doc.get('Status') == 'minecraft:full'
                and (doc.get('xPos'), doc.get('zPos')) == p, 'non-FULL Nether chunk: '+str(p))
    volume = observer.Volume(roots)
    remaining = []
    remaining_count = 0
    total_air_components = 0
    for cx, cz in sorted(selected):
        visited = set()
        for y in range(-127, 32):
            for lz in range(16):
                for lx in range(16):
                    start = (lx, y, lz)
                    if start in visited:
                        continue
                    absolute = (cx*16+lx, y, cz*16+lz)
                    state = volume.at(*absolute)
                    if state is None or state.get('Name') not in AIR:
                        visited.add(start)
                        continue
                    queue = deque([start])
                    visited.add(start)
                    cells = []
                    safe = True
                    lava_boundary = 0
                    rock_boundary = 0
                    while queue:
                        x0, y0, z0 = queue.popleft()
                        cells.append((x0, y0, z0))
                        if len(cells) > 1024 or x0 in (0, 15) or z0 in (0, 15):
                            safe = False
                        for dx, dy, dz in DIRECTIONS:
                            nx, ny, nz = x0+dx, y0+dy, z0+dz
                            if nx < 0 or nx > 15 or nz < 0 or nz > 15 or ny < -128 or ny > 511:
                                safe = False
                                continue
                            adjacent = volume.at(cx*16+nx, ny, cz*16+nz)
                            require(adjacent is not None, 'unexpected unknown owner-chunk Nether cell')
                            if adjacent.get('Name') in AIR:
                                if ny > 31:
                                    safe = False
                                    continue
                                key = (nx, ny, nz)
                                if key not in visited:
                                    visited.add(key)
                                    queue.append(key)
                            elif source_lava(adjacent):
                                lava_boundary += 1
                            elif adjacent.get('Name') in NETHER_ROCK:
                                rock_boundary += 1
                            else:
                                safe = False
                    total_air_components += 1
                    qualifies = (safe and 0 < len(cells) <= 1024 and lava_boundary >= 4
                                 and lava_boundary >= rock_boundary)
                    if qualifies:
                        remaining_count += 1
                    if qualifies and len(remaining) < 100:
                        xs = [p[0] for p in cells]
                        ys = [p[1] for p in cells]
                        zs = [p[2] for p in cells]
                        remaining.append({
                            'chunk': [cx, cz], 'size': len(cells),
                            'bbox_local': [min(xs), min(ys), min(zs), max(xs), max(ys), max(zs)],
                            'lava_boundary': lava_boundary, 'rock_boundary': rock_boundary,
                        })
    native_lock = world/'.neverfolia-nevernether-native.lock'
    height_lock = world/'.neverfolia-nevernether-height.lock'
    require(native_lock.is_file() and height_lock.is_file(), 'NeverNether saved lock missing')
    native_value = native_lock.read_text(encoding='utf-8')
    height_value = height_lock.read_text(encoding='utf-8')
    locks = native_value == R16_PROFILE+'\n' and height_value == HEIGHT_PROFILE+'\n'
    return {
        'schema': 1, 'audit': 'nevernether-r16-lava-ocean-r1', 'chunk_count': len(selected),
        'range_y': [-127, 31], 'max_candidate_size': 1024,
        'air_components_examined': total_air_components,
        'remaining_r16_lava_ocean_candidates': remaining_count, 'examples': remaining,
        'saved_native_lock': native_value.rstrip('\n'), 'saved_height_lock': height_value.rstrip('\n'),
        'locks_verified': locks, 'pass': locks and remaining_count == 0,
        'scope': 'Nine persisted FULL chunks from the fixed candidate protocol; exact R16 owner-chunk predicate, read-only.',
    }


def run_experiment(root, out, paired, observer, nbt, jar, baseline,
                   current_packs, historical_packs, source_sha):
    runs, ores, worlds = {}, {}, {}
    reference = None
    for role in ROLES:
        role_out = out/role
        role_out.mkdir(parents=True, exist_ok=False)
        if role == 'historical':
            binary, label, source, packs = baseline, 'baseline', paired.BASE_SHA, historical_packs
        else:
            binary, label, source, packs = jar, 'candidate', source_sha, current_packs
        role_root = root/'.work'/('field-r13-r16-natural-'+role)
        run, census = paired.generate(
            role_root, observer, nbt, binary, packs, role_out, label, source, reference
        )
        runs[role], ores[role] = run, census
        worlds[role] = role_root/'.work'/('field-r12-paired-'+label)/'world'
        if role == 'historical':
            reference = run['areas']
    return runs, ores, worlds


def evaluate(paired, runs, ores, ecology, nether, source_sha):
    require(set(runs) == set(ROLES) == set(ores), 'all three roles required')
    old, a, b = (runs[r] for r in ROLES)
    protocol = (
        all(normal_phases(r) for r in runs.values())
        and old.get('source_sha') == paired.BASE_SHA
        and old.get('jar_sha256') == paired.BASE_JAR_SHA
        and a.get('source_sha') == b.get('source_sha') == source_sha
        and a.get('jar_sha256') == b.get('jar_sha256')
        and set(old.get('pack_sha256', {})) == set(a.get('pack_sha256', {})) == PACKS
        and old['pack_sha256']['NeverOverworld.zip'] == a['pack_sha256']['NeverOverworld.zip']
        == b['pack_sha256']['NeverOverworld.zip']
        and a['pack_sha256'] == b['pack_sha256']
        and all(r.get('seed') == paired.SEED for r in runs.values())
        and bool(old.get('requests'))
        and old['requests'] == a.get('requests') == b.get('requests')
        and paired.plan_signature(old['areas']) == paired.plan_signature(a['areas'])
        == paired.plan_signature(b['areas'])
    )
    delta = paired.ore_delta(ores['candidate-a'], ores['candidate-b'])
    historical = {r: paired.compare_ore(ores['historical'], ores[r]) for r in ROLES[1:]}
    density = all(v['baseline_blocks'] >= 200 and v['retained_ratio'] is not None
                  and 0.40 <= v['retained_ratio'] <= 0.60 for v in historical.values())
    stable = all(unchanged_phases(r) for r in runs.values())
    exact = protocol and len(ores['candidate-a']) >= 100 and delta['changed_positions'] == 0
    dry = all(mines_pass(runs[r], paired.MINE_TARGETS) for r in ROLES[1:])
    trees = {r: submerged(runs[r]) for r in ROLES}
    tree_observation = trees['historical'] > 0 and all(trees[r] < trees['historical'] for r in ROLES[1:])
    roof = all(r.get('nether_roof_cells') == 9*256 for r in runs.values())
    eco = all(ecology[r].get('pass') is True for r in ROLES[1:])
    lava_ocean = all(nether[r].get('pass') is True for r in ROLES[1:])
    checks = {
        'equal_execution_protocol_except_historical_r15_nether_pairing': protocol,
        'exact_candidate_ore_repeatability': exact,
        'saved_phase_stability': stable,
        'density_vs_delivered': density,
        'both_candidate_mines_dry_with_metadata': dry,
        'submerged_tree_component_reduction_observed': tree_observation,
        'overworld_r13_ecology_audit': eco,
        'nether_r16_lava_ocean_audit': lava_ocean,
        'nether_roof512_verified': roof,
    }
    return {
        'schema': 1, 'profile': PROFILE, 'source_sha': source_sha, 'seed': paired.SEED,
        'production_ready': False, 'manual_test_eligible': all(checks.values()), 'checks': checks,
        'candidate_jar_sha256': a['jar_sha256'], 'baseline_jar_sha256': old['jar_sha256'],
        'pack_sha256': a['pack_sha256'], 'historical_pack_sha256': old['pack_sha256'],
        'candidate_repeatability': delta, 'historical_comparisons': historical,
        'submerged_components': trees, 'ecology': ecology, 'nether_r16': nether,
        'historical_exact_subset_gate_preserved': all(x['pass'] is True for x in historical.values()),
        'limitations': [
            'One fixed seed and bounded natural samples; not whole-world production acceptance.',
            'Historical binary uses its compatible R15 Nether pack; Overworld pack and requests are identical.',
            'Candidate A/B must match every sampled ore coordinate and both saved worlds pass R13/R16 audits.',
            'Dry-mine coverage is one vanilla mineshaft plus one collapsed mine, all saved piece cells checked.',
            'R13 ecology covers every FULL chunk selected by the forest+mine protocol, not every biome.',
            'R16 audit mirrors the owner-chunk predicate over the protocol nine FULL Nether chunks.',
            'Village/mine visual appearance still requires in-game review.',
        ],
    }


def check_native(log):
    for name in MARKERS:
        require(re.search(r'^PASS '+re.escape(name)+r' checks=[1-9][0-9]*(?:\s|$)', log, re.M),
                'missing native result: '+name)
    require('BUILD SUCCESSFUL' in log and 'BUILD FAILED' not in log, 'native build incomplete')


def package(out, jar, packs, report, manifest, run_id):
    require(report.get('profile') == PROFILE and report.get('manual_test_eligible') is True
            and report.get('production_ready') is False, 'candidate not eligible')
    require(all(v is True for v in report.get('checks', {}).values()), 'incomplete natural acceptance')
    require(manifest.get('profile') == PROFILE and manifest.get('source_sha') == report['source_sha']
            and manifest.get('r13_installed') is True and manifest.get('r16_installed') is True,
            'build profile mismatch')
    require(type(run_id) is int and run_id > 0 and manifest.get('workflow_run') == run_id,
            'workflow run mismatch')
    require(sha(jar) == report['candidate_jar_sha256'] == manifest.get('jar_sha256'), 'JAR changed')
    require(set(packs) == PACKS and {n: sha(p) for n,p in packs.items()} == report['pack_sha256'],
            'pack changed')
    check_native((out/'build-smoke.log').read_text(encoding='utf-8'))
    require(json.loads((out/'field-r13-r16-natural.json').read_text(encoding='utf-8')) == report,
            'report not persisted')
    payload = {'server.jar': Path(jar).read_bytes()}
    payload.update({'world/datapacks/'+n: Path(p).read_bytes() for n,p in packs.items()})
    payload['server.properties'] = (
        f"level-name=world\nlevel-seed={report['seed']}\n"
        'initial-enabled-packs=vanilla,file/NeverOverworld.zip,file/NeverNether.zip\n'
    ).encode()
    for p in sorted(out.rglob('*')):
        if p.is_file() and p.suffix in ('.json', '.log', '.txt'):
            require(not p.is_symlink(), 'symlink in evidence')
            payload['evidence/'+p.relative_to(out).as_posix()] = p.read_bytes()
    info = dict(manifest, manual_test_eligible=True, production_ready=False, new_world_required=True,
                native_tree_origin_min_y=126, nether_profile=R16_PROFILE,
                natural_acceptance_profile=PROFILE)
    payload['BUILD-INFO.json'] = (json.dumps(info, indent=2)+'\n').encode()
    payload['README-RU.txt'] = (
        'NeverFolia FIELD-R13/R16 — тестовый кандидат для НОВОГО мира, Java 25.\n'
        'Оба датапака уже лежат в world/datapacks; старый мир/region/level.dat не переносить.\n'
        'R13: грибы, тыквы, бамбук и мох не генерируются ниже Y126; трава/цветы очищаются при контакте с водой до Y130.\n'
        'R13: generated underground water/lava сбрасываются перед восстановлением surface-connected океана.\n'
        'R13: защищённые части шахт повторно осушаются после второго boundary-flood прохода.\n'
        'R16: закрываются только подтверждённые owner-chunk воздушные полости лавового океана; большие/краевые пещеры сохраняются.\n'
        'Natural gate: два независимых кандидата, сухие шахты после рестарта, R13 ecology audit, R16 lava-ocean audit, roof Y512.\n'
        'Запуск: java -Xms1G -Xmx4G -jar server.jar --nogui\n'
        'Production-ready=false: после CI всё равно нужен визуальный осмотр мира в игре.\n'
    ).encode('utf-8')
    payload['SHA256SUMS.txt'] = ''.join(
        hashlib.sha256(b).hexdigest()+'  '+n+'\n' for n,b in sorted(payload.items())
    ).encode()
    name = 'NeverFolia-FIELD-R13-R16-NATURAL-TEST-'+report['source_sha'][:7]+'.zip'
    dest = out/name
    with zipfile.ZipFile(dest, 'x', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for n,b in sorted(payload.items()):
            archive.writestr(n,b)
    with zipfile.ZipFile(dest) as archive:
        require(archive.testzip() is None, 'bad bundle ZIP')
    return {'path': name, 'sha256': sha(dest), 'production_ready': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('jar','baseline-jar','overworld','historical-nether','nether','output','build-manifest'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--source-sha', required=True)
    parser.add_argument('--run-id', type=int, required=True)
    args = parser.parse_args()
    require(re.fullmatch('[0-9a-f]{40}', args.source_sha), 'full source SHA required')
    root = Path(__file__).resolve().parents[2]
    paired = load('r13_r16_paired', root/'scripts/probe-never-overworld-paired-r12.py')
    observer = load('r13_r16_observer', root/'scripts/probe-never-overworld-trees-villages-r1.py')
    nbt = observer.load_nbt(root)
    require(sha(args.baseline_jar) == paired.BASE_JAR_SHA, 'wrong delivered baseline')
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    target = out/'field-r13-r16-natural.json'
    require(not target.exists(), 'existing natural report cannot be overwritten')
    manifest = json.loads(args.build_manifest.read_text(encoding='utf-8'))
    require(manifest.get('profile') == PROFILE and manifest.get('source_sha') == args.source_sha
            and manifest.get('jar_sha256') == sha(args.jar)
            and manifest.get('r13_installed') is True and manifest.get('r16_installed') is True,
            'missing exact R13/R16 build profile')
    current_packs = {'NeverOverworld.zip': args.overworld.resolve(), 'NeverNether.zip': args.nether.resolve()}
    historical_packs = {'NeverOverworld.zip': args.overworld.resolve(),
                        'NeverNether.zip': args.historical_nether.resolve()}
    report = {'schema': 1, 'profile': PROFILE, 'source_sha': args.source_sha,
              'manual_test_eligible': False, 'production_ready': False}
    try:
        runs, ores, worlds = run_experiment(
            root, out, paired, observer, nbt, args.jar.resolve(), args.baseline_jar.resolve(),
            current_packs, historical_packs, args.source_sha
        )
        ecology, nether = {}, {}
        for role in ROLES[1:]:
            ecology[role] = ecology_audit(observer, nbt, worlds[role], runs[role])
            nether[role] = r16_lava_ocean_audit(observer, nbt, worlds[role])
            write_json(out/role/'field-r13-ecology.json', ecology[role])
            write_json(out/role/'r16-lava-ocean.json', nether[role])
        report = evaluate(paired, runs, ores, ecology, nether, args.source_sha)
        for role in ROLES[1:]:
            write_json(out/(role+'-vs-historical-full-delta.json'),
                       paired.ore_delta(ores['historical'], ores[role]))
        write_json(target, report)
        require(report['manual_test_eligible'], 'FIELD-R13/R16 natural acceptance rejected; see report')
        bundle = package(out, args.jar.resolve(), current_packs, report, manifest, args.run_id)
        write_json(out/'field-r13-r16-natural-bundle.json', bundle)
        print(json.dumps(bundle, indent=2), flush=True)
    except Exception as error:
        report['manual_test_eligible'] = False
        report['error'] = f'{type(error).__name__}: {error}'
        write_json(target, report)
        raise


if __name__ == '__main__':
    main()
