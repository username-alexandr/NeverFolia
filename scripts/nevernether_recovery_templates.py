"""Authored replacement designs for four absent D&T 5.3.2 templates.

These are explicitly new NeverFolia designs, NOT recovered upstream originals.
Only attachment contracts are taken from supplied source metadata. No source
NBT/assets are embedded. A replacement never overwrites an existing source file.
"""
from __future__ import annotations

import gzip
import hashlib
import io
import json
import struct
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
PREFIX = 'data/nova_structures/structure/'
STONE = 'minecraft:polished_blackstone_bricks'
AIR = 'minecraft:air'


def nbt(value: object) -> tuple[int, bytes]:
    """Small writer for authored int/string/compound/homogeneous-list NBT only.

    Deliberately not a re-encoder for arbitrary upstream NBT: numeric tag types
    must not be guessed when round-tripping third-party templates.
    """
    def text(s: str) -> bytes:
        raw = s.encode('utf-8')
        if len(raw) > 65535 or any(ord(c) > 127 or ord(c) == 0 for c in s):
            raise ValueError('Authored NBT strings must be non-NUL ASCII <=65535 bytes')
        return struct.pack('>H', len(raw)) + raw
    if type(value) is int:
        return 3, struct.pack('>i', value)
    if isinstance(value, str):
        return 8, text(value)
    if isinstance(value, list):
        children = [nbt(child) for child in value]
        typ = children[0][0] if children else 0
        if any(t != typ for t, _ in children):
            raise ValueError('Mixed NBT list element types')
        return 9, bytes([typ]) + struct.pack('>i', len(children)) + b''.join(b for _, b in children)
    if isinstance(value, dict):
        chunks = []
        for key in sorted(value):
            if not isinstance(key, str): raise ValueError('NBT compound keys must be strings')
            typ, payload = nbt(value[key])
            chunks.append(bytes([typ]) + text(key) + payload)
        return 10, b''.join(chunks) + b'\0'
    raise ValueError(f'Unsupported authored NBT value type: {type(value).__name__}')


def encode(value: dict) -> bytes:
    typ, raw = nbt(value)
    if typ != 10: raise ValueError('Root must be a compound')
    output = io.BytesIO()
    with gzip.GzipFile(fileobj=output, mode='wb', filename='', mtime=0, compresslevel=9) as z:
        z.write(b'\x0a\x00\x00' + raw)
    return output.getvalue()


class Template:
    def __init__(self, size: tuple[int, int, int], data_version: int):
        if any(type(n) is not int or not 1 <= n <= 128 for n in size):
            raise ValueError('Invalid authored template dimensions')
        if type(data_version) is not int or data_version <= 0:
            raise ValueError('Invalid DataVersion')
        self.size, self.data_version = size, data_version
        self.blocks: dict[tuple[int, int, int], tuple[dict, dict | None]] = {}

    def block(self, x: int, y: int, z: int, name: str, properties: dict | None = None,
              block_nbt: dict | None = None) -> None:
        pos = (x, y, z)
        if any(not 0 <= pos[i] < self.size[i] for i in range(3)):
            raise ValueError(f'Block {pos} outside {self.size}')
        state = {'Name': name}
        if properties: state['Properties'] = dict(properties)
        self.blocks[pos] = (state, block_nbt)

    def box(self, a: tuple[int, int, int], b: tuple[int, int, int], name: str) -> None:
        if any(a[i] > b[i] for i in range(3)): raise ValueError('Reversed box')
        for y in range(a[1], b[1] + 1):
            for z in range(a[2], b[2] + 1):
                for x in range(a[0], b[0] + 1): self.block(x, y, z, name)

    def port(self, pos: tuple[int, int, int], orientation: str, name: str,
             pool: str = 'minecraft:empty', target: str = 'minecraft:empty',
             final_state: str = STONE) -> None:
        self.block(*pos, 'minecraft:jigsaw', {'orientation': orientation}, {
            'id': 'minecraft:jigsaw', 'joint': 'aligned', 'name': name, 'pool': pool,
            'target': target, 'final_state': final_state,
            'placement_priority': 0, 'selection_priority': 0,
        })

    def value(self) -> dict:
        palette, indices, blocks = [], {}, []
        for pos in sorted(self.blocks, key=lambda p: (p[1], p[2], p[0])):
            state, block_nbt = self.blocks[pos]
            key = json.dumps(state, sort_keys=True)
            if key not in indices:
                indices[key] = len(palette); palette.append(state)
            block = {'pos': list(pos), 'state': indices[key]}
            if block_nbt is not None: block['nbt'] = block_nbt
            blocks.append(block)
        return {'DataVersion': self.data_version, 'size': list(self.size),
                'palette': palette, 'blocks': blocks, 'entities': []}


