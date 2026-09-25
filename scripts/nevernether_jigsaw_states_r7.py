"""Pinned repairs for two invalid Jigsaw final_state strings in the supplied ZIPs.

Only TAG_String payloads are replaced. Original NBT scalar types, palettes,
geometry, inventories and every unrelated byte are preserved before re-gzip.
"""
from __future__ import annotations
import copy
import gzip
import hashlib
import importlib.util
import io
import json
from pathlib import Path, PurePosixPath
import struct

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / 'worldgen-spec/never-nether-jigsaw-states-r7.json'
MAX_NBT = 32 * 1024 * 1024


def parser():
    spec = importlib.util.spec_from_file_location('nn_r7_nbt', ROOT / 'scripts/hash-never-nether-chunks.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module.parse_nbt


def encoded_field(value: str) -> bytes:
    raw = value.encode('utf-8')
    if len(raw) > 65535:
        raise ValueError('TAG_String length overflow')
    return b'\x08\x00\x0bfinal_state' + struct.pack('>H', len(raw)) + raw


def repair(payload: bytes, old: str, new: str, expected_count: int) -> bytes:
    if type(expected_count) is not int or expected_count < 1 or old == new:
        raise ValueError('Invalid final-state repair contract')
    compressed = payload.startswith(b'\x1f\x8b')
    if compressed:
        with gzip.GzipFile(fileobj=io.BytesIO(payload)) as stream:
            raw = stream.read(MAX_NBT + 1)
    else:
        raw = payload
    if len(raw) > MAX_NBT:
        raise ValueError('NBT exceeds limit')
    parse = parser(); original = parse(raw); expected = copy.deepcopy(original)
    changed = 0
    for block in expected.get('blocks', []):
        nbt = block.get('nbt', {})
        if nbt.get('id') == 'minecraft:jigsaw' and nbt.get('final_state') == old:
            nbt['final_state'] = new; changed += 1
    before, after = encoded_field(old), encoded_field(new)
    if changed != expected_count or raw.count(before) != changed:
        raise ValueError('Expected exact Jigsaw fields, not a broad binary substitution')
    updated = raw.replace(before, after)
    if parse(updated) != expected:
        raise ValueError('Unrelated NBT changed')
    # Modified payloads are reproducible; no input ZIP is rewritten.
    return gzip.compress(updated, compresslevel=9, mtime=0) if compressed else updated


def apply_states(archive, source_key: str) -> None:
    profile = json.loads(PROFILE.read_text())['sources'].get(source_key)
    if profile is None or archive.sha256 != profile['source_sha256']:
        return  # Other versions/synthetic fixtures receive no implicit conversion.
    staged = []
    for rule in profile['repairs']:
        path = PurePosixPath(rule['path']); payload = archive.entries.get(path)
        if payload is None or hashlib.sha256(payload).hexdigest() != rule['input_sha256']:
            raise ValueError('Jigsaw source contract mismatch: ' + str(path))
        out = repair(payload, rule['old'], rule['new'], rule['count'])
        staged.append((path, out, rule))
    for path, out, rule in staged:
        archive.entries[path] = out
        archive.decoded.pop(path, None)
        archive.provenance[path] = 'neverfolia-jigsaw-finalstate-r7/' + str(path)
        archive.compatibility_changes.append({
            'policy': 'exact_jigsaw_final_state_r7', 'resource': str(path),
            'old': rule['old'], 'new': rule['new'], 'count': rule['count'],
            'input_sha256': rule['input_sha256'], 'output_sha256': hashlib.sha256(out).hexdigest(),
        })
    archive.dependency_cache.clear()
