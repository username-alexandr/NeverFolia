#!/usr/bin/env python3
"""Synthetic regression fixtures; they are not replacement game assets."""
from __future__ import annotations
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
import warnings
import zipfile

import never_resource_stack as s

GRAPH = s.module(s.ROOT / 'audit-neveroverworld-r39-resources.py', 'stack_test_graph')
NBT = s.module(s.ROOT / 'build-never-overworld-external-structures-r19.py', 'stack_test_nbt')


def encoded(value):
    return json.dumps(value).encode()


def template(pool=None):
    block = {'state': (3, 0), 'pos': (9, (3, [0, 0, 0]))}
    if pool is not None:
        block['nbt'] = (10, {'pool': (8, pool)})
    return {'size': (9, (3, [1, 1, 1])),
            'palette': (9, (10, [{'Name': (8, 'minecraft:jigsaw' if pool is not None else 'minecraft:stone')}])),
            'blocks': (9, (10, [block])), 'entities': (9, (10, []))}


def nbt_bytes(root):
    return NBT._nbt_encode('gzip', '', root)


def pool(location):
    return encoded({'fallback': 'minecraft:empty', 'elements': [
        {'weight': 1, 'element': {'element_type': 'minecraft:single_pool_element', 'location': location}}]})


def base_files(location='test:room'):
    return {'data/minecraft/worldgen/template_pool/empty.json': encoded({'fallback': 'minecraft:empty', 'elements': []}),
            'data/test/worldgen/structure_set/main.json': encoded({'structures': [{'structure': 'test:main', 'weight': 1}]}),
            'data/test/worldgen/structure/main.json': encoded({'type': 'minecraft:jigsaw', 'start_pool': 'test:start'}),
            'data/test/worldgen/template_pool/start.json': pool(location)}


def graph_report(*layers):
    stack = s.ResourceStack()
    for ident, entries in layers:
        stack.add(ident, entries)
    return s.audit_resources(stack, GRAPH, NBT._nbt_parse)


def zipped(files):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, raw in files.items():
            z.writestr(name, raw)
    return stream.getvalue()


