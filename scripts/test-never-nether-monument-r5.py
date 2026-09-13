#!/usr/bin/env python3
"""Synthetic, payload-free conversion regressions; not world-generation tests."""
from __future__ import annotations
import copy
import hashlib
import json
from pathlib import Path, PurePosixPath
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import nevernether_monument_r5 as mod


def fixture():
    return {'processors': [
        {'processor_type': key, **({'input_block': 'minecraft:red_nether_bricks',
        'output_block': 'minecraft:nether_bricks', 'probability': 0.25} if 'random' in key else {})}
        for key in mod.PROCESSORS], 'elements': [{'weight': 3, 'element': {
        'element_type': mod.ELEMENT[0], 'name': 'room', 'max_count': 1,
        'location': 'test:room', 'processors': 'test:processors', 'projection': 'rigid'}}]}


class MonumentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        raw = (json.dumps(fixture()) + '\n').encode()
        key = PurePosixPath('data/test/worldgen/template_pool/start.json')
        self.archive = SimpleNamespace(sha256=mod.SOURCE_SHA, entries={key: raw}, decoded={},
            provenance={key: str(key)}, dependency_cache={'old': 'entry'}, native_codecs=set(),
            supplemental_notices={}, compatibility_changes=[])
        self.profile = {'source_sha256': mod.SOURCE_SHA,
            'contract_hashes': {str(key): hashlib.sha256(raw).hexdigest()},
            'expected_translations': {**{k: 1 for k in mod.PROCESSORS}, mod.ELEMENT[0]: 1},
            'supplemental_files': []}
        for name, target, raw in [('nether.json', 'data/test/loot_table/nether.json', b'{"type":"minecraft:chest","pools":[]}'),
                                 ('LICENSE.txt', 'licenses/test.txt', b'Synthetic license fixture only.\n')]:
            (self.root / name).write_bytes(raw)
            self.profile['supplemental_files'].append({'filename': name, 'git_blob': mod.blob_hash(raw), 'pack_path': target})
        self.profile_path = self.root / 'profile.json'; self.save()
        self.patcher = patch.object(mod, 'PROFILE', self.profile_path); self.patcher.start()
    def tearDown(self):
        self.patcher.stop(); self.tmp.cleanup()
    def save(self): self.profile_path.write_text(json.dumps(self.profile))
    def apply(self): mod.apply_monument(self.archive, self.root)
    def atomic_failure(self):
        before = copy.deepcopy(vars(self.archive))
        with self.assertRaises(ValueError): self.apply()
        self.assertEqual(vars(self.archive), before)
    def test_types_translate_without_other_changes(self):
        obj = fixture(); before = copy.deepcopy(obj); result, counts = mod.translate(obj)
        self.assertEqual(obj, before); self.assertEqual(counts, self.profile['expected_translations'])
        reverse = {v: k for k, v in mod.PROCESSORS.items()}
        for entry in result['processors']: entry['processor_type'] = reverse[entry['processor_type']]
        result['elements'][0]['element']['element_type'] = mod.ELEMENT[0]
        self.assertEqual(result, before)
    def test_vanilla_order_unchanged(self):
        obj = {'processors': [{'processor_type': 'minecraft:ignore', 'blocks': ['minecraft:air']}, {'processor_type': 'minecraft:rule', 'rules': []}]}
        self.assertEqual(mod.translate(obj), (obj, {}))
    def test_unknown_processor_rejected(self):
        with self.assertRaises(ValueError): mod.translate({'processor_type': 'mod:other'})
    def test_unknown_element_rejected(self):
        with self.assertRaises(ValueError): mod.translate({'element_type': 'mod:other'})
    def test_random_multi_output_rejected(self):
        p = fixture()['processors'][1]; p['output_blocks'] = ['minecraft:air']
        with self.assertRaises(ValueError): mod.translate(p)
    def test_random_missing_output_rejected(self):
        p = fixture()['processors'][1]; del p['output_block']
        with self.assertRaises(ValueError): mod.translate(p)
    def test_horizontal_pillar_rejected(self):
        with self.assertRaises(ValueError): mod.translate({'processor_type': 'repurposed_structures:pillar_processor', 'direction': 'east'})
    def test_forced_pillar_rejected(self):
        with self.assertRaises(ValueError): mod.translate({'processor_type': 'repurposed_structures:pillar_processor', 'forced_placement': True})
    def test_zero_quota_preserved(self):
        result, _ = mod.translate({'element_type': mod.ELEMENT[0], 'name': 'none', 'max_count': 0})
        self.assertEqual(result['max_count'], 0)
    def test_invalid_quota_rejected(self):
        for value in (-1, 1.2, True, '1'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                mod.translate({'element_type': mod.ELEMENT[0], 'name': 'group', 'max_count': value})
    def test_empty_quota_group_rejected(self):
        with self.assertRaises(ValueError): mod.translate({'element_type': mod.ELEMENT[0], 'name': '', 'max_count': 1})
    def test_exact_loot_and_scoped_codec_profile(self):
        self.apply()
        self.assertEqual(self.archive.entries[PurePosixPath('data/test/loot_table/nether.json')], (self.root/'nether.json').read_bytes())
        self.assertEqual(self.archive.native_codecs, mod.NATIVE_CODECS)
        self.assertFalse(self.archive.compatibility_changes[0]['runtime_validated'])
        self.assertEqual(self.archive.dependency_cache, {}); self.assertEqual(len(self.archive.supplemental_notices), 1)
    def test_wrong_archive_atomic(self):
        self.archive.sha256 = '0'*64; self.atomic_failure()
    def test_wrong_profile_atomic(self):
        self.profile['source_sha256'] = '0'*64; self.save(); self.atomic_failure()
    def test_changed_input_atomic(self):
        self.archive.entries[next(iter(self.archive.entries))] += b' '; self.atomic_failure()
    def test_wrong_inventory_atomic(self):
        self.profile['expected_translations'][mod.ELEMENT[0]] = 2; self.save(); self.atomic_failure()
    def test_missing_loot_atomic(self):
        (self.root/'nether.json').unlink(); self.atomic_failure()
    def test_corrupt_loot_atomic(self):
        (self.root/'nether.json').write_bytes(b'{}'); self.atomic_failure()
    def test_missing_license_atomic(self):
        (self.root/'LICENSE.txt').unlink(); self.atomic_failure()
    def test_existing_loot_not_overwritten(self):
        self.archive.entries[PurePosixPath('data/test/loot_table/nether.json')] = b'{}'; self.atomic_failure()
    def test_second_application_fails_closed(self):
        self.apply(); self.atomic_failure()
    def test_repeatability(self):
        before = copy.deepcopy(self.archive); self.apply(); first = copy.deepcopy(vars(self.archive))
        self.archive = before; self.apply(); self.assertEqual(first, vars(self.archive))
    def test_unsafe_supplemental_path_rejected(self):
        self.profile['supplemental_files'][0]['pack_path'] = '../out.json'; self.save(); self.atomic_failure()
    def test_duplicate_supplemental_path_rejected(self):
        self.profile['supplemental_files'].append(self.profile['supplemental_files'][0]); self.save(); self.atomic_failure()

class LegacyPatchTests(unittest.TestCase):
    @staticmethod
    def patch(tries=3, spread=1):
        return {'type':'minecraft:random_patch','config':{'tries':tries,'xz_spread':spread,'y_spread':0,
            'feature':{'feature':{'type':'minecraft:block_column','config':{}},
                       'placement':[{'type':'minecraft:random_offset','xz_spread':0,'y_spread':-1}]}}}
    def test_nested_feature_and_original_offset_preserved(self):
        obj=self.patch(); before=copy.deepcopy(obj); result=mod.convert_legacy_patch(obj)
        self.assertEqual(obj,before)
        child=result['config']['features'][0]
        self.assertEqual(child['feature'],obj['config']['feature']['feature'])
        self.assertEqual(child['placement'][-1],obj['config']['feature']['placement'][0])
        self.assertEqual(result['type'],'minecraft:sequence')
    def test_triangular_distribution_matches_two_unit_uniform_draws(self):
        child=mod.convert_legacy_patch(self.patch())['config']['features'][0]
        self.assertEqual(child['placement'][0],{'type':'minecraft:count','count':3})
        distribution=child['placement'][1]['xz_spread']['distribution']
        observed={x['data']:x['weight'] for x in distribution}
        from collections import Counter
        self.assertEqual(observed,dict(Counter(a-b for a in (0,1) for b in (0,1))))
    def test_fire_remains_one_attempt_no_horizontal_spread(self):
        child=mod.convert_legacy_patch(self.patch(1,0))['config']['features'][0]
        self.assertEqual(len(child['placement']),2)
        self.assertEqual(child['placement'][0]['count'],1)
    def test_unknown_profile_not_approximated(self):
        with self.assertRaises(ValueError):mod.convert_legacy_patch(self.patch(5,8))
    def test_extra_keys_not_silently_dropped(self):
        obj=self.patch();obj['config']['extra']=True
        with self.assertRaises(ValueError):mod.convert_legacy_patch(obj)


if __name__ == '__main__': unittest.main(verbosity=2)
