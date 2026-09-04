#!/usr/bin/env python3
from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

HELPER_REL = Path('folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldFlood.java')
MARKER = '// NeverFolia: sparse raised-bank fallback for flooded sugar cane.'
CALL_OLD = '''        if (placed == 0 && fallbackIndex >= 0) {
            final int localX = fallbackIndex & 15;
            final int localZ = (fallbackIndex >>> 4) & 15;
            final long hash = shorelineHash(chunk.getPos(), fallbackIndex ^ 0x6B6B);
            placeSugarCaneColumn(chunk, minX, minZ, localX, localZ, hash);
        }
'''
CALL_NEW = '''        if (placed == 0 && fallbackIndex >= 0) {
            final int localX = fallbackIndex & 15;
            final int localZ = (fallbackIndex >>> 4) & 15;
            final long hash = shorelineHash(chunk.getPos(), fallbackIndex ^ 0x6B6B);
            placeSugarCaneColumn(chunk, minX, minZ, localX, localZ, hash);
            return;
        }

        if (placed == 0) {
            createSparseSugarCaneBankAtFloodShoreline(level, chunk, minX, minZ);
        }
'''
INSERT_BEFORE = '    private static boolean isSugarCaneBiome(final WorldGenLevel level, final BlockPos pos) {\n'
METHOD = r'''    // NeverFolia: sparse raised-bank fallback for flooded sugar cane.
    // The Y=128 flood can move the shoreline so far above vanilla terrain that
    // no naturally generated cane substrate survives at water level. In that
    // case a small fraction of river/swamp chunks receive one deterministic
    // 1x1 sand bank and a 1-3 block cane clump. Reads/writes remain strictly
    // inside the owning chunk (local coordinates 1..14), preserving Folia
    // ownership and chunk-order determinism.
    private static void createSparseSugarCaneBankAtFloodShoreline(
        final WorldGenLevel level,
        final ChunkAccess chunk,
        final int minX,
        final int minZ
    ) {
        final long chunkHash = shorelineHash(chunk.getPos(), 0x7C7C);
        // Roughly one fallback bank per sixteen qualifying chunks. Natural
        // shoreline cane, when available, always wins and bypasses this path.
        if (Math.floorMod(chunkHash, 16L) != 0L) {
            return;
        }

        final BlockPos.MutableBlockPos surface = new BlockPos.MutableBlockPos();
        final BlockPos.MutableBlockPos above = new BlockPos.MutableBlockPos();
        final BlockPos.MutableBlockPos below = new BlockPos.MutableBlockPos();
        int bestIndex = -1;
        long bestScore = Long.MAX_VALUE;

        for (int localZ = 1; localZ <= 14; ++localZ) {
            for (int localX = 1; localX <= 14; ++localX) {
                final int index = (localZ << 4) | localX;
                surface.set(minX + localX, FLOOD_LEVEL, minZ + localZ);
                above.set(minX + localX, FLOOD_LEVEL + 1, minZ + localZ);
                below.set(minX + localX, FLOOD_LEVEL - 1, minZ + localZ);

                if (!chunk.getBlockState(surface).is(Blocks.WATER)
                    || !chunk.getBlockState(above).isAir()) {
                    continue;
                }

                final BlockState belowState = chunk.getBlockState(below);
                if (belowState.isAir() || belowState.is(Blocks.WATER)) {
                    continue;
                }
                if (!hasChunkLocalWaterNeighbor(chunk, minX, minZ, localX, localZ)) {
                    continue;
                }
                if (!isSugarCaneBiome(level, above)) {
                    continue;
                }

                final long score = shorelineHash(chunk.getPos(), index ^ 0x4D4D) & Long.MAX_VALUE;
                if (score < bestScore) {
                    bestScore = score;
                    bestIndex = index;
                }
            }
        }

        if (bestIndex < 0) {
            return;
        }

        final int localX = bestIndex & 15;
        final int localZ = (bestIndex >>> 4) & 15;
        surface.set(minX + localX, FLOOD_LEVEL, minZ + localZ);
        chunk.setBlockState(surface, Blocks.SAND.defaultBlockState(), 0);
        final long caneHash = shorelineHash(chunk.getPos(), bestIndex ^ 0x3E3E);
        placeSugarCaneColumn(chunk, minX, minZ, localX, localZ, caneHash);
    }

'''


