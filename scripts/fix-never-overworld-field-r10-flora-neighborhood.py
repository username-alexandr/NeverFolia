#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

REL = Path('folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldSubmergedRemnants.java')
OLD = '''    private static boolean touchesWater(final ChunkAccess chunk, final BlockPos pos, final int minX, final int minZ) {
        if (stateAtOwned(chunk, pos.getX(), pos.getY() - 1, pos.getZ(), minX, minZ).is(Blocks.WATER)
            || stateAtOwned(chunk, pos.getX(), pos.getY() + 1, pos.getZ(), minX, minZ).is(Blocks.WATER)) return true;
        for (int[] d : HORIZONTAL) {
            if (stateAtOwned(chunk, pos.getX() + d[0], pos.getY(), pos.getZ() + d[1], minX, minZ).is(Blocks.WATER)) return true;
        }
        return false;
    }
'''
NEW = '''    private static boolean touchesWater(final ChunkAccess chunk, final BlockPos pos, final int minX, final int minZ) {
        // Final flooded bottoms can leave a terrestrial plant one block below a
        // tree/log or sediment lip while source water occupies a diagonal cell.
        // Inspect only the owning chunk so the result stays independent of the
        // neighbouring chunk's LIGHT scheduling order.
        for (int dy = -1; dy <= 1; ++dy) {
            for (int dz = -1; dz <= 1; ++dz) {
                for (int dx = -1; dx <= 1; ++dx) {
                    if (dx == 0 && dy == 0 && dz == 0) continue;
                    if (stateAtOwned(chunk, pos.getX() + dx, pos.getY() + dy, pos.getZ() + dz, minX, minZ).is(Blocks.WATER)) {
                        return true;
                    }
                }
            }
        }
        return false;
    }
'''


def fail(message: str) -> None:
    raise SystemExit('[NeverFolia][NeverOverworld FIELD-R10 flora-neighborhood] ' + message)


def patch(text: str) -> str:
    if NEW in text:
        if text.count(NEW) != 1 or OLD in text:
            fail('partial/duplicate patched helper')
        return text
    if text.count(OLD) != 1:
        fail(f'expected exactly one old touchesWater method, got {text.count(OLD)}')
    out = text.replace(OLD, NEW, 1)
    if out.count('for (int dy = -1; dy <= 1; ++dy)') != 1:
        fail('3x3x3 flood-neighborhood loop missing')
    if 'neighbouring chunk\'s LIGHT scheduling order' not in out:
        fail('ownership/determinism marker missing')
    return out


def self_test() -> None:
    fixture = 'class X {\n' + OLD + '}\n'
    out = patch(fixture)
    if patch(out) != out:
        fail('transformer is not idempotent')
    for marker in ('dx = -1', 'dy = -1', 'dz = -1', 'stateAtOwned(chunk'):
        if marker not in out:
            fail('missing marker ' + marker)
    print('[NeverFolia][NeverOverworld FIELD-R10 flora-neighborhood] SELF-TEST OK')


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument('folia', nargs='?', type=Path)
    p.add_argument('--self-test', action='store_true')
    a = p.parse_args()
    self_test()
    if a.self_test:
        return
    if a.folia is None:
        p.error('folia worktree path is required')
    path = a.folia.resolve() / REL
    if not path.is_file():
        fail('helper missing: ' + str(path))
    path.write_text(patch(path.read_text(encoding='utf-8')), encoding='utf-8')
    print('[NeverFolia][NeverOverworld FIELD-R10 flora-neighborhood] owning-chunk 3x3x3 water detection applied')


if __name__ == '__main__':
    main()
