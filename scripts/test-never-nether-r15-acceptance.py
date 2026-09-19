#!/usr/bin/env python3
"""Synthetic fail-closed regressions for the R15 acceptance and packaging gate."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

SPEC = importlib.util.spec_from_file_location('r15_gate', Path(__file__).with_name('check-never-nether-r15-acceptance.py'))
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


def fixture():
    plan = {'schema': 1, 'seed': GATE.SEED, 'chunk_count': 50, 'normal_stop': True,
            'process_exit_code': 0, 'chunks': [list(p) for p in sorted(GATE.EXPECTED)]}
    audit = {'schema': 1, 'read_only': True, 'audit': 'nevernether-field-integrity-r1',
             'chunk_count': 50, 'chunks': copy.deepcopy(plan['chunks']), 'range_y': [-128, 511],
             'pocket_limit': 64, 'counts': {'enclosed_small_air_components': 0, 'enclosed_small_air_blocks': 0,
             'source_lava_with_air_below': 0, 'hanging_source_lava_shelf_candidates': 0,
             'r15_original_owner_micro_components': 0, 'r15_original_owner_micro_blocks': 0},
             'enclosed_air_samples': [], 'source_lava_air_below_samples': [], 'hanging_lava_shelf_samples': [],
             'samples_truncated': {'enclosed_air': False, 'lava_air_below': False, 'hanging_lava_shelf': False}}
    summary = {'schema': 1, 'seed': GATE.SEED, 'chunk_count': 50, 'full_chunks': 50,
               'roof_y': 512, 'roof_cells_checked': 12800, 'roof512_pass': True, 'roof_failures': [],
               'padding_y': [513, 527], 'padding_non_air': 0, 'natural_integrity_runtime_pass': True,
               'source_lava_with_air_below': 0, 'hanging_source_lava_shelf_candidates': 0}
    return plan, audit, summary


def add_cavity(audit, point=(-85, 120, 12), high=None, provenance=None):
    high = point if high is None else high
    size = high[1]-point[1]+1
    provenance = {'original': size} if provenance is None else provenance
    edge = any(point[i]//16 != high[i]//16 or point[i] % 16 == 0 or high[i] % 16 == 15 for i in (0, 2))
    original = provenance == {'original': size}
    audit['enclosed_air_samples'].append({'size': size, 'sample': list(point), 'bbox': list(point)+list(high),
                                         'provenance_counts': provenance, 'original_only': original,
                                         'touches_owner_chunk_boundary': edge})
    audit['counts']['enclosed_small_air_components'] += 1
    audit['counts']['enclosed_small_air_blocks'] += size
    if original and not edge:
        audit['counts']['r15_original_owner_micro_components'] += 1
        audit['counts']['r15_original_owner_micro_blocks'] += size


class AcceptanceTests(unittest.TestCase):
    def test_valid_sample_is_not_production_acceptance(self):
        result = GATE.evaluate(*fixture())
        self.assertTrue(result['nether_field_acceptance_pass'])
        self.assertIs(result['production_ready'], False)

    def test_original_body_cavity_fails(self):
        p, a, s = fixture(); add_cavity(a)
        self.assertFalse(GATE.evaluate(p, a, s)['nether_field_acceptance_pass'])

    def test_roof_envelope_is_visible_not_body_failure(self):
        p, a, s = fixture(); add_cavity(a, (-85, 510, 12))
        result = GATE.evaluate(p, a, s)
        self.assertTrue(result['nether_field_acceptance_pass'])
        self.assertEqual(result['roof_envelope_micro_components'], 1)

    def test_mixed_body_and_roof_cavity_fails(self):
        p, a, s = fixture(); add_cavity(a, (-85, 506, 12), (-85, 507, 12))
        self.assertFalse(GATE.evaluate(p, a, s)['nether_field_acceptance_pass'])

    def test_chunk_edge_cavity_is_reported(self):
        p, a, s = fixture(); add_cavity(a, (-96, 120, 12))
        result = GATE.evaluate(p, a, s)
        self.assertTrue(result['nether_field_acceptance_pass'])
        self.assertEqual(result['chunk_edge_micro_components'], 1)

    def test_unknown_body_provenance_fails(self):
        p, a, s = fixture(); add_cavity(a, provenance={'unrecorded': 1})
        self.assertFalse(GATE.evaluate(p, a, s)['nether_field_acceptance_pass'])

    def test_external_body_air_is_not_claimed_as_original(self):
        p, a, s = fixture(); add_cavity(a, provenance={'external': 1})
        self.assertTrue(GATE.evaluate(p, a, s)['nether_field_acceptance_pass'])

    def test_hanging_lava_fails_even_with_runtime_green(self):
        p, a, s = fixture()
        for key, sample_key in (('source_lava_with_air_below', 'source_lava_air_below_samples'),
                                ('hanging_source_lava_shelf_candidates', 'hanging_lava_shelf_samples')):
            a['counts'][key] = s[key] = 1; a[sample_key] = [{'position': [-3109, 10, -6289]}]
        self.assertFalse(GATE.evaluate(p, a, s)['nether_field_acceptance_pass'])

    def test_truncation_and_omission_are_not_success(self):
        for key in ('enclosed_air', 'lava_air_below', 'hanging_lava_shelf'):
            for value in (True, None, 'false'):
                with self.subTest(key=key, value=value):
                    p, a, s = fixture(); a['samples_truncated'][key] = value
                    with self.assertRaises(ValueError): GATE.evaluate(p, a, s)

    def test_incomplete_coverage_rejected(self):
        for field, value in (('full_chunks', 49), ('roof_cells_checked', 12799), ('padding_non_air', 1),
                              ('roof_y', 511), ('roof512_pass', False), ('natural_integrity_runtime_pass', 'true')):
            with self.subTest(field=field):
                p, a, s = fixture(); s[field] = value
                with self.assertRaises(ValueError): GATE.evaluate(p, a, s)

    def test_seed_types_and_normal_stop(self):
        for field, value in (('seed', str(GATE.SEED)), ('seed', 0), ('process_exit_code', True),
                             ('normal_stop', False), ('schema', True), ('chunk_count', '50')):
            p, a, s = fixture(); p[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): GATE.evaluate(p, a, s)

    def test_duplicate_and_different_chunk_sets(self):
        for replacement in ([0, 0], None):
            p, a, s = fixture(); a['chunks'][0] = a['chunks'][1] if replacement is None else replacement
            with self.assertRaises(ValueError): GATE.evaluate(p, a, s)

    def test_sample_count_and_provenance_must_be_complete(self):
        p, a, s = fixture(); add_cavity(a)
        for key, value in (('enclosed_small_air_components', 2), ('enclosed_small_air_blocks', 2),
                           ('r15_original_owner_micro_components', 0)):
            candidate = copy.deepcopy(a); candidate['counts'][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): GATE.evaluate(p, candidate, s)
        a['enclosed_air_samples'][0]['provenance_counts'] = {}
        with self.assertRaises(ValueError): GATE.evaluate(p, a, s)

    def test_large_bbox_does_not_trigger_unbounded_scan(self):
        p, a, s = fixture(); add_cavity(a); a['enclosed_air_samples'][0]['bbox'][3] = 10**20
        with self.assertRaises(ValueError): GATE.evaluate(p, a, s)

    def test_input_documents_unchanged(self):
        docs = fixture(); before = copy.deepcopy(docs); GATE.evaluate(*docs)
        self.assertEqual(docs, before)

    def test_duplicate_json_key_is_rejected(self):
        with self.assertRaises(ValueError): GATE.json_bytes(b'{"schema":1,"schema":2}')

    def test_saved_locks_are_required_and_never_rewritten(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name, value in (('.neverfolia-nevernether-height.lock', GATE.HEIGHT),
                                ('.neverfolia-nevernether-native.lock', GATE.NATIVE)):
                (root/name).write_text(value+'\n')
            GATE.verify_locks(root)
            native = root/'.neverfolia-nevernether-native.lock'
            for value in ('', 'OLD\n', 'X'*257):
                native.write_text(value)
                with self.assertRaises(ValueError): GATE.verify_locks(root)
                self.assertEqual(native.read_text(), value)
            native.unlink(); native.symlink_to(root/'.neverfolia-nevernether-height.lock')
            with self.assertRaises(ValueError): GATE.verify_locks(root)
            self.assertTrue(native.is_symlink())

    def test_test_bundle_checksums_and_create_only_output(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with zipfile.ZipFile(root/'server.jar', 'w') as archive:
                archive.writestr('META-INF/MANIFEST.MF', 'Synthetic test fixture only')
            marker = {'schema': 1, 'profile': GATE.NATIVE, 'requires_height_profile': GATE.HEIGHT,
                      'new_world_required': True}
            fingerprint = {'content_sha256': 'a'*64}
            with zipfile.ZipFile(root/'NeverNether-R15-FieldR1.zip', 'w') as archive:
                archive.writestr(GATE.MARKER, json.dumps(marker))
                archive.writestr('nevernether-worldgen-fingerprint.json', json.dumps(fingerprint))
            (root/'r15-pack-build.json').write_text(json.dumps(fingerprint))
            report = GATE.evaluate(*fixture())
            bundle = GATE.package(root, report, 'b'*40)
            digest = GATE.sha256(bundle)
            with zipfile.ZipFile(bundle) as archive:
                info = json.loads(archive.read('BUILD-INFO.json'))
                self.assertFalse(info['production_ready'])
                for line in archive.read('SHA256SUMS.txt').decode().splitlines():
                    expected, name = line.split('  ', 1)
                    self.assertEqual(hashlib.sha256(archive.read(name)).hexdigest(), expected)
            with self.assertRaises(FileExistsError): GATE.package(root, report, 'b'*40)
            self.assertEqual(GATE.sha256(bundle), digest)
            with self.assertRaises(ValueError): GATE.package(root, {'nether_field_acceptance_pass': False}, 'c'*40)
            self.assertFalse((root/f'NeverFolia-R15-TEST-{"c"*7}.zip').exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
