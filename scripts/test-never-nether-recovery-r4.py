#!/usr/bin/env python3
"""Authored-template contracts; NOT a Minecraft placement/registry test."""
import copy
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
from types import SimpleNamespace
import unittest

from nevernether_recovery_templates import (AIR, PREFIX, STONE, Template, apply_recoveries,
                                          decoration, encode, generated, nbt)
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('recovery_nbt', ROOT / 'scripts/hash-never-nether-chunks.py')
DECODER = importlib.util.module_from_spec(spec); spec.loader.exec_module(DECODER)


class RecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.templates = generated(5000)
        cls.values = {k: v.value() for k, v in cls.templates.items()}
        cls.encoded = {k: encode(v) for k, v in cls.values.items()}

    def test_exact_four_missing_resource_ids(self):
        self.assertEqual(set(self.templates), {
            'donjon/coloseum_part/deco_14', 'donjon/coloseum_part/deco_15',
            'donjon/room/donjon_room_3x3x3_1',
            'piglin_outstation/main/piglin_outpost_outer_layer_foundation_1'})

    def test_all_authored_nbt_roundtrips(self):
        for name, value in self.values.items():
            with self.subTest(name=name):
                self.assertEqual(DECODER.parse_nbt(gzip.decompress(self.encoded[name])), value)

    def test_all_positions_and_palette_indices_in_bounds(self):
        for v in self.values.values():
            positions = set()
            for b in v['blocks']:
                self.assertNotIn(tuple(b['pos']), positions); positions.add(tuple(b['pos']))
                self.assertTrue(all(0 <= p < s for p, s in zip(b['pos'], v['size'])))
                self.assertTrue(0 <= b['state'] < len(v['palette']))
            self.assertEqual(len(positions), v['size'][0] * v['size'][1] * v['size'][2])

    def test_decoration_variants_are_not_duplicate_or_empty(self):
        a, b = (self.encoded[f'donjon/coloseum_part/deco_{n}'] for n in (14, 15))
        self.assertNotEqual(a, b)
        for n in (14, 15):
            t = self.templates[f'donjon/coloseum_part/deco_{n}']
            self.assertEqual(t.size, (4, 4, 4))
            self.assertGreater(sum(st['Name'] != AIR for st, _ in t.blocks.values()), 20)

    def test_decor_attachment_ports_match_observed_contract(self):
        expected = {((0, 0, 0), 'down_south'), ((0, 0, 3), 'down_east'),
                    ((3, 0, 0), 'down_west'), ((3, 0, 3), 'down_north')}
        for n in (14, 15):
            t = self.templates[f'donjon/coloseum_part/deco_{n}']
            found = set()
            for p, (state, data) in t.blocks.items():
                if state['Name'] != 'minecraft:jigsaw': continue
                self.assertEqual(data['name'], 'nova_structures:deco')
                self.assertEqual(data['pool'], 'minecraft:empty')
                found.add((p, state['Properties']['orientation']))
            self.assertEqual(found, expected)

    def test_no_lava_water_mod_blocks_or_embedded_commands(self):
        for value in self.values.values():
            for state in value['palette']:
                self.assertTrue(state['Name'].startswith('minecraft:'))
                self.assertNotIn(state['Name'], {'minecraft:lava', 'minecraft:water', 'minecraft:command_block'})
            self.assertNotIn('Command', json.dumps(value))

    def test_hall_envelope_and_attachment(self):
        t = self.templates['donjon/room/donjon_room_3x3x3_1']
        self.assertEqual(t.size, (46, 21, 46))
        state, data = t.blocks[(45, 0, 45)]
        self.assertEqual(state['Properties']['orientation'], 'south_up')
        self.assertEqual(data['name'], 'nova_structures:donjon_room_3x3x3')
        self.assertEqual(data['pool'], 'minecraft:empty')

    def test_hall_ladders_have_backing_and_floor_exits(self):
        t = self.templates['donjon/room/donjon_room_3x3x3_1']
        for z in (4, 41):
            for y in range(1, 20):
                self.assertEqual(t.blocks[(1, y, z)][0]['Name'], 'minecraft:ladder')
                self.assertEqual(t.blocks[(0, y, z)][0]['Name'], STONE)
            for y in (0, 7, 14):
                self.assertEqual(t.blocks[(2, y, z)][0]['Name'], STONE)
                self.assertEqual(t.blocks[(2, y + 1, z)][0]['Name'], AIR)
                self.assertEqual(t.blocks[(2, y + 2, z)][0]['Name'], AIR)

    def test_hall_preserves_chest_and_mob_hooks(self):
        t = self.templates['donjon/room/donjon_room_3x3x3_1']
        pools = [d['pool'] for _, d in t.blocks.values() if d]
        self.assertEqual(pools.count('nova_structures:donjon/donjon_chest'), 2)
        self.assertEqual(pools.count('nova_structures:donjon/donjon_mob'), 4)

    def test_foundation_attachment_and_two_continuations(self):
        t = self.templates['piglin_outstation/main/piglin_outpost_outer_layer_foundation_1']
        self.assertEqual(t.size, (22, 42, 48))
        state, port = t.blocks[(0, 28, 47)]
        self.assertEqual(state['Properties']['orientation'], 'west_up')
        self.assertEqual(port['name'], 'nova_structures:outstation_outer_layer')
        for z, i in ((41, 1), (42, 2)):
            state, port = t.blocks[(21, 0, z)]
            self.assertEqual(port['target'], f'nova_structures:outstation_netherrack_layer_{i}')
            self.assertEqual(port['pool'], 'nova_structures:piglin_outstation/outer_layer')

    def test_foundation_has_no_air_inside_support_mass(self):
        t = self.templates['piglin_outstation/main/piglin_outpost_outer_layer_foundation_1']
        for (x, y, z), (state, _) in t.blocks.items():
            if y <= 28: self.assertNotEqual(state['Name'], AIR)

    def test_stable_output_bytes_and_zero_gzip_timestamp(self):
        for name, value in self.values.items():
            self.assertEqual(encode(value), self.encoded[name])
            self.assertEqual(self.encoded[name][4:8], b'\0\0\0\0')

    def stub(self):
        path = PurePosixPath('data/test/structure/contract.nbt')
        payload = b'contract test bytes'
        a = SimpleNamespace(sha256='test-sha', entries={path: payload}, provenance={},
                            compatibility_changes=[], dependency_cache={'old': True},
                            decode=lambda p: {'DataVersion': 5000})
        profile = {'source_sha256': 'test-sha', 'contract_inputs': {str(path): hashlib.sha256(payload).hexdigest()}}
        return a, profile

    def test_new_resources_only_and_dormant_room_disclosed(self):
        a, profile = self.stub(); before = dict(a.entries)
        apply_recoveries(a, profile)
        for key, data in before.items(): self.assertEqual(a.entries[key], data)
        self.assertEqual(len(a.entries), 5)
        self.assertEqual(len(a.compatibility_changes), 4)
        self.assertTrue(all(not v['upstream_original'] and not v['runtime_validated'] for v in a.compatibility_changes))
        self.assertEqual(sum(v['natural_consumer'] == 'not_present_in_supplied_frames' for v in a.compatibility_changes), 1)
        self.assertFalse(a.dependency_cache)

    def test_bad_source_hash_cannot_mutate(self):
        a, profile = self.stub(); before = dict(a.entries); a.sha256 = 'changed'
        with self.assertRaises(ValueError): apply_recoveries(a, profile)
        self.assertEqual(a.entries, before); self.assertEqual(a.compatibility_changes, [])

    def test_bad_contract_hash_cannot_mutate(self):
        a, profile = self.stub(); before = dict(a.entries)
        profile['contract_inputs'][next(iter(profile['contract_inputs']))] = '0' * 64
        with self.assertRaises(ValueError): apply_recoveries(a, profile)
        self.assertEqual(a.entries, before)

    def test_existing_last_destination_rejects_entire_batch(self):
        a, profile = self.stub()
        a.entries[PurePosixPath(PREFIX + 'piglin_outstation/main/piglin_outpost_outer_layer_foundation_1.nbt')] = b'keep original'
        before = dict(a.entries)
        with self.assertRaises(ValueError): apply_recoveries(a, profile)
        self.assertEqual(a.entries, before); self.assertEqual(a.compatibility_changes, [])

    def test_writer_does_not_guess_unsupported_numeric_tags(self):
        for value in (1.0, True, b'bytes', None):
            with self.subTest(value=value), self.assertRaises(ValueError): nbt(value)

    def test_writer_rejects_mixed_list(self):
        with self.assertRaises(ValueError): nbt([1, 'text'])

    def test_bad_dimensions_version_or_coordinates_fail(self):
        for size in ((0, 1, 1), (129, 1, 1), (1, 1, -1)):
            with self.assertRaises(ValueError): Template(size, 5000)
        with self.assertRaises(ValueError): Template((1, 1, 1), 0)
        t = Template((1, 1, 1), 5000)
        with self.assertRaises(ValueError): t.block(1, 0, 0, AIR)
        with self.assertRaises(ValueError): t.box((1, 0, 0), (0, 0, 0), AIR)
        with self.assertRaises(ValueError): decoration(5000, 16)


if __name__ == '__main__': unittest.main(verbosity=2)
