#!/usr/bin/env python3
"""HEIGHT2 + ORE-LIGHT: repeat the fixed candidate, keep historical deltas.

The historical strict paired gate is NOT modified or relabelled. That gate
already fails on repeats of the delivered binary. This experiment instead
requires exact repeatability of the fixed candidate and unchanged FULL chunks,
while measuring its density against the exact delivered baseline. Native mask
subset and late-writer tests remain mandatory. All worlds are new and separate.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import zipfile

PROFILE = 'FIELD-R12-HEIGHT2-ORE-LIGHT-1'
PACKS = {'NeverOverworld.zip', 'NeverNether.zip'}
ROLES = ('historical', 'candidate-a', 'candidate-b')
PHASES = ('initial', 'complete', 'restart')
MARKERS = ('FieldPolicyR12Test', 'FieldR12Smoke', 'TreePreservationSmoke',
           'UpperOreLightR12Smoke', 'VillageFoundationSmoke', 'FloodBoundarySmoke',
           'DesertR1Smoke', 'SandstormR1Smoke', 'NeverNetherFieldCleanupR15Smoke')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    require(spec is not None and spec.loader is not None, 'missing module')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


def evaluate(paired, runs, ores, source_sha):
    require(set(runs) == set(ROLES) == set(ores), 'all three independent roles required')
    old, a, b = (runs[r] for r in ROLES)
    require(all(isinstance(r, dict) for r in runs.values()), 'invalid run evidence')
    protocol = (all(normal_phases(r) for r in runs.values())
                and old.get('source_sha') == paired.BASE_SHA
                and old.get('jar_sha256') == paired.BASE_JAR_SHA
                and a.get('source_sha') == b.get('source_sha') == source_sha
                and a.get('jar_sha256') == b.get('jar_sha256')
                and set(old.get('pack_sha256', {})) == PACKS
                and all(r.get('seed') == paired.SEED and r.get('pack_sha256') == old['pack_sha256']
                        for r in runs.values())
                and bool(old.get('requests'))
                and old['requests'] == a.get('requests') == b.get('requests')
                and paired.plan_signature(old['areas']) == paired.plan_signature(a['areas'])
                == paired.plan_signature(b['areas']))
    delta = paired.ore_delta(ores['candidate-a'], ores['candidate-b'])
    historical = {r: paired.compare_ore(ores['historical'], ores[r]) for r in ROLES[1:]}
    density = all(v['baseline_blocks'] >= 200 and v['retained_ratio'] is not None
                  and 0.40 <= v['retained_ratio'] <= 0.60 for v in historical.values())
    stable = all(unchanged_phases(r) for r in runs.values())
    exact = protocol and len(ores['candidate-a']) >= 100 and delta['changed_positions'] == 0
    dry = all(mines_pass(runs[r], paired.MINE_TARGETS) for r in ROLES[1:])
    trees = {r: submerged(runs[r]) for r in ROLES}
    tree_observation = trees['historical'] > 0 and all(trees[r] < trees['historical'] for r in ROLES[1:])
    nether = all(r.get('nether_roof_cells') == 9 * 256 for r in runs.values())
    checks = {'equal_execution_protocol': protocol, 'exact_candidate_repeatability': exact,
              'saved_phase_stability': stable, 'density_vs_delivered': density,
              'both_candidate_mines_dry_with_metadata': dry,
              'submerged_component_reduction_observed': tree_observation,
              'both_packs_and_nether_roof_verified': nether}
    return {'schema': 1, 'profile': PROFILE, 'source_sha': source_sha, 'seed': paired.SEED,
            'production_ready': False, 'manual_test_eligible': all(checks.values()), 'checks': checks,
            'candidate_jar_sha256': a['jar_sha256'], 'baseline_jar_sha256': old['jar_sha256'],
            'pack_sha256': a['pack_sha256'], 'candidate_repeatability': delta,
            'historical_comparisons': historical, 'submerged_components': trees,
            'historical_exact_subset_gate_preserved': all(x['pass'] is True for x in historical.values()),
            'limitations': ['Independent protocol: does not relabel the failed historical paired gate.',
                'New candidate must match its repeat at EVERY sampled resource coordinate; no tolerance.',
                'Historical coordinates remain diagnostics; the exact final-mask subset is a native test.',
                'One seed, three forest areas, two mine variants; not complete world acceptance.',
                'Tree components are not identities. Y125/126 and fallen exceptions are native tests.',
                'Nether test covers joint startup, nine FULL chunks, roof512/padding, not all Nether mechanics.',
                'Village and mine appearance still requires in-game review.']}


def check_native(log):
    for name in MARKERS:
        require(re.search(r'^PASS ' + name + r' checks=[1-9][0-9]*(?:\s|$)', log, re.M),
                'missing native result: ' + name)
    require('BUILD SUCCESSFUL' in log and 'BUILD FAILED' not in log, 'native build incomplete')


def package(out, jar, packs, report, manifest, run_id):
    require(report.get('profile') == PROFILE and report.get('manual_test_eligible') is True
            and report.get('production_ready') is False, 'candidate not eligible')
    expected = {'equal_execution_protocol', 'exact_candidate_repeatability', 'saved_phase_stability',
                'density_vs_delivered', 'both_candidate_mines_dry_with_metadata',
                'submerged_component_reduction_observed', 'both_packs_and_nether_roof_verified'}
    require(set(report.get('checks', {})) == expected and all(v is True for v in report['checks'].values()),
            'incomplete independent checks')
    require(manifest.get('profile') == PROFILE and manifest.get('source_sha') == report['source_sha']
            and manifest.get('overlay_installed') is True, 'build profile mismatch')
    require(sha(jar) == report['candidate_jar_sha256'] == manifest['jar_sha256'], 'JAR changed')
    require(set(packs) == PACKS and {n: sha(p) for n, p in packs.items()} == report['pack_sha256'], 'pack changed')
    require(type(run_id) is int and run_id > 0, 'invalid workflow run')
    require(manifest.get('workflow_run') == run_id, 'different build run')
    check_native((out / 'build-smoke.log').read_text(encoding='utf-8'))
    require(json.loads((out / 'height2-ore-light.json').read_text()) == report, 'report not persisted')
    payload = {'server.jar': Path(jar).read_bytes()}
    payload.update({'world/datapacks/' + n: Path(p).read_bytes() for n, p in packs.items()})
    payload['server.properties'] = (f"level-name=world\nlevel-seed={report['seed']}\n"
        'initial-enabled-packs=vanilla,file/NeverOverworld.zip,file/NeverNether.zip\n').encode()
    for p in sorted(out.rglob('*')):
        if p.is_file() and p.suffix in ('.json', '.log', '.txt'):
            require(not p.is_symlink(), 'symlink in evidence')
            payload['evidence/' + p.relative_to(out).as_posix()] = p.read_bytes()
    info = dict(manifest, manual_test_eligible=True, production_ready=False, new_world_required=True,
                native_tree_origin_min_y=126, fallen_tree_exception=True, nether_included=True,
                village_visual_review_required=True,
                historical_exact_subset_gate_preserved=report['historical_exact_subset_gate_preserved'])
    payload['BUILD-INFO.json'] = (json.dumps(info, indent=2) + '\n').encode()
    payload['README-RU.txt'] = ('Тестовая сборка HEIGHT2 + ORE-LIGHT, Java 25.\n'
        'Распаковать в НОВУЮ папку. Оба датапака уже в world/datapacks.\n'
        'Обычное дерево: точка генерации не ниже Y126 при океане Y128.\n'
        'Поваленные деревья могут размещаться глубже. Старые деревья не удаляются.\n'
        'Руда: final retain=25%, верхняя очистка перенесена на LIGHT.\n'
        'Сухие шахты защищены по частям; квадратная подсыпка деревень отключена.\n'
        'Запуск: java -Xms1G -Xmx4G -jar server.jar --nogui\n'
        'EULA подтверждать только при согласии. Старые level.dat, регионы и lock не переносить.\n'
        'После успешной загрузки mojang_26.2.jar сохраняйте cache между рестартами.\n'
        'NeverEnd не включён. Production-ready=false; требуется осмотр в игре.\n'
        'Прежний провал проверки координат старой сборки не переименован в успех.\n'
        'Новый допуск основан на точном повторе исправленного кандидата и сравнении плотности;\n'
        'полное сравнение с историческими координатами также сохранено в evidence.\n').encode()
    payload['SHA256SUMS.txt'] = ''.join(hashlib.sha256(b).hexdigest() + '  ' + n + '\n'
                                      for n, b in sorted(payload.items())).encode()
    name = 'NeverFolia-HEIGHT2-ORE-LIGHT-TEST-' + report['source_sha'][:7] + '.zip'
    dest = out / name
    with zipfile.ZipFile(dest, 'x', zipfile.ZIP_DEFLATED) as archive:
        for n, b in sorted(payload.items()):
            archive.writestr(n, b)
    with zipfile.ZipFile(dest) as archive:
        require(archive.testzip() is None, 'bad bundle ZIP')
    return {'path': name, 'sha256': sha(dest), 'production_ready': False}


def run_experiment(root, out, paired, observer, nbt, jar, baseline, packs, source_sha):
    runs, ores, reference = {}, {}, None
    for role in ROLES:
        role_out = out / role
        role_out.mkdir(parents=True, exist_ok=False)
        # Each candidate uses label=candidate so the shared observer verifies
        # persisted mine metadata in BOTH copies. Root/output are independent.
        binary, label, source = ((baseline, 'baseline', paired.BASE_SHA) if role == 'historical'
                                 else (jar, 'candidate', source_sha))
        run_root = root / '.work' / ('height2-ore-light-' + role)
        run, census = paired.generate(run_root, observer, nbt, binary, packs, role_out, label, source, reference)
        runs[role], ores[role] = run, census
        reference = runs['historical']['areas']
    report = evaluate(paired, runs, ores, source_sha)
    for role in ROLES[1:]:
        observer.write_json(out / (role + '-vs-historical-full-delta.json'),
                            paired.ore_delta(ores['historical'], ores[role]))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('jar', 'baseline-jar', 'overworld', 'nether', 'output', 'build-manifest'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--source-sha', required=True)
    parser.add_argument('--run-id', type=int, required=True)
    args = parser.parse_args()
    require(re.fullmatch('[0-9a-f]{40}', args.source_sha), 'full source SHA required')
    root = Path(__file__).resolve().parents[2]
    paired = load('height2_paired', root / 'scripts/probe-never-overworld-paired-r12.py')
    observer = load('height2_observer', root / 'scripts/probe-never-overworld-trees-villages-r1.py')
    nbt = observer.load_nbt(root)
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    target = out / 'height2-ore-light.json'
    require(not target.exists(), 'existing report cannot be overwritten')
    require(sha(args.baseline_jar) == paired.BASE_JAR_SHA, 'wrong delivered baseline')
    manifest = json.loads(args.build_manifest.read_text())
    require(manifest.get('profile') == PROFILE and manifest.get('source_sha') == args.source_sha
            and manifest.get('jar_sha256') == sha(args.jar) and manifest.get('overlay_installed') is True,
            'missing exact build profile')
    packs = {'NeverOverworld.zip': args.overworld.resolve(), 'NeverNether.zip': args.nether.resolve()}
    report = {'profile': PROFILE, 'source_sha': args.source_sha, 'manual_test_eligible': False,
              'production_ready': False}
    try:
        report = run_experiment(root, out, paired, observer, nbt, args.jar.resolve(),
                                args.baseline_jar.resolve(), packs, args.source_sha)
        observer.write_json(target, report)
        require(report['manual_test_eligible'], 'candidate failed independent repeatability/density/mine/tree checks')
        bundle = package(out, args.jar.resolve(), packs, report, manifest, args.run_id)
        observer.write_json(out / 'height2-ore-light-bundle.json', bundle)
        print(json.dumps(bundle, indent=2), flush=True)
    except Exception as error:
        report['manual_test_eligible'] = False
        report['error'] = f'{type(error).__name__}: {error}'
        observer.write_json(target, report)
        raise


if __name__ == '__main__':
    main()