class StackTests(unittest.TestCase):
    def test_missing_template_can_be_provided_by_nether(self):
        before = graph_report(('vanilla', {}), ('file/Overworld.zip', base_files()))
        after = graph_report(('vanilla', {}), ('file/Overworld.zip', base_files()),
                             ('file/Nether.zip', {'data/test/structure/room.nbt': nbt_bytes(template())}))
        self.assertFalse(before['pass'])
        self.assertEqual(before['counts']['missing_templates'], 1)
        self.assertTrue(after['pass'])
        self.assertFalse(after['production_accepted'])
        self.assertEqual(after['resource_resolution']['non_tag_providers']['data/test/structure/room.nbt']['pack'], 'file/Nether.zip')

    def test_late_pool_override_can_undo_a_valid_repair(self):
        fixed = {**base_files(), 'data/test/structure/room.nbt': nbt_bytes(template())}
        broken = {'data/test/worldgen/template_pool/start.json': pool('test:absent')}
        wrong = graph_report(('vanilla', {}), ('file/Overworld.zip', fixed), ('file/Nether.zip', broken))
        reversed_order = graph_report(('vanilla', {}), ('file/Nether.zip', broken), ('file/Overworld.zip', fixed))
        self.assertFalse(wrong['pass'])
        self.assertTrue(reversed_order['pass'])
        self.assertEqual(wrong['missing'][0]['id'], 'test:absent')
        event = wrong['resource_resolution']['overrides'][0]
        self.assertTrue(event['bytes_changed'])
        self.assertEqual(event['previous']['pack'], 'file/Overworld.zip')
        self.assertEqual(event['winner']['pack'], 'file/Nether.zip')

    def test_identical_override_still_records_both_providers(self):
        stack = s.ResourceStack()
        for name in ('a', 'b'):
            stack.add(name, {'data/test/function/a.mcfunction': b'say example\n'})
        self.assertFalse(stack.overrides[0]['bytes_changed'])
        self.assertEqual(stack.providers['data/test/function/a.mcfunction']['pack'], 'b')

    def test_full_path_and_namespace_are_identity(self):
        stack = s.ResourceStack()
        stack.add('a', {'data/test/structure/a/room.nbt': b'a', 'data/test/structure/b/room.nbt': b'b',
                        'data/other/structure/a/room.nbt': b'c'})
        self.assertEqual(set(stack.indexes()['template']), {'test:a/room', 'test:b/room', 'other:a/room'})
        self.assertFalse(stack.overrides)

    def test_tag_contributions_are_not_misreported_as_last_winner(self):
        stack = s.ResourceStack()
        path = 'data/test/tags/function/load.json'
        stack.add('a', {path: encoded({'values': ['test:a']})})
        stack.add('b', {path: encoded({'values': ['test:b']})})
        self.assertNotIn(path, stack.files)
        self.assertNotIn(path, stack.providers)
        self.assertEqual([x['pack'] for x in stack.tag_contributors[path]], ['a', 'b'])

    def test_late_structure_set_controls_actual_roots(self):
        original = base_files()
        newer = {'data/test/worldgen/structure_set/main.json': encoded({'structures': [{'structure': 'test:other', 'weight': 1}]}),
                 'data/test/worldgen/structure/other.json': encoded({'type': 'minecraft:fortress'})}
        report = graph_report(('a', original), ('b', newer))
        self.assertEqual([r['id'] for r in report['roots']], ['test:other'])
        self.assertEqual(report['roots'][0]['provider']['pack'], 'b')

    def test_duplicate_pack_ids_fail(self):
        stack = s.ResourceStack()
        stack.add('a', {})
        with self.assertRaises(ValueError):
            stack.add('a', {})

    def test_no_roots_never_passes(self):
        report = graph_report(('vanilla', {}))
        self.assertFalse(report['pass'])
        self.assertFalse(report['audit_complete'])

    def test_alias_is_root_local_and_does_not_fix_missing_start_holder(self):
        files = base_files()
        files['data/test/worldgen/structure/main.json'] = encoded({
            'type': 'minecraft:jigsaw', 'start_pool': 'test:unavailable',
            'pool_aliases': [{'type': 'minecraft:direct', 'alias': 'test:unavailable', 'target': 'test:start'}]})
        report = graph_report(('a', files))
        self.assertFalse(report['pass'])
        self.assertIn('test:unavailable', {x['id'] for x in report['missing']})

    def test_omitted_jigsaw_entity_id_is_valid(self):
        self.assertEqual(s.jigsaw_pools(template('test:child')), ['test:child'])

    def test_non_jigsaw_pool_field_is_not_a_connector(self):
        root = template()
        root['blocks'][1][1][0]['nbt'] = (10, {'pool': (8, 'test:not_a_connector')})
        self.assertEqual(s.jigsaw_pools(root), [])

    def test_multi_palette_jigsaw_is_included(self):
        root = template('test:child')
        palette = root.pop('palette')[1]
        root['palettes'] = (9, (9, [palette, (10, [{'Name': (8, 'minecraft:stone')}])]))
        self.assertEqual(s.jigsaw_pools(root), ['test:child'])

    def test_bad_palette_index_is_reported_as_error_not_missing_pass(self):
        root = template('test:child')
        root['blocks'][1][1][0]['state'] = (3, 5)
        report = graph_report(('a', {**base_files(), 'data/test/structure/room.nbt': nbt_bytes(root)}))
        self.assertFalse(report['pass'])
        self.assertTrue(report['errors'])
        self.assertFalse(report['audit_complete'])

    def test_contradictory_jigsaw_id_fails(self):
        root = template('test:child')
        root['blocks'][1][1][0]['nbt'][1]['id'] = (8, 'minecraft:chest')
        with self.assertRaises(ValueError):
            s.jigsaw_pools(root)

    def test_valid_format(self):
        for fields in ({'pack_format': 107}, {'min_format': [107, 1], 'max_format': [107, 1]},
                       {'pack_format': 100, 'supported_formats': [100, 107]}):
            self.assertEqual(s.check_metadata(encoded({'pack': fields}))['pack'], fields)

    def test_unsupported_overlay_filter_or_version_fails(self):
        cases = [{'pack': {'pack_format': 107}, 'overlays': {}},
                 {'pack': {'pack_format': 107}, 'filter': {'block': []}},
                 {'pack': {'pack_format': 106}}, {'pack': {'pack_format': True}}]
        for case in cases:
            with self.subTest(case=case), self.assertRaises((ValueError, KeyError)):
                s.check_metadata(encoded(case))

    def test_duplicate_or_non_finite_json_fails(self):
        for raw in (b'{"a":1,"a":2}', b'{"a":NaN}'):
            with self.assertRaises(ValueError):
                s.decode_json(raw)

    def test_unsafe_and_nested_pack_paths_fail(self):
        for files in ({'../pack.mcmeta': b'{}'}, {'wrapper/pack.mcmeta': b'{}'},
                      {'pack.mcmeta': b'{}', 'data/test/../evil.json': b'{}'},
                      {'pack.mcmeta': b'{}', 'data//test/a.json': b'{}'}):
            with self.subTest(files=list(files)), self.assertRaises(ValueError):
                s.zip_entries(zipped(files), kind='pack')

    def test_duplicate_zip_members_fail(self):
        stream = io.BytesIO()
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            with zipfile.ZipFile(stream, 'w') as z:
                z.writestr('pack.mcmeta', b'{}')
                z.writestr('pack.mcmeta', b'{}')
        with self.assertRaises(ValueError):
            s.zip_entries(stream.getvalue(), kind='pack')

    def test_end_to_end_pinned_manifest_and_immutability(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            engine = zipped({'data/minecraft/worldgen/template_pool/empty.json': encoded({'fallback': 'minecraft:empty', 'elements': []})})
            payloads = [zipped({'META-INF/versions/26.2/folia-26.2.jar': engine}),
                        zipped({'pack.mcmeta': encoded({'pack': {'pack_format': 107}}), **base_files()}),
                        zipped({'pack.mcmeta': encoded({'pack': {'pack_format': 107}}), 'data/test/structure/room.nbt': nbt_bytes(template())})]
            records = []
            for i, raw in enumerate(payloads):
                path = root / str(i)
                path.write_bytes(raw)
                records.append({'path': str(path), 'sha256': s.digest(raw)})
            manifest = {'schema': 1, 'server': records[0], 'packs': [dict(records[1], id='file/Overworld.zip'), dict(records[2], id='file/Nether.zip')]}
            before = {p.name: p.read_bytes() for p in root.iterdir()}
            report = s.audit_manifest(manifest)
            self.assertTrue(report['pass'])
            self.assertTrue(report['inputs_unchanged'])
            self.assertEqual(report['resource_resolution']['order_low_to_high'], ['vanilla', 'file/Overworld.zip', 'file/Nether.zip'])
            self.assertEqual(before, {p.name: p.read_bytes() for p in root.iterdir()})
            wrong = copy.deepcopy(manifest)
            wrong['packs'][1]['sha256'] = '0' * 64
            with self.assertRaises(ValueError):
                s.audit_manifest(wrong)
            self.assertEqual(before, {p.name: p.read_bytes() for p in root.iterdir()})


if __name__ == '__main__':
    unittest.main(verbosity=2)
