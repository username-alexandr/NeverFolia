#!/usr/bin/env python3
"""Independent-gate and orchestration unit tests; collaborators are fixtures.

The unchanged paired observer's actual world/NBT methods are exercised in the
workflow, not simulated by these unit tests. No Minecraft execution is implied.
"""
from __future__ import annotations
from copy import deepcopy
from collections import Counter
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
import zipfile
import hashlib

spec = importlib.util.spec_from_file_location('probe_natural', Path(__file__).with_name('probe-natural.py'))
N = importlib.util.module_from_spec(spec); spec.loader.exec_module(N)


class PairedFixture:
    BASE_SHA = 'b' * 40
    BASE_JAR_SHA = 'b' * 64
    SEED = -2996952393010080672
    MINE_TARGETS = ('minecraft:mineshaft', 'neverfolia:collapsed_mine')

    @staticmethod
    def plan_signature(areas):
        return json.dumps(areas, sort_keys=True)

    @staticmethod
    def ore_delta(before, after):
        changes = [{'position': list(p), 'before': before.get(p), 'after': after.get(p)}
                   for p in sorted(before.keys() | after.keys()) if before.get(p) != after.get(p)]
        return {'changed_positions': len(changes), 'changes': changes}

    @staticmethod
    def compare_ore(before, after):
        added = sum(before.get(p) != k for p, k in after.items())
        ratio = len(after) / len(before) if before else None
        return {'baseline_blocks': len(before), 'candidate_blocks': len(after),
                'retained_ratio': ratio, 'new_or_retyped_positions': added,
                'pass': len(before) >= 200 and added == 0 and 0.4 <= ratio <= 0.6}


def fixture():
    source = 'a' * 40
    run = {'source_sha': source, 'jar_sha256': 'a' * 64, 'seed': PairedFixture.SEED,
           'pack_sha256': {p: p for p in N.PACKS},
           'areas': [{'kind': 'forest', 'chunks': [[0, 0]]}],
           'requests': [{'phase': 'initial', 'operation': 'locate'}],
           'phases': [{'name': p, 'normal_stop': True, 'exit_code': 0} for p in N.PHASES],
           'ore_transitions': [{'changed_positions': 0}, {'changed_positions': 0}],
           'observations': [{'target': t, 'fluid_examples': [], 'metadata_checked': True,
                             'counts': {'fluid_cells': 0, 'air_cells': 50}} for t in PairedFixture.MINE_TARGETS]
                            + [{'counts': {'wholly_submerged_components': 0}}],
           'nether_roof_cells': 2304}
    runs = {r: deepcopy(run) for r in N.ROLES}
    runs['historical'].update(source_sha=PairedFixture.BASE_SHA, jar_sha256=PairedFixture.BASE_JAR_SHA)
    runs['historical']['observations'][-1]['counts']['wholly_submerged_components'] = 12
    before = {(x, 0, 0): 'iron' for x in range(1000)}
    after = {p: k for p, k in before.items() if p[0] % 2 == 0}
    ores = {'historical': before, 'candidate-a': deepcopy(after), 'candidate-b': deepcopy(after)}
    return source, runs, ores


