#!/usr/bin/env python3
from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

HELPER_REL = Path('folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldFlood.java')
MARKER = '// NeverFolia: tiny vegetated shoreline islet fallback for flooded flora.'
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
            createSparseVegetatedShorelineIslet(level, chunk, minX, minZ);
        }
'''
INSERT_BEFORE = '    private static boolean isSugarCaneBiome(final WorldGenLevel level, final BlockPos pos) {\n'
METHOD = r'''    // NeverFolia: tiny vegetated shoreline islet fallback for flooded flora.
    // The Y=128 flood plane can sit far above the historical river/swamp bank.
    // When no natural raised substrate survives in this owning chunk, create one
    // small deterministic emergent islet instead of a visually obvious dirt pillar.
    //
    // The islet is intentionally rare, fully chunk-owned and only generated after
    // ordinary captured/reseeded sugar cane failed. Its 5x5 bounding box never
    // touches a chunk edge. A tapered underwater dirt root supports an irregular
    // grass/sand cap, then biome-appropriate cane, flowers/ferns and an occasional
    // lily pad are added around the new shoreline.
    private static void createSparseVegetatedShorelineIslet(
        final WorldGenLevel level,
        final ChunkAccess chunk,
        final int minX,
        final int minZ
    ) {
        final long chunkHash = shorelineHash(chunk.getPos(), 0x7C7C);
        // About one fallback islet per sixteen eligible river/swamp chunks.
        // Natural relocated/reseeded flora always wins and bypasses this path.
        if (Math.floorMod(chunkHash, 16L) != 0L) {
            return;
        }

        final BlockPos.MutableBlockPos surface = new BlockPos.MutableBlockPos();
        final BlockPos.MutableBlockPos above = new BlockPos.MutableBlockPos();
        int bestIndex = -1;
        long bestScore = Long.MAX_VALUE;

        // Radius two requires centres in 3..12 to keep every read/write chunk-local.
        for (int localZ = 3; localZ <= 12; ++localZ) {
            for (int localX = 3; localX <= 12; ++localX) {
                final int index = (localZ << 4) | localX;
                surface.set(minX + localX, FLOOD_LEVEL, minZ + localZ);
                above.set(minX + localX, FLOOD_LEVEL + 1, minZ + localZ);

                if (!chunk.getBlockState(surface).is(Blocks.WATER)
                    || !chunk.getBlockState(above).isAir()
                    || !isSugarCaneBiome(level, above)) {
                    continue;
                }

                // Require open water around the centre so the fallback reads as
                // a little shoreline island, not a blob fused into existing land.
                int clearWater = 0;
                for (int dz = -2; dz <= 2; ++dz) {
                    for (int dx = -2; dx <= 2; ++dx) {
                        if (dx * dx + dz * dz > 5) {
                            continue;
                        }
                        surface.set(minX + localX + dx, FLOOD_LEVEL, minZ + localZ + dz);
                        above.set(minX + localX + dx, FLOOD_LEVEL + 1, minZ + localZ + dz);
                        if (chunk.getBlockState(surface).is(Blocks.WATER)
                            && chunk.getBlockState(above).isAir()) {
                            ++clearWater;
                        }
                    }
                }
                if (clearWater < 16) {
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

        final int centerX = bestIndex & 15;
        final int centerZ = (bestIndex >>> 4) & 15;

        // Build a compact irregular cap. The deterministic edge hash removes a
        // few radius-two cells so the outline is not a perfect circle.
        for (int dz = -2; dz <= 2; ++dz) {
            for (int dx = -2; dx <= 2; ++dx) {
                final int distanceSq = dx * dx + dz * dz;
                if (distanceSq > 5) {
                    continue;
                }
                final int localX = centerX + dx;
                final int localZ = centerZ + dz;
                final int localIndex = (localZ << 4) | localX;
                final long cellHash = shorelineHash(chunk.getPos(), localIndex ^ 0x2A2A);
                if (distanceSq >= 4 && Math.floorMod(cellHash, 4L) == 0L) {
                    continue;
                }

                surface.set(minX + localX, FLOOD_LEVEL, minZ + localZ);
                above.set(minX + localX, FLOOD_LEVEL + 1, minZ + localZ);
                if (!chunk.getBlockState(surface).is(Blocks.WATER)
                    || !chunk.getBlockState(above).isAir()) {
                    continue;
                }

                // Sandy tips around the water, grassy/dirt body inside.
                final boolean sandy = distanceSq >= 4
                    || (distanceSq >= 2 && Math.floorMod(cellHash, 5L) == 0L);
                chunk.setBlockState(
                    surface,
                    sandy ? Blocks.SAND.defaultBlockState() : Blocks.GRASS_BLOCK.defaultBlockState(),
                    0
                );

                // Tapered underwater root. This avoids a one-block floating plate
                // while keeping the feature tiny even over a very deep flood basin.
                final int rootDepth = distanceSq == 0 ? 3 : (distanceSq <= 2 ? 2 : 1);
                for (int depth = 1; depth <= rootDepth; ++depth) {
                    surface.set(minX + localX, FLOOD_LEVEL - depth, minZ + localZ);
                    if (!chunk.getBlockState(surface).is(Blocks.WATER)) {
                        break;
                    }
                    chunk.setBlockState(surface, Blocks.DIRT.defaultBlockState(), 0);
                }
            }
        }

        // Put one or two cane clumps on actual wet edges.
        int canePlaced = 0;
        for (int dz = -2; dz <= 2 && canePlaced < 2; ++dz) {
            for (int dx = -2; dx <= 2 && canePlaced < 2; ++dx) {
                final int localX = centerX + dx;
                final int localZ = centerZ + dz;
                final int localIndex = (localZ << 4) | localX;
                above.set(minX + localX, FLOOD_LEVEL + 1, minZ + localZ);
                surface.set(minX + localX, FLOOD_LEVEL, minZ + localZ);

                if (!chunk.getBlockState(above).isAir()
                    || !isSugarCaneGround(chunk.getBlockState(surface))
                    || !hasChunkLocalWaterNeighbor(chunk, minX, minZ, localX, localZ)) {
                    continue;
                }

                final long caneHash = shorelineHash(chunk.getPos(), localIndex ^ 0x3E3E);
                if (canePlaced == 0 || Math.floorMod(caneHash, 3L) == 0L) {
                    placeSugarCaneColumn(chunk, minX, minZ, localX, localZ, caneHash);
                    ++canePlaced;
                }
            }
        }

        decorateVegetatedShorelineIslet(level, chunk, minX, minZ, centerX, centerZ, bestIndex);
    }

    private static void decorateVegetatedShorelineIslet(
        final WorldGenLevel level,
        final ChunkAccess chunk,
        final int minX,
        final int minZ,
        final int centerX,
        final int centerZ,
        final int seedIndex
    ) {
        final BlockPos.MutableBlockPos pos = new BlockPos.MutableBlockPos();
        final BlockPos.MutableBlockPos ground = new BlockPos.MutableBlockPos();
        pos.set(minX + centerX, FLOOD_LEVEL + 1, minZ + centerZ);
        final String biome = level.getBiome(pos).unwrapKey()
            .map(key -> key.identifier().toString())
            .orElse("");
        final boolean swamp = "minecraft:swamp".equals(biome)
            || "minecraft:mangrove_swamp".equals(biome);
        final boolean frozen = "minecraft:frozen_river".equals(biome);

        int decorated = 0;
        for (int dz = -1; dz <= 1 && decorated < 4; ++dz) {
            for (int dx = -1; dx <= 1 && decorated < 4; ++dx) {
                final int localX = centerX + dx;
                final int localZ = centerZ + dz;
                final int localIndex = (localZ << 4) | localX;
                pos.set(minX + localX, FLOOD_LEVEL + 1, minZ + localZ);
                ground.set(minX + localX, FLOOD_LEVEL, minZ + localZ);
                if (!chunk.getBlockState(pos).isAir()
                    || !chunk.getBlockState(ground).is(Blocks.GRASS_BLOCK)) {
                    continue;
                }

                final long floraHash = shorelineHash(chunk.getPos(), localIndex ^ seedIndex ^ 0x5151);
                if (Math.floorMod(floraHash, 3L) == 0L) {
                    continue;
                }

                if (frozen) {
                    // Keep frozen-river islets restrained rather than flowering.
                    if (Math.floorMod(floraHash, 4L) == 0L) {
                        chunk.setBlockState(pos, Blocks.FERN.defaultBlockState(), 0);
                        ++decorated;
                    }
                    continue;
                }

                if (swamp) {
                    chunk.setBlockState(
                        pos,
                        Math.floorMod(floraHash, 3L) == 0L
                            ? Blocks.BLUE_ORCHID.defaultBlockState()
                            : Blocks.FERN.defaultBlockState(),
                        0
                    );
                } else {
                    final int flower = (int)Math.floorMod(floraHash, 3L);
                    chunk.setBlockState(
                        pos,
                        flower == 0
                            ? Blocks.DANDELION.defaultBlockState()
                            : (flower == 1
                                ? Blocks.POPPY.defaultBlockState()
                                : Blocks.SHORT_GRASS.defaultBlockState()),
                        0
                    );
                }
                ++decorated;
            }
        }

        // One optional lily pad just off the island edge.
        final int[][] offsets = {{3, 0}, {-3, 0}, {0, 3}, {0, -3}};
        final int start = (int)Math.floorMod(shorelineHash(chunk.getPos(), seedIndex ^ 0x6262), 4L);
        for (int i = 0; i < offsets.length; ++i) {
            final int[] offset = offsets[(start + i) & 3];
            final int localX = centerX + offset[0];
            final int localZ = centerZ + offset[1];
            if (localX < 1 || localX > 14 || localZ < 1 || localZ > 14) {
                continue;
            }
            pos.set(minX + localX, FLOOD_LEVEL + 1, minZ + localZ);
            ground.set(minX + localX, FLOOD_LEVEL, minZ + localZ);
            if (chunk.getBlockState(pos).isAir() && chunk.getBlockState(ground).is(Blocks.WATER)) {
                if (Math.floorMod(shorelineHash(chunk.getPos(), seedIndex ^ 0x7373), 2L) == 0L) {
                    chunk.setBlockState(pos, Blocks.LILY_PAD.defaultBlockState(), 0);
                }
                break;
            }
        }
    }

'''


def fail(message: str) -> None:
    raise SystemExit(f'[NeverFolia][shoreline vegetated islet] {message}')


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
        'localX = 3; localX <= 12',
        'localZ = 3; localZ <= 12',
        'clearWater < 16',
        'Blocks.GRASS_BLOCK',
        'Blocks.SAND',
        'rootDepth = distanceSq == 0 ? 3',
        'decorateVegetatedShorelineIslet',
        'Blocks.BLUE_ORCHID',
        'Blocks.FERN',
        'Blocks.DANDELION',
        'Blocks.POPPY',
        'Blocks.SHORT_GRASS',
        'Blocks.LILY_PAD',
        'createSparseVegetatedShorelineIslet(level, chunk, minX, minZ)',
        'hasChunkLocalWaterNeighbor(chunk, minX, minZ, localX, localZ)',
        'isSugarCaneBiome(level, above)',
    )
    missing = [marker for marker in required if marker not in text]
    if missing:
        fail(f'missing islet markers: {missing}')
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
    print('[NeverFolia][shoreline vegetated islet] tiny deterministic islet fallback applied')
    print('  density: ~1/16 eligible river/swamp chunks, only when natural relocation failed')
    print('  cap: irregular ~5x5 grass/sand shoreline at Y=128 with tapered dirt root')
    print('  flora: 1-2 cane clumps + biome-appropriate flowers/ferns + optional lily pad')
    print('  ownership: centre 3..12, all reads/writes remain inside the owning chunk')


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
    private static boolean isSugarCaneGround(BlockState state) { return true; }
    private static boolean hasChunkLocalWaterNeighbor(ChunkAccess chunk, int minX, int minZ, int localX, int localZ) { return true; }
    private static long shorelineHash(Object pos, int index) { return 0L; }
    private static void placeSugarCaneColumn(ChunkAccess chunk, int minX, int minZ, int localX, int localZ, long hash) {}
}
'''
    with tempfile.TemporaryDirectory(prefix='nr-shoreline-vegetated-islet-') as tmp:
        root = Path(tmp)
        helper = root / HELPER_REL
        helper.parent.mkdir(parents=True, exist_ok=True)
        helper.write_text(fixture, encoding='utf-8')
        text = patch(helper.read_text(encoding='utf-8'))
        validate(text)
        helper.write_text(text, encoding='utf-8')
        if 'Math.floorMod(chunkHash, 4L)' in text:
            fail('SELF-TEST: obsolete 1/4 pillar density survived')
        if 'three-block-deep maximum root/hummock' in text:
            fail('SELF-TEST: obsolete pillar/hummock implementation survived')
    print('[NeverFolia][shoreline vegetated islet] SELF-TEST OK')


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
    self_test()
    apply(args.folia_root.resolve())


if __name__ == '__main__':
    main()
