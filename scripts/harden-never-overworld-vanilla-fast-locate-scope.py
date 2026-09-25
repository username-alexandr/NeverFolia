#!/usr/bin/env python3
from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

CHUNK_REL = Path('folia-server/src/minecraft/java/net/minecraft/world/level/chunk/ChunkGenerator.java')
OLD = '        if (!createReference && NeverOverworldVanillaFastLocate.handles(wantedStructures)) {\n'
NEW = '''        if (!createReference
            && level.dimension().equals(net.minecraft.world.level.Level.OVERWORLD)
            && level.getMinY() == -512
            && level.getHeight() == 1024
            && NeverOverworldVanillaFastLocate.handles(wantedStructures)) {
'''


def patch(source: str) -> str:
    if NEW in source:
        raise SystemExit('[NeverFolia][vanilla fast locate scope] guard already applied')
    count = source.count(OLD)
    if count != 1:
        raise SystemExit(f'[NeverFolia][vanilla fast locate scope] expected one hook, got {count}')
    source = source.replace(OLD, NEW, 1)
    for marker in (
        'level.dimension().equals(net.minecraft.world.level.Level.OVERWORLD)',
        'level.getMinY() == -512',
        'level.getHeight() == 1024',
        'NeverOverworldVanillaFastLocate.handles(wantedStructures)',
    ):
        if marker not in source:
            raise SystemExit(f'[NeverFolia][vanilla fast locate scope] missing {marker!r}')
    return source


def self_test() -> None:
    fixture = '''class ChunkGenerator {
    Object find(boolean createReference, ServerLevel level, HolderSet<Structure> wantedStructures) {
        if (!createReference && NeverOverworldVanillaFastLocate.handles(wantedStructures)) {
            return NeverOverworldVanillaFastLocate.find(this, level, wantedStructures, pos, maxSearchRadius);
        }
    }
}
'''
    out = patch(fixture)
    if out.index('level.getMinY() == -512') > out.index('NeverOverworldVanillaFastLocate.handles'):
        raise SystemExit('[NeverFolia][vanilla fast locate scope] dimension guard must precede handles')
    print('[NeverFolia][vanilla fast locate scope] SELF-TEST OK')


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('folia', nargs='?', type=Path)
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if args.folia is None:
        parser.error('folia root is required unless --self-test is used')
    path = args.folia.resolve() / CHUNK_REL
    if not path.is_file():
        raise SystemExit(f'[NeverFolia][vanilla fast locate scope] ChunkGenerator not found: {path}')
    path.write_text(patch(path.read_text(encoding='utf-8')), encoding='utf-8')
    print('[NeverFolia][vanilla fast locate scope] NeverOverworld-only guard applied')
    print(f'  source: {path}')


if __name__ == '__main__':
    main()
