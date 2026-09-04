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
    // Raising the flood plane from the old vanilla sea level to Y=128 means a
    // river/swamp column can be dozens of blocks above its former seabed. Requiring
    // solid terrain directly at Y=127 therefore made the fallback impossible in
    // the exact flooded biomes that need it. Create a tiny deterministic emergent
    // dirt hummock instead. It is intentionally sparse, non-gravity, chunk-owned,
    // and only appears in river/swamp biome cells with water around it.
    private static void createSparseSugarCaneBankAtFloodShoreline(
        final WorldGenLevel level,
        final ChunkAccess chunk,
        final int minX,
        final int minZ
    ) {
        final long chunkHash = shorelineHash(chunk.getPos(), 0x7C7C);
        // Approximately one fallback hummock per four eligible river/swamp chunks.
        // Natural relocated/reseeded cane always wins and bypasses this path.
        if (Math.floorMod(chunkHash, 4L) != 0L) {
            return;
        }

        final BlockPos.MutableBlockPos surface = new BlockPos.MutableBlockPos();
        final BlockPos.MutableBlockPos above = new BlockPos.MutableBlockPos();
        int bestIndex = -1;
        long bestScore = Long.MAX_VALUE;

        for (int localZ = 1; localZ <= 14; ++localZ) {
            for (int localX = 1; localX <= 14; ++localX) {
                final int index = (localZ << 4) | localX;
                surface.set(minX + localX, FLOOD_LEVEL, minZ + localZ);
                above.set(minX + localX, FLOOD_LEVEL + 1, minZ + localZ);

                if (!chunk.getBlockState(surface).is(Blocks.WATER)
                    || !chunk.getBlockState(above).isAir()) {
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

        // Form a three-block-deep maximum root/hummock. DIRT is deliberately used
        // instead of gravity-affected SAND so the new Y=128 ecology remains stable
        // even when the historic seabed is far below the raised flood plane.
        for (int depth = 0; depth < 3; ++depth) {
            surface.set(minX + localX, FLOOD_LEVEL - depth, minZ + localZ);
            if (!chunk.getBlockState(surface).is(Blocks.WATER)) {
                break;
            }
            chunk.setBlockState(surface, Blocks.DIRT.defaultBlockState(), 0);
        }

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
        'Math.floorMod(chunkHash, 4L)',
        'localX = 1; localX <= 14',
        'localZ = 1; localZ <= 14',
        'chunk.getBlockState(surface).is(Blocks.WATER)',
        'depth = 0; depth < 3',
        'chunk.setBlockState(surface, Blocks.DIRT.defaultBlockState(), 0)',
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
    print('[NeverFolia][shoreline cane bank] sparse deterministic hummock fallback applied')
    print('  density: ~1/4 eligible river/swamp chunks, only when natural relocation failed')
    print('  hummock: Y=128 down to at most Y=126 using stable dirt; cane: Y=129..131')
    print('  ownership: local coordinates 1..14 only; no neighboring chunk access')


def self_test() -> None:
    fixture = '''final class NeverOverworldFlood {
    private static final int FLOOD_LEVEL = 128;
    private static void reseedSugarCaneAtFloodShoreline(final WorldGenLevel level, final ChunkAccess chunk, int minX, int minZ) {
        int placed = 0;
        int fallbackIndex = -1;
        if (placed == 0 && fallbackIndex >= 0) {
            final int localX = fallbackIndex & 15;
            final int localZ = (fallbackIndex >>> 4) & 15;
            final long hash = shorelineHash(chunk.getPos(), fallbackIndex ^ 0x6B6B);
            placeSugarCaneColumn(chunk, minX, minZ, localX, localZ, hash);
        }
    }
    private static boolean isSugarCaneBiome(final WorldGenLevel level, final BlockPos pos) {
        return true;
    }
    private static boolean hasChunkLocalWaterNeighbor(ChunkAccess chunk, int minX, int minZ, int localX, int localZ) { return true; }
    private static long shorelineHash(Object pos, int index) { return 0L; }
    private static void placeSugarCaneColumn(ChunkAccess chunk, int minX, int minZ, int localX, int localZ, long hash) {}
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
