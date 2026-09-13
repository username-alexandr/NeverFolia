"""Exact-source native monument conversion; no third-party asset payloads.

Original supplemental loot is verified by immutable Git blob identity. Conversion
is atomic in staging and does not certify registry startup or world generation.
"""
from __future__ import annotations
from collections import Counter
import copy
import hashlib
import json
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / 'worldgen-spec/never-nether-monument-r5.json'
CACHE = ROOT / '.work/nevernether-monument-loot-r5'
SOURCE_SHA = 'c76cd5ab549974b051a352a633abd2f78a916acc40392bc53ba0581c3116a8c9'
PROCESSORS = {
    'repurposed_structures:noise_replace_with_properties_processor': 'neverfolia:noise_replace_properties',
    'repurposed_structures:random_replace_with_properties_processor': 'neverfolia:random_replace_properties',
    'repurposed_structures:pillar_processor': 'neverfolia:vertical_pillar',
    'repurposed_structures:structure_void_processor': 'neverfolia:structure_void',
}
ELEMENT = ('yungsapi:max_count_single_element', 'neverfolia:limited_single_pool_element')
NATIVE_CODECS = {('processor_type', value) for value in PROCESSORS.values()} | {('element_type', ELEMENT[1])}


def blob_hash(raw: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()


def translate(value: dict) -> tuple[dict, dict[str, int]]:
    value = copy.deepcopy(value)
    counts: Counter[str] = Counter()
    def walk(obj):
        if isinstance(obj, list):
            for item in obj:
                walk(item)
        elif isinstance(obj, dict):
            ptype = obj.get('processor_type')
            if ptype in PROCESSORS:
                if ptype.endswith('random_replace_with_properties_processor'):
                    if 'output_block' not in obj or 'output_blocks' in obj:
                        raise ValueError('Only the exact single-output random profile is ported')
                if ptype.endswith('pillar_processor'):
                    if obj.get('direction', 'down') != 'down' or obj.get('forced_placement', False):
                        raise ValueError('Only non-forced downward monument pillars are ported')
                obj['processor_type'] = PROCESSORS[ptype]
                counts[ptype] += 1
            elif isinstance(ptype, str) and not ptype.startswith('minecraft:'):
                raise ValueError(f'Unknown processor is not dropped: {ptype}')
            element = obj.get('element_type')
            if element == ELEMENT[0]:
                if type(obj.get('max_count')) is not int or obj['max_count'] < 0 or not isinstance(obj.get('name'), str) or not obj['name']:
                    raise ValueError('Invalid named room quota')
                obj['element_type'] = ELEMENT[1]
                counts[element] += 1
            elif isinstance(element, str) and not element.startswith('minecraft:'):
                raise ValueError(f'Unknown pool element is not dropped: {element}')
            for item in obj.values():
                walk(item)
    walk(value)
    return value, dict(sorted(counts.items()))


def read_supplements(cache: Path, profile: dict) -> dict[PurePosixPath, bytes]:
    staged = {}
    for item in profile['supplemental_files']:
        path = cache / item['filename']
        if not path.is_file():
            raise ValueError(f'Pinned monument input missing: {path}; run fetch-never-nether-monument-loot-r5.py')
        raw = path.read_bytes()
        if blob_hash(raw) != item['git_blob']:
            raise ValueError(f'Pinned monument supplemental blob mismatch: {path.name}')
        target = PurePosixPath(item['pack_path'])
        if target.is_absolute() or '..' in target.parts or target in staged:
            raise ValueError(f'Unsafe or duplicate supplemental destination: {target}')
        if target.suffix == '.json' and not isinstance(json.loads(raw), dict):
            raise ValueError('Supplemental loot must be an object')
        staged[target] = raw
    return staged


def apply_monument(archive, cache: Path = CACHE) -> None:
    if archive.sha256 != SOURCE_SHA:
        raise ValueError('Unrecognized monument ZIP; no native conversion attempted')
    profile = json.loads(PROFILE.read_text())
    if profile['source_sha256'] != SOURCE_SHA:
        raise ValueError('Monument profile source identity mismatch')
    staged = {}
    all_counts: Counter[str] = Counter()
    for name, expected in profile['contract_hashes'].items():
        path = PurePosixPath(name)
        payload = archive.entries.get(path)
        if payload is None or hashlib.sha256(payload).hexdigest() != expected:
            raise ValueError(f'Monument input contract mismatch: {path}')
        converted, counts = translate(json.loads(payload))
        all_counts.update(counts)
        if counts:
            staged[path] = (json.dumps(converted, indent=2) + '\n').encode()
    if dict(sorted(all_counts.items())) != profile['expected_translations']:
        raise ValueError('Unexpected native processor/room quota inventory')
    for name, expected in profile.get('legacy_feature_hashes', {}).items():
        path = PurePosixPath(name)
        payload = archive.entries.get(path)
        if payload is None or hashlib.sha256(payload).hexdigest() != expected:
            raise ValueError(f'Legacy feature input contract mismatch: {path}')
        staged[path] = (json.dumps(convert_legacy_patch(json.loads(payload)), indent=2) + '\n').encode()
    supplements = read_supplements(cache, profile)
    for path in supplements:
        if path in archive.entries:
            raise ValueError(f'Supplement would overwrite existing source: {path}')
    # No staging mutation occurs until all input hashes and output resources pass.
    for path, payload in staged.items():
        archive.entries[path] = payload
        archive.decoded.pop(path, None)
        archive.provenance[path] = 'neverfolia-native-r5/' + str(path)
    for path, payload in supplements.items():
        archive.entries[path] = payload
        archive.provenance[path] = 'pinned-upstream-supplement/' + str(path)
    archive.native_codecs = set(NATIVE_CODECS)
    archive.supplemental_notices = {p: raw for p, raw in supplements.items() if p.parts[0] != 'data'}
    archive.dependency_cache.clear()
    archive.compatibility_changes.append({
        'policy': 'native_monument_r5', 'source_sha256': SOURCE_SHA,
        'required_runtime_profile': 'NN-NATIVE-R5', 'runtime_validated': False,
        'translated_counts': dict(sorted(all_counts.items())),
        'supplemental_files': profile['supplemental_files'],
        'pillar_safety_policy': 'worldgen-owned-vertical-bounded-confirmed-anchor-only',
    })


def convert_legacy_patch(value: dict) -> dict:
    """26.2 removed random_patch; preserve the exact source attempt/offset distribution.

    Weighted placement consumes RNG differently from the old feature. This is an
    explicit compatibility conversion, not a claim of identical historic layouts.
    """
    if set(value) != {'type', 'config'} or value['type'] != 'minecraft:random_patch':
        raise ValueError('Expected the pinned legacy random_patch shape')
    config = value['config']
    if set(config) != {'tries', 'xz_spread', 'y_spread', 'feature'}:
        raise ValueError('Unexpected legacy patch configuration')
    tries, spread, vertical = config['tries'], config['xz_spread'], config['y_spread']
    if (tries, spread, vertical) not in ((1, 0, 0), (3, 1, 0)):
        raise ValueError('Only the two inspected monument patch profiles are supported')
    child = copy.deepcopy(config['feature'])
    if set(child) != {'feature', 'placement'} or not isinstance(child['placement'], list):
        raise ValueError('Unexpected nested placed feature')
    placement = [{'type': 'minecraft:count', 'count': tries}]
    if spread:
        placement.append({'type': 'minecraft:random_offset', 'xz_spread': {
            'type': 'minecraft:weighted_list', 'distribution': [
                {'data': -1, 'weight': 1}, {'data': 0, 'weight': 2}, {'data': 1, 'weight': 1}]}, 'y_spread': 0})
    child['placement'] = placement + child['placement']
    return {'type': 'minecraft:sequence', 'config': {'features': [child]}}