def fail(message: str) -> None:
    raise SystemExit(f'[NeverFolia][shoreline cane bank] {message}')


def patch(text: str) -> str:
    if MARKER in text:
        return text
    if text.count(CALL_OLD) != 1:
        fail(f'expected one old fallback block, got {text.count(CALL_OLD)}')
    if text.count(INSERT_BEFORE) != 1:
        fail(f'expected one isSugarCaneBiome insertion point, got {text.count(INSERT_BEFORE)}')
    text = text.replace(CALL_OLD, CALL_NEW, 1)
    text = text.replace(INSERT_BEFORE, METHOD + INSERT_BEFORE, 1)
    return text


def validate(text: str) -> None:
    required = (
        MARKER,
        'Math.floorMod(chunkHash, 16L)',
        'localX = 1; localX <= 14',
        'localZ = 1; localZ <= 14',
        'chunk.getBlockState(surface).is(Blocks.WATER)',
        'chunk.setBlockState(surface, Blocks.SAND.defaultBlockState(), 0)',
        'createSparseSugarCaneBankAtFloodShoreline(level, chunk, minX, minZ)',
        'hasChunkLocalWaterNeighbor(chunk, minX, minZ, localX, localZ)',
        'isSugarCaneBiome(level, above)',
    )
    missing = [marker for marker in required if marker not in text]
    if missing:
        fail(f'missing fallback markers: {missing}')
    forbidden = ('getChunk(', 'getChunkAt(', 'moonrise$syncLoadNonFull')
    leaked = [marker for marker in forbidden if marker in text]
    if leaked:
        fail(f'cross-chunk/loading primitive leaked into flood helper: {leaked}')


def apply(root: Path) -> None:
    helper = root / HELPER_REL
    if not helper.is_file():
        fail(f'NeverOverworldFlood helper not found: {helper}')
    text = patch(helper.read_text(encoding='utf-8'))
    validate(text)
    helper.write_text(text, encoding='utf-8')
    print('[NeverFolia][shoreline cane bank] sparse deterministic bank fallback applied')
    print('  density: ~1/16 qualifying river/swamp chunks, only when natural relocation failed')
    print('  bank: one Y=128 sand cell; cane: Y=129..131')
    print('  ownership: local coordinates 1..14 only; no neighboring chunk access')


def self_test() -> None:
    fixture = '''final class NeverOverworldFlood {
    private static final int FLOOD_LEVEL = 128;
    private static void reseedSugarCaneAtFloodShoreline(Object level, Object chunk, int minX, int minZ) {
        int placed = 0;
        int fallbackIndex = -1;
        if (placed == 0 && fallbackIndex >= 0) {
            final int localX = fallbackIndex & 15;
            final int localZ = (fallbackIndex >>> 4) & 15;
            final long hash = shorelineHash(chunk.getPos(), fallbackIndex ^ 0x6B6B);
            placeSugarCaneColumn(chunk, minX, minZ, localX, localZ, hash);
        }
    }
    private static boolean isSugarCaneBiome(final WorldGenLevel level, final BlockPos pos) { return true; }
    private static boolean hasChunkLocalWaterNeighbor(Object chunk, int minX, int minZ, int localX, int localZ) { return true; }
    private static long shorelineHash(Object pos, int index) { return 0L; }
    private static void placeSugarCaneColumn(Object chunk, int minX, int minZ, int localX, int localZ, long hash) {}
}
'''
    with tempfile.TemporaryDirectory(prefix='nr-shoreline-cane-bank-') as tmp:
        root = Path(tmp)
        helper = root / HELPER_REL
        helper.parent.mkdir(parents=True, exist_ok=True)
        helper.write_text(fixture, encoding='utf-8')
        text = patch(helper.read_text(encoding='utf-8'))
        validate(text)
        helper.write_text(text, encoding='utf-8')
    print('[NeverFolia][shoreline cane bank] SELF-TEST OK')


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('folia_root', nargs='?', type=Path)
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if args.folia_root is None:
        parser.error('folia_root is required unless --self-test is used')
    apply(args.folia_root.resolve())


if __name__ == '__main__':
    main()