def decoration(data_version: int, variant: int) -> Template:
    if variant not in (14, 15): raise ValueError('Only missing variants 14 and 15 are authored')
    t = Template((4, 4, 4), data_version)
    t.box((0, 0, 0), (3, 3, 3), AIR)
    t.box((0, 0, 0), (3, 0, 3), STONE)
    if variant == 14:
        t.box((1, 1, 1), (2, 1, 2), 'minecraft:chiseled_polished_blackstone')
        t.box((1, 2, 1), (2, 2, 2), 'minecraft:glowstone')
        t.box((1, 3, 1), (2, 3, 2), 'minecraft:polished_blackstone_slab')
    else:
        t.box((1, 1, 1), (2, 1, 2), 'minecraft:gilded_blackstone')
        for x, z in ((1, 1), (2, 2)):
            t.block(x, 2, z, 'minecraft:polished_basalt', {'axis': 'y'})
            t.block(x, 3, z, 'minecraft:shroomlight')
    for pos, orient in (((0, 0, 0), 'down_south'), ((0, 0, 3), 'down_east'),
                        ((3, 0, 0), 'down_west'), ((3, 0, 3), 'down_north')):
        t.port(pos, orient, 'nova_structures:deco', final_state='minecraft:structure_void')
    return t


def hall(data_version: int) -> Template:
    """46x21x46 gallery; grid dimensions inferred from neighboring 3xNxM rooms.

    The supplied frames have no consumer of donjon_room_3x3x3. This resource
    repairs loading of the pool; it does not add a new frame or claim natural
    placement of this particular room. It is useful for explicit template QA.
    """
    t = Template((46, 21, 46), data_version)
    t.box((0, 0, 0), (45, 20, 45), AIR)
    for y in (0, 20): t.box((0, y, 0), (45, y, 45), STONE)
    for x in (0, 45): t.box((x, 1, 0), (x, 19, 45), STONE)
    for z in (0, 45): t.box((0, 1, z), (45, 19, z), STONE)
    # Wide perimeter galleries and a cross-shaped bridge on both upper levels.
    for y in (7, 14):
        for x in range(1, 45):
            for z in range(1, 45):
                if x <= 8 or x >= 37 or z <= 8 or z >= 37 or 21 <= x <= 24 or 21 <= z <= 24:
                    t.block(x, y, z, STONE)
        for edge in (8, 21, 24, 37):
            for v in range(9, 37):
                if 20 <= v <= 25: continue
                t.block(edge, y + 1, v, 'minecraft:polished_blackstone_brick_wall')
                t.block(v, y + 1, edge, 'minecraft:polished_blackstone_brick_wall')
    # Load-bearing columns, full floor and roof, no fluid traps.
    for x in (10, 19, 26, 35):
        for z in (10, 19, 26, 35):
            t.box((x, 1, z), (x, 19, z), 'minecraft:polished_basalt')
            for y in (5, 12, 19): t.block(x, y, z, 'minecraft:shroomlight')
    # Each gallery has access through the 16-block room grid's door positions.
    for y in (1, 8, 15):
        for c in (7, 23, 39):
            for x in (0, 45): t.box((x, y, c - 1), (x, y + 3, c + 2), AIR)
            for z in (0, 45): t.box((c - 1, y, z), (c + 2, y + 3, z), AIR)
    # Two physically backed ladder shafts connect all three walking levels.
    for z in (4, 41):
        for y in range(1, 20):
            t.block(0, y, z, STONE)
            t.block(1, y, z, 'minecraft:ladder', {'facing': 'east', 'waterlogged': 'false'})
    for x, z in ((6, 6), (39, 39)):
        t.port((x, 1, z), 'down_south', 'minecraft:empty',
               'nova_structures:donjon/donjon_chest', 'nova_structures:donjon_chest_stable', AIR)
    for x, z in ((16, 23), (29, 23), (23, 16), (23, 29)):
        t.port((x, 2, z), 'down_south', 'minecraft:empty',
               'nova_structures:donjon/donjon_mob', 'nova_structures:donjon_piglin', AIR)
    t.port((45, 0, 45), 'south_up', 'nova_structures:donjon_room_3x3x3')
    return t