class GateTests(unittest.TestCase):
    def test_identical_candidate_and_half_density(self):
        source, runs, ores = fixture()
        self.assertTrue(N.evaluate(PairedFixture, runs, ores, source)['manual_test_eligible'])

    def test_changed_candidate_position_rejects_even_equal_counts(self):
        source, runs, ores = fixture()
        ores['candidate-b'][(9999, 0, 0)] = ores['candidate-b'].pop((0, 0, 0))
        r = N.evaluate(PairedFixture, runs, ores, source)
        self.assertFalse(r['manual_test_eligible'])
        self.assertEqual(r['candidate_repeatability']['changed_positions'], 2)

    def test_changed_kind_rejects(self):
        source, runs, ores = fixture(); ores['candidate-b'][(0, 0, 0)] = 'gold'
        self.assertFalse(N.evaluate(PairedFixture, runs, ores, source)['checks']['exact_candidate_repeatability'])

    def test_historical_failure_retained_not_relabelled(self):
        source, runs, ores = fixture()
        for role in N.ROLES[1:]: ores[role][(9999, 0, 0)] = ores[role].pop((0, 0, 0))
        report = N.evaluate(PairedFixture, runs, ores, source)
        self.assertTrue(report['manual_test_eligible'])
        self.assertFalse(report['historical_exact_subset_gate_preserved'])
        self.assertFalse(report['historical_comparisons']['candidate-a']['pass'])
        self.assertEqual(report['historical_comparisons']['candidate-a']['new_or_retyped_positions'], 1)

    def test_density_not_relaxed(self):
        for count in (50, 1000):
            source, runs, ores = fixture()
            for role in N.ROLES[1:]: ores[role] = dict(list(ores['historical'].items())[:count])
            self.assertFalse(N.evaluate(PairedFixture, runs, ores, source)['manual_test_eligible'])

    def test_insufficient_population(self):
        source, runs, ores = fixture()
        for role in N.ROLES: ores[role] = {}
        self.assertFalse(N.evaluate(PairedFixture, runs, ores, source)['manual_test_eligible'])

    def test_missing_and_reordered_phase_rejected(self):
        for phases in ([], list(reversed(N.PHASES))):
            source, runs, ores = fixture()
            runs['candidate-b']['phases'] = [{'name': p, 'normal_stop': True, 'exit_code': 0} for p in phases]
            self.assertFalse(N.evaluate(PairedFixture, runs, ores, source)['manual_test_eligible'])

    def test_nonzero_and_boolean_exit_not_normal(self):
        for code in (1, False, '0'):
            source, runs, ores = fixture(); runs['candidate-b']['phases'][0]['exit_code'] = code
            self.assertFalse(N.evaluate(PairedFixture, runs, ores, source)['manual_test_eligible'])

    def test_phase_ore_mutation_rejects(self):
        source, runs, ores = fixture(); runs['candidate-b']['ore_transitions'][1]['changed_positions'] = 1
        self.assertFalse(N.evaluate(PairedFixture, runs, ores, source)['manual_test_eligible'])

    def test_wrong_binary_or_pack_rejects(self):
        for field, value in (('jar_sha256', 'c' * 64), ('pack_sha256', {}), ('seed', 2), ('source_sha', 'c' * 40)):
            source, runs, ores = fixture(); runs['candidate-b'][field] = value
            self.assertFalse(N.evaluate(PairedFixture, runs, ores, source)['manual_test_eligible'])

    def test_different_requests_or_selection_reject(self):
        for field in ('areas', 'requests'):
            source, runs, ores = fixture(); runs['candidate-b'][field] = []
            self.assertFalse(N.evaluate(PairedFixture, runs, ores, source)['manual_test_eligible'])

    def test_repeat_candidate_also_requires_mine_metadata(self):
        source, runs, ores = fixture(); runs['candidate-b']['observations'][0]['metadata_checked'] = False
        self.assertFalse(N.evaluate(PairedFixture, runs, ores, source)['manual_test_eligible'])

    def test_wet_and_filled_mines_rejected(self):
        for field, count in (('fluid_cells', 1), ('air_cells', 0)):
            source, runs, ores = fixture(); runs['candidate-b']['observations'][0]['counts'][field] = count
            self.assertFalse(N.evaluate(PairedFixture, runs, ores, source)['manual_test_eligible'])

    def test_nether_roof_evidence_required(self):
        source, runs, ores = fixture(); runs['candidate-b']['nether_roof_cells'] = 0
        self.assertFalse(N.evaluate(PairedFixture, runs, ores, source)['manual_test_eligible'])

    def test_tree_observation_not_silently_skipped(self):
        source, runs, ores = fixture(); runs['candidate-b']['observations'][-1]['counts']['wholly_submerged_components'] = 12
        self.assertFalse(N.evaluate(PairedFixture, runs, ores, source)['manual_test_eligible'])

    def test_native_markers_require_real_pass_line(self):
        good = '\n'.join(f'PASS {s} checks=1' for s in N.MARKERS) + '\nBUILD SUCCESSFUL'
        N.check_native(good)
        for bad in (good.replace('PASS UpperOreLightR12Smoke', 'echo PASS UpperOreLightR12Smoke'),
                    good.replace('PASS FieldPolicyR12Test checks=1', 'PASS FieldPolicyR12Test checks=0'),
                    good + '\nBUILD FAILED'):
            with self.assertRaises(ValueError): N.check_native(bad)


