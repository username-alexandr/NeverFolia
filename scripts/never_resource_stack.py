#!/usr/bin/env python3
"""Read-only, ordered resource audit for the pinned Folia 26.2 QA kit.

Manifest packs are in LOW-to-HIGH priority after bundled vanilla. Only flat
packs are accepted: overlays and filters fail explicitly, never disappear.
Non-tag resources use last-provider precedence. Tag contributions are recorded
but NOT merged or validated. The reused graph checks possible jigsaw references,
not geometry, commands, loot, codecs, biome eligibility or actual world generation.
No pack, world, fingerprint or kernel is modified by this program.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import json
from pathlib import Path, PurePosixPath
import re
import sys
import zipfile

ROOT = Path(__file__).resolve().parent
TARGET_FORMAT = (107, 1)
FAMILIES = {
    'pool': ('worldgen/template_pool', 'json'),
    'structure': ('worldgen/structure', 'json'),
    'set': ('worldgen/structure_set', 'json'),
    'template': ('structure', 'nbt'),
    'placed_feature': ('worldgen/placed_feature', 'json'),
}
LIMITS = {'pack': 256 * 1024 * 1024, 'server': 1024 * 1024 * 1024}


def need(ok, message):
    if not ok:
        raise ValueError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    loaded = importlib.util.module_from_spec(spec)
    sys.modules[name] = loaded
    spec.loader.exec_module(loaded)
    return loaded


def object_pairs(pairs):
    result = {}
    for key, value in pairs:
        need(key not in result, 'Duplicate JSON key: ' + key)
        result[key] = value
    return result


def decode_json(raw):
    def invalid(value):
        raise ValueError('Non-finite JSON constant: ' + value)
    return json.loads(raw, object_pairs_hook=object_pairs, parse_constant=invalid)


def version(value, upper=False):
    if type(value) is int and value >= 0:
        return value, 2147483647 if upper else 0
    if isinstance(value, list) and len(value) == 2 and all(type(x) is int and x >= 0 for x in value):
        return tuple(value)
    raise ValueError('Invalid pack version: ' + repr(value))


def check_metadata(raw, target=TARGET_FORMAT):
    meta = decode_json(raw)
    need(isinstance(meta, dict) and isinstance(meta.get('pack'), dict), 'Invalid pack.mcmeta')
    need('overlays' not in meta and 'filter' not in meta,
         'Pack overlays/filters need a separate resolver; refusing incomplete audit')
    pack = meta['pack']
    if 'min_format' in pack or 'max_format' in pack:
        lo, hi = version(pack['min_format']), version(pack['max_format'], True)
    else:
        value = pack.get('supported_formats', pack.get('pack_format'))
        if isinstance(value, dict):
            lo, hi = version(value['min_inclusive']), version(value['max_inclusive'], True)
        elif isinstance(value, list) and len(value) == 2:
            lo, hi = version(value[0]), version(value[1], True)
        else:
            lo, hi = version(value), version(value, True)
    need(lo <= tuple(target) <= hi, 'Pack does not support target format ' + repr(target))
    return meta


def zip_entries(raw, *, kind):
    """Read and CRC-check only root data and metadata, without extracting files."""
    result = {}
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        infos = z.infolist()
        need(len(infos) <= 200000, 'Too many ZIP entries')
        need(sum(i.file_size for i in infos) <= LIMITS[kind], 'ZIP uncompressed size limit exceeded')
        seen = set()
        for info in infos:
            name = info.filename
            need(name not in seen, 'Duplicate ZIP member: ' + name)
            seen.add(name)
            p = PurePosixPath(name)
            normalized = name[:-1] if info.is_dir() else name
            need(normalized and str(p) == normalized and not p.is_absolute()
                 and '..' not in p.parts and '\\' not in name and ':' not in name,
                 'Noncanonical or unsafe ZIP path: ' + name)
            need(not info.flag_bits & 1 and ((info.external_attr >> 16) & 0o170000) != 0o120000,
                 'Encrypted or symlink ZIP member: ' + name)
            if info.is_dir():
                continue
            selected = name.startswith('data/') or name in ('pack.mcmeta', 'version.json')
            if kind == 'server':
                selected = selected or (name.startswith('META-INF/versions/') and name.endswith('/folia-26.2.jar'))
            if selected:
                need(info.file_size <= (LIMITS['server'] if name.endswith('.jar') else 32 * 1024 * 1024),
                     'Resource exceeds size limit: ' + name)
                result[name] = z.read(info)
        if kind == 'pack':
            need('pack.mcmeta' in result, 'Only root-level flat datapacks are supported')
            need(sum(PurePosixPath(n).name == 'pack.mcmeta' for n in seen) == 1,
                 'Ambiguous pack.mcmeta locations')
    return result


def pinned_bytes(record, kind):
    need(isinstance(record, dict), 'Input record must be an object')
    expected = record.get('sha256')
    need(isinstance(expected, str) and re.fullmatch('[0-9a-f]{64}', expected), 'An exact SHA-256 is required')
    path = Path(record['path'])
    need(path.is_file() and not path.is_symlink(), 'Missing or symlink input: ' + str(path))
    need(path.stat().st_size <= LIMITS[kind], 'Input exceeds size limit: ' + str(path))
    raw = path.read_bytes()
    need(digest(raw) == expected, 'Input hash mismatch: ' + str(path))
    return raw


class ResourceStack:
    def __init__(self):
        self.files = {}
        self.providers = {}
        self.overrides = []
        self.tag_contributors = {}
        self.order = []

    def add(self, pack_id, entries):
        need(isinstance(pack_id, str) and pack_id and pack_id not in self.order, 'Duplicate/invalid pack id')
        self.order.append(pack_id)
        for name, raw in sorted(entries.items()):
            if not name.startswith('data/'):
                continue
            parts = PurePosixPath(name).parts
            need(len(parts) >= 4, 'Invalid data path: ' + name)
            provider = {'pack': pack_id, 'sha256': digest(raw)}
            if parts[2] == 'tags':
                self.tag_contributors.setdefault(name, []).append(provider)
                continue
            if name in self.files:
                self.overrides.append({'path': name, 'previous': self.providers[name],
                                       'winner': provider, 'bytes_changed': self.files[name] != raw})
            self.files[name] = raw
            self.providers[name] = provider

    def indexes(self):
        result = {}
        for kind, (family, extension) in FAMILIES.items():
            pattern = re.compile(r'data/([^/]+)/' + re.escape(family) + r'/(.+)\.' + extension)
            result[kind] = {m[1] + ':' + m[2]: path for path in sorted(self.files)
                            if (m := pattern.fullmatch(path))}
        return result


def jigsaw_pools(root):
    """Recognize jigsaws by block palette, including omitted block-entity IDs."""
    if 'palette' in root:
        need('palettes' not in root, 'Both palette and palettes present')
        palettes = [root['palette']]
    elif 'palettes' in root:
        tag = root['palettes']
        need(tag[0] == 9 and tag[1][0] == 9, 'Invalid palettes list')
        palettes = [(9, value) for value in tag[1][1]]
    else:
        raise ValueError('Template has no block palette')
    need(bool(palettes), 'Empty palettes list')
    need(all(p[0] == 9 and p[1][0] == 10 for p in palettes), 'Invalid typed palette')
    states = [p[1][1] for p in palettes]
    blocks = root.get('blocks')
    need(blocks is not None and blocks[0] == 9 and blocks[1][0] in (0, 10), 'Invalid blocks list')
    result = set()
    for block in blocks[1][1]:
        state = block.get('state')
        need(state is not None and state[0] == 3 and type(state[1]) is int
             and all(0 <= state[1] < len(p) for p in states), 'Invalid block palette index')
        if not any(p[state[1]].get('Name') == (8, 'minecraft:jigsaw') for p in states):
            continue
        tag = block.get('nbt')
        need(tag is not None and tag[0] == 10, 'Jigsaw has no block entity compound')
        entity = tag[1]
        need('id' not in entity or entity['id'] == (8, 'minecraft:jigsaw'), 'Contradictory jigsaw block entity id')
        pool = entity.get('pool')
        need(pool is not None and pool[0] == 8 and isinstance(pool[1], str), 'Jigsaw has no string pool')
        result.add(pool[1])
    return sorted(result)


def audit_resources(stack, graph, parse_nbt):
    indexes = stack.indexes()
    def load(kind, ident):
        raw = stack.files[indexes[kind][ident]]
        return jigsaw_pools(parse_nbt(raw)[2]) if kind == 'template' else decode_json(raw)
    report = graph.Audit(indexes, load).run()
    report['audit_complete'] = not report['errors']
    report['resource_index_counts'] = {kind: len(values) for kind, values in indexes.items()}
    for row in report['roots']:
        row['provider'] = stack.providers[indexes['structure'][row['id']]]
    report['resource_resolution'] = {
        'order_low_to_high': list(stack.order),
        'non_tag_providers': stack.providers,
        'overrides': stack.overrides,
        'tag_contributors_not_merged': stack.tag_contributors,
    }
    report['production_accepted'] = False
    report['runtime_tested_by_this_audit'] = False
    report['scope'] += ' Ordered non-tag files only; tag semantics, overlays and filters are not evaluated.'
    return report


def audit_manifest(manifest):
    need(isinstance(manifest, dict) and manifest.get('schema') == 1, 'Unknown stack manifest schema')
    packs = manifest.get('packs')
    need(isinstance(packs, list) and packs, 'Empty datapack stack is not accepted')
    ids = [p['id'] for p in packs]
    need(all(isinstance(x, str) and x.startswith('file/') for x in ids)
         and len(ids) == len(set(ids)), 'Invalid or duplicate file pack id')
    records = [manifest['server'], *packs]
    need(len({Path(r['path']).resolve() for r in records}) == len(records), 'Duplicate input file path')
    server_raw = pinned_bytes(manifest['server'], 'server')
    bundled = zip_entries(server_raw, kind='server')
    nested = [n for n in bundled if n.startswith('META-INF/versions/') and n.endswith('/folia-26.2.jar')]
    need(len(nested) == 1, 'Expected one pinned Folia 26.2 bundled server')
    engine_raw = bundled[nested[0]]
    vanilla = zip_entries(engine_raw, kind='server')
    stack = ResourceStack()
    stack.add('vanilla', vanilla)
    for record in packs:
        entries = zip_entries(pinned_bytes(record, 'pack'), kind='pack')
        check_metadata(entries['pack.mcmeta'])
        stack.add(record['id'], entries)
    graph = module(ROOT / 'audit-neveroverworld-r39-resources.py', 'stack_jigsaw_graph')
    nbt = module(ROOT / 'build-never-overworld-external-structures-r19.py', 'stack_nbt_codec')
    report = audit_resources(stack, graph, nbt._nbt_parse)
    report['inputs'] = {'server': dict(manifest['server']), 'packs': [dict(p) for p in packs],
                        'engine_member': nested[0], 'engine_sha256': digest(engine_raw),
                        'target_format': list(TARGET_FORMAT)}
    for record in records:
        with Path(record['path']).open('rb') as stream:
            need(hashlib.file_digest(stream, 'sha256').hexdigest() == record['sha256'], 'Input changed during audit')
    report['inputs_unchanged'] = True
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    try:
        manifest = decode_json(args.manifest.read_bytes())
        protected = [args.manifest, *(Path(r['path']) for r in [manifest['server'], *manifest['packs']])]
        need(args.report.resolve() not in {p.resolve() for p in protected}, 'Report cannot overwrite an input')
        report = audit_manifest(manifest)
    except Exception as error:
        print('STACK_AUDIT_ERROR', repr(error), file=sys.stderr)
        return 2
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with args.report.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({k: report[k] for k in ('pass', 'audit_complete', 'counts', 'errors')}))
    return 0 if report['pass'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