def foundation(data_version: int) -> Template:
    """Solid stepped buttress with the existing outer-layer vault's attachment.

    Keep the 22x42x48 envelope and y=28 anchor, but do not copy its vault or loot.
    Top air is explicit only inside the envelope; surrounding world is untouched.
    """
    t = Template((22, 42, 48), data_version)
    t.box((0, 0, 0), (21, 41, 47), AIR)
    # Continuous stone mass under every part of the deck (no air pocket fill pass).
    t.box((0, 0, 0), (21, 28, 47), 'minecraft:blackstone')
    for y in (0, 7, 14, 21, 28):
        t.box((0, y, 0), (21, y, 47), STONE)
    # Perimeter parapet, with the anchor-facing edge kept walkable.
    for z in (0, 47): t.box((1, 29, z), (21, 30, z), STONE)
    t.box((21, 29, 0), (21, 30, 47), STONE)
    for z in range(4, 45, 8):
        t.box((18, 29, z), (19, 32, z + 1), 'minecraft:polished_basalt')
        t.box((18, 33, z), (19, 33, z + 1), 'minecraft:shroomlight')
    t.port((0, 28, 47), 'west_up', 'nova_structures:outstation_outer_layer')
    # Continue the same two source land/void-layer connection chains as the vault.
    t.port((21, 0, 41), 'east_up', 'minecraft:minecraft_empty',
           'nova_structures:piglin_outstation/outer_layer', 'nova_structures:outstation_netherrack_layer_1', 'minecraft:blackstone')
    t.port((21, 0, 42), 'east_up', 'minecraft:minecraft_empty',
           'nova_structures:piglin_outstation/outer_layer', 'nova_structures:outstation_netherrack_layer_2', 'minecraft:blackstone')
    return t


def generated(data_version: int) -> dict[str, Template]:
    return {
        'donjon/coloseum_part/deco_14': decoration(data_version, 14),
        'donjon/coloseum_part/deco_15': decoration(data_version, 15),
        'donjon/room/donjon_room_3x3x3_1': hall(data_version),
        'piglin_outstation/main/piglin_outpost_outer_layer_foundation_1': foundation(data_version),
    }


def apply_recoveries(archive, profile: dict) -> None:
    """Verify all pinned inputs and output destinations before changing the view."""
    if archive.sha256 != profile['source_sha256']:
        raise ValueError('Recovery source SHA-256 mismatch')
    data_version = None
    for rel, expected_hash in profile['contract_inputs'].items():
        path = PurePosixPath(rel)
        if path not in archive.entries or hashlib.sha256(archive.entries[path]).hexdigest() != expected_hash:
            raise ValueError(f'Recovery contract input mismatch: {rel}')
        if data_version is None and path.suffix == '.nbt':
            data_version = archive.decode(path).get('DataVersion')
    if data_version is None: raise ValueError('No reference DataVersion')
    pending = []
    for name, template in generated(data_version).items():
        path = PurePosixPath(PREFIX + name + '.nbt')
        if path in archive.entries: raise ValueError(f'Recovery would overwrite existing template: {path}')
        value = template.value()
        pending.append((path, encode(value), template))
    for path, payload, template in pending:
        archive.entries[path] = payload
        archive.provenance[path] = 'neverfolia-authored/recovery-r4'
        archive.compatibility_changes.append({
            'resource': str(path), 'policy': 'authored_reconstruction_r4',
            'sha256': hashlib.sha256(payload).hexdigest(), 'size': list(template.size),
            'blocks': len(template.blocks), 'upstream_original': False,
            'runtime_validated': False,
            'natural_consumer': 'not_present_in_supplied_frames' if '3x3x3' in str(path) else 'source_attachment_contract',
        })
    archive.dependency_cache.clear()