class PackageTests(unittest.TestCase):
    def setup_case(self, out):
        source, runs, ores = fixture()
        jar = out / 'server.jar'; jar.write_bytes(b'jar fixture')
        packs = {p: out / p for p in N.PACKS}
        for n, p in packs.items(): p.write_bytes(n.encode())
        for r in N.ROLES[1:]: runs[r]['jar_sha256'] = N.sha(jar)
        for r in N.ROLES: runs[r]['pack_sha256'] = {n: N.sha(p) for n, p in packs.items()}
        report = N.evaluate(PairedFixture, runs, ores, source)
        manifest = {'profile': N.PROFILE, 'source_sha': source, 'workflow_run': 123,
                    'overlay_installed': True, 'jar_sha256': N.sha(jar)}
        (out / 'build-smoke.log').write_text('\n'.join(f'PASS {s} checks=1' for s in N.MARKERS) + '\nBUILD SUCCESSFUL')
        (out / 'height2-ore-light.json').write_text(json.dumps(report))
        return jar, packs, report, manifest

    def test_bundle_has_both_packs_and_verified_sums(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); args = self.setup_case(root)
            result = N.package(root, *args, 123)
            with zipfile.ZipFile(root / result['path']) as archive:
                self.assertIn('world/datapacks/NeverNether.zip', archive.namelist())
                for line in archive.read('SHA256SUMS.txt').decode().splitlines():
                    digest, name = line.split('  ', 1)
                    self.assertEqual(digest, hashlib.sha256(archive.read(name)).hexdigest())
                self.assertFalse(json.loads(archive.read('BUILD-INFO.json'))['production_ready'])

    def test_failed_or_incomplete_check_cannot_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); jar, packs, report, manifest = self.setup_case(root)
            report['checks']['exact_candidate_repeatability'] = False
            with self.assertRaises(ValueError): N.package(root, jar, packs, report, manifest, 123)
            self.assertFalse(list(root.glob('NeverFolia-*.zip')))

    def test_missing_overlay_or_wrong_run_cannot_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); jar, packs, report, manifest = self.setup_case(root)
            for field, value in (('overlay_installed', False), ('workflow_run', 124), ('profile', 'unpatched')):
                bad = dict(manifest); bad[field] = value
                with self.assertRaises(ValueError): N.package(root, jar, packs, report, bad, 123)

    def test_changed_jar_or_pack_cannot_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); jar, packs, report, manifest = self.setup_case(root)
            for p in (jar, *packs.values()):
                original = p.read_bytes(); p.write_bytes(b'changed')
                with self.assertRaises(ValueError): N.package(root, jar, packs, report, manifest, 123)
                p.write_bytes(original)

    def test_missing_nether_cannot_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); jar, packs, report, manifest = self.setup_case(root)
            del packs['NeverNether.zip']
            with self.assertRaises(ValueError): N.package(root, jar, packs, report, manifest, 123)

    def test_changed_persisted_report_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); args = self.setup_case(root)
            (root / 'height2-ore-light.json').write_text('{}')
            with self.assertRaises(ValueError): N.package(root, *args, 123)

    def test_existing_bundle_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); args = self.setup_case(root)
            result = N.package(root, *args, 123); prior = (root / result['path']).read_bytes()
            with self.assertRaises(FileExistsError): N.package(root, *args, 123)
            self.assertEqual((root / result['path']).read_bytes(), prior)


class OrchestrationTests(unittest.TestCase):
    def test_independent_worlds_and_metadata_for_both_candidates(self):
        source, runs, ores = fixture()
        paired = Mock(wraps=PairedFixture)
        for field in ('BASE_SHA', 'BASE_JAR_SHA', 'SEED', 'MINE_TARGETS'):
            setattr(paired, field, getattr(PairedFixture, field))
        calls = []
        def generate(root, observer, nbt, jar, packs, out, label, sha, reference):
            role = N.ROLES[len(calls)]; calls.append((root, out, label, reference))
            return runs[role], ores[role]
        paired.generate = generate
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); out = root / 'artifacts'; out.mkdir()
            report = N.run_experiment(root, out, paired, Mock(), Mock(), root/'new.jar', root/'old.jar', {}, source)
        self.assertTrue(report['manual_test_eligible'])
        self.assertEqual([c[2] for c in calls], ['baseline', 'candidate', 'candidate'])
        self.assertEqual(len({c[0] for c in calls}), 3)
        self.assertEqual(len({c[1] for c in calls}), 3)
        self.assertIsNone(calls[0][3]); self.assertEqual(calls[2][3], runs['historical']['areas'])

    def test_generation_failure_never_runs_remaining_roles(self):
        paired = Mock(); paired.BASE_SHA = PairedFixture.BASE_SHA
        paired.generate.side_effect = RuntimeError('normal stop failed')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); out = root/'artifacts'; out.mkdir()
            with self.assertRaises(RuntimeError):
                N.run_experiment(root, out, paired, Mock(), Mock(), root/'new.jar', root/'old.jar', {}, 'a'*40)
        self.assertEqual(paired.generate.call_count, 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
