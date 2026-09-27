#!/usr/bin/env python3
"""Build a small last-priority overlay for ONE exact R38 candidate.

Only three reviewed template IDs and terminal pool fields in two templates change.
This is not a general missing-resource replacement or a terrain/water rewrite.
The original pack and its fingerprint stay untouched. Runtime acceptance is separate.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
import zipfile

SOURCE_SHA256 = '32ea5160f0bed3a80cf400c907622c7dbb76a9bb4160e309cacb5d712a8bd9f7'
FIXES = {
    'nova_structures:conduit_ruin/road/conduit_ruin_road_cruve_1': (
        'nova_structures:conduit_ruin/road/conduit_ruin_road_curve_1',
        'a84e7e8ac26a833647ebdcb867bc839c4fea86e1c5a8a6f3a4c34d42a143f92d'),
    'nova_structures:conduit_ruin/road/conduit_ruin_road_cruve_2': (
        'nova_structures:conduit_ruin/road/conduit_ruin_road_curve_2',
        '90666aab079ee4f57ba2611e26d76f081a698b17305d47112839ea1443141116'),
    'nova_structures:trident_trials_monument/small_monument/room_parts/small_monument_oof_wall4': (
        'nova_structures:trident_trials_monument/small_monument/room_parts/small_monument_roof_wall4',
        '555f8439031ef5088bd178ab993df62c1f0dcd0bd800b759312705746e37b0e6'),
}
JSON_PATHS = (
    'data/nova_structures/worldgen/template_pool/conduit_ruin/road.json',
    'data/nova_structures/worldgen/template_pool/trident_monument/small/room_parts.json',
)
NBT_PATHS = tuple('data/nova_structures/structure/conduit_ruin/house/conduit_ruin_house_b_' + str(n) + '.nbt' for n in (3,4))
TERMINAL_OLD, TERMINAL_NEW = 'minecraft:minecraft_empty', 'minecraft:empty'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def builder_module():
    path = Path(__file__).with_name('build-never-overworld-external-structures-r19.py')
    spec = importlib.util.spec_from_file_location('r39_repair_nbt', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def rewrite_locations(data, replacements):
    """Only location fields of known single-template elements, not arbitrary strings."""
    result = copy.deepcopy(data)
    events = []
    def visit(value, path):
        if isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, path + [index])
        elif isinstance(value, dict):
            if value.get('element_type') in ('minecraft:single_pool_element','minecraft:legacy_single_pool_element'):
                old = value.get('location')
                if old in replacements:
                    value['location'] = replacements[old]
                    events.append({'path': path + ['location'], 'old': old, 'new': replacements[old]})
            for key, child in value.items():
                visit(child, path + [key])
    visit(result, [])
    restored = copy.deepcopy(result)
    for event in events:
        parent = restored
        for key in event['path'][:-1]:parent = parent[key]
        parent[event['path'][-1]] = event['old']
    if restored != data:
        raise ValueError('An unapproved JSON field was modified')
    return result, events


def rewrite_terminal_pool(root):
    """NBT block positions, palettes, entities and all non-pool tags stay identical."""
    changed = copy.deepcopy(root)
    indexes = []
    blocks = changed.get('blocks', (9,(10,[])))[1][1]
    for index, block in enumerate(blocks):
        nbt = block.get('nbt', (10,{}))[1]
        if nbt.get('pool') == (8, TERMINAL_OLD):
            nbt['pool'] = (8, TERMINAL_NEW)
            indexes.append(index)
    restored = copy.deepcopy(changed)
    for index in indexes:
        restored['blocks'][1][1][index]['nbt'][1]['pool'] = (8, TERMINAL_OLD)
    if restored != root:
        raise ValueError('An unapproved NBT field was modified')
    return changed, indexes


def build_overlay(source, output):
    source, output = Path(source), Path(output)
    raw = source.read_bytes()
    if digest(raw) != SOURCE_SHA256:
        raise ValueError('Source is not the exact c6e522c R38 pack; no output written')
    if output.exists():
        raise FileExistsError('Refusing to overwrite ' + str(output))
    builder = builder_module()
    files, changes = {}, []
    with zipfile.ZipFile(io.BytesIO(raw)) as original:
        if len(original.namelist()) != len(set(original.namelist())):
            raise ValueError('Duplicate source ZIP members')
        if original.testzip() is not None:
            raise ValueError('Invalid source ZIP CRC')
        metadata = json.loads(original.read('pack.mcmeta'))
        if metadata.get('overlays') or metadata.get('filter'):
            raise ValueError('Unsupported source pack overlay/filter')
        meta = {'pack': copy.deepcopy(metadata['pack'])}
        meta['pack']['description'] = 'NeverFolia R39: targeted reference fixes; exact R38 base required'
        files['pack.mcmeta'] = (json.dumps(meta,indent=2) + '\n').encode()
        counts = {key:0 for key in FIXES}
        for old,(target,expected_hash) in FIXES.items():
            ns,path = target.split(':',1)
            payload = original.read(f'data/{ns}/structure/{path}.nbt')
            if digest(payload) != expected_hash:
                raise ValueError('Reviewed target changed: ' + target)
        for path in JSON_PATHS:
            before = original.read(path)
            after, events = rewrite_locations(json.loads(before), {k:v[0] for k,v in FIXES.items()})
            if not events:
                raise ValueError('Expected reference repair absent in ' + path)
            payload = (json.dumps(after,indent=2,ensure_ascii=False) + '\n').encode()
            if json.loads(payload) != after:
                raise ValueError('JSON round trip failed')
            files[path] = payload
            for event in events:counts[event['old']] += 1
            changes.append({'path':path,'source_sha256':digest(before),'output_sha256':digest(payload),'fields':events})
        if any(value != 1 for value in counts.values()):
            raise ValueError('Expected exactly one occurrence per reviewed template reference: ' + str(counts))
        for path in NBT_PATHS:
            before = original.read(path)
            compression,name,root = builder._nbt_parse(before)
            changed,indexes = rewrite_terminal_pool(root)
            if not indexes:
                raise ValueError('Expected bad terminal pool absent in ' + path)
            payload = builder._nbt_encode(compression,name,changed)
            if builder._nbt_parse(payload) != (compression,name,changed):
                raise ValueError('NBT round trip failed in ' + path)
            files[path] = payload
            changes.append({'path':path,'source_sha256':digest(before),'output_sha256':digest(payload),
                            'pool_block_indexes':indexes,'old':TERMINAL_OLD,'new':TERMINAL_NEW,
                            'all_other_typed_nbt_identical':True})
    report = {'schema':1,'source_pack_sha256':SOURCE_SHA256,'template_reference_count':sum(counts.values()),
              'changed_resource_files':len(changes),'changes':changes,
              'target_templates_byte_identical':{v[0]:v[1] for v in FIXES.values()},
              'runtime_tested':False,'release_accepted':False,
              'scope':'Reference-only last-priority overlay; no baseline pack, engine, block palette, entity, loot, spawner or saved world mutation'}
    output.parent.mkdir(parents=True,exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=output.parent,prefix='.r39-',suffix='.zip',delete=False) as stream:
            temporary = Path(stream.name)
        with zipfile.ZipFile(temporary,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
            for path,payload in sorted(files.items()):
                info = zipfile.ZipInfo(path,date_time=(1980,1,1,0,0,0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                z.writestr(info,payload)
        with zipfile.ZipFile(temporary) as z:
            if z.testzip() is not None or set(z.namelist()) != set(files):
                raise ValueError('Invalid output ZIP')
            if any(z.read(path) != payload for path,payload in files.items()):
                raise ValueError('Output payload mismatch')
        if digest(source.read_bytes()) != SOURCE_SHA256:
            raise ValueError('Source changed during operation')
        report['overlay_sha256'] = digest(temporary.read_bytes())
        # Exclusive publication: unlike replace(), this cannot clobber a new target.
        os.link(temporary,output)
    finally:
        if temporary is not None:temporary.unlink(missing_ok=True)
    return report


class Regression(unittest.TestCase):
    def test_only_single_location_fields(self):
        src={'element_type':'minecraft:single_pool_element','location':'old','other':'old','weight':7}
        changed,events=rewrite_locations(src,{'old':'new'})
        self.assertEqual(changed,{**src,'location':'new'});self.assertEqual(len(events),1)
        self.assertEqual(src['location'],'old')

    def test_no_arbitrary_string_replacement(self):
        src={'location':'old','feature':'old','values':['old']}
        self.assertEqual(rewrite_locations(src,{'old':'new'}),(src,[]))

    def test_nested_legacy_list(self):
        src={'elements':[{'element':{'element_type':'minecraft:legacy_single_pool_element','location':'old'},'weight':2}]}
        changed,events=rewrite_locations(src,{'old':'new'})
        self.assertEqual(changed['elements'][0]['weight'],2);self.assertEqual(len(events),1)

    def test_unknown_location_untouched(self):
        src={'element_type':'minecraft:single_pool_element','location':'unknown'}
        self.assertEqual(rewrite_locations(src,{'old':'new'}),(src,[]))

    def sample(self):
        return {'blocks':(9,(10,[{'pos':(9,(3,[1,2,3])),'state':(3,0),'nbt':(10,{'pool':(8,TERMINAL_OLD),'target':(8,'kept')})}])),
                'entities':(9,(10,[{'id':(8,'minecraft:painting')}])),'palette':(9,(10,[{'Name':(8,'minecraft:jigsaw')}])),
                'untouched':(8,TERMINAL_OLD)}

    def test_nbt_field_only(self):
        root=self.sample();changed,indexes=rewrite_terminal_pool(root)
        self.assertEqual(indexes,[0]);self.assertEqual(changed['entities'],root['entities'])
        self.assertEqual(changed['palette'],root['palette']);self.assertEqual(changed['untouched'],root['untouched'])
        self.assertEqual(root['blocks'][1][1][0]['nbt'][1]['pool'],(8,TERMINAL_OLD))

    def test_existing_terminal_not_changed(self):
        root=self.sample();root['blocks'][1][1][0]['nbt'][1]['pool']=(8,TERMINAL_NEW)
        self.assertEqual(rewrite_terminal_pool(root),(root,[]))

    def test_nbt_three_compression_roundtrips(self):
        builder=builder_module();changed,_=rewrite_terminal_pool(self.sample())
        for compression in ('raw','gzip','zlib'):
            self.assertEqual(builder._nbt_parse(builder._nbt_encode(compression,'',changed)),(compression,'',changed))

    def test_unknown_source_creates_no_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            src=Path(tmp)/'source.zip';out=Path(tmp)/'out.zip';src.write_bytes(b'unknown')
            with self.assertRaises(ValueError):build_overlay(src,out)
            self.assertFalse(out.exists());self.assertEqual(src.read_bytes(),b'unknown')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--self-test',action='store_true')
    p.add_argument('--pack',type=Path);p.add_argument('--output',type=Path);p.add_argument('--report',type=Path)
    a=p.parse_args()
    if a.self_test:
        result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Regression))
        return 0 if result.wasSuccessful() else 1
    if not all((a.pack,a.output,a.report)):
        p.error('--pack, --output and --report are required')
    report=build_overlay(a.pack,a.output)
    a.report.parent.mkdir(parents=True,exist_ok=True)
    a.report.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    return 0


if __name__=='__main__':raise SystemExit(main())
