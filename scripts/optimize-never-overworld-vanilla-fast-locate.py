#!/usr/bin/env python3
from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

HELPER_REL = Path(
    'folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldVanillaFastLocate.java'
)

OLD_IMPORT = 'import net.minecraft.world.level.levelgen.Heightmap;\n'
NEW_IMPORT = 'import net.minecraft.world.level.levelgen.DensityFunction;\n'

OLD_PROBE = '''                final int base = generator.getBaseHeight(
                    centerX + dx,
                    centerZ + dz,
                    Heightmap.Types.WORLD_SURFACE_WG,
                    level,
                    state.randomState()
                );
                if (base < MIN_DRY_BASE_HEIGHT) {
                    return false;
                }
'''

NEW_PROBE = '''                final int base = preliminarySurfaceY(
                    state,
                    centerX + dx,
                    centerZ + dz
                );
                if (base < MIN_DRY_BASE_HEIGHT) {
                    return false;
                }
'''

PASSES_BIOME_MARKER = '    private static boolean passesBiome(\n'

SURFACE_HELPER = '''    /**
     * Matches NoiseChunk#computePreliminarySurfaceLevel without allocating or
     * scanning a 1024-block NoiseColumn. The router density is evaluated once at
     * the requested X/Z and floored exactly like NoiseChunk does internally.
     */
    private static int preliminarySurfaceY(
        final ChunkGeneratorStructureState state,
        final int blockX,
        final int blockZ
    ) {
        final double estimated = state.randomState()
            .router()
            .preliminarySurfaceLevel()
            .compute(new DensityFunction.SinglePointContext(blockX, 0, blockZ));
        if (!Double.isFinite(estimated)) {
            return Integer.MIN_VALUE;
        }
        return (int)Math.floor(estimated);
    }

'''

REQUIRED = (
    'DensityFunction.SinglePointContext',
    '.router()',
    '.preliminarySurfaceLevel()',
    'preliminarySurfaceY(',
    'Double.isFinite',
)

FORBIDDEN = (
    'generator.getBaseHeight(',
    'Heightmap.Types.WORLD_SURFACE_WG',
    'moonrise$syncLoadNonFull',
    'getChunk(',
)


def optimize_text(text: str) -> str:
    if 'DensityFunction.SinglePointContext' in text and '.preliminarySurfaceLevel()' in text:
        return text

    if OLD_IMPORT not in text:
        raise SystemExit('[NeverFolia][vanilla fast locate surface] Heightmap import marker not found')
    if OLD_PROBE not in text:
        raise SystemExit('[NeverFolia][vanilla fast locate surface] getBaseHeight footprint marker not found')
    if PASSES_BIOME_MARKER not in text:
        raise SystemExit('[NeverFolia][vanilla fast locate surface] passesBiome insertion marker not found')

    text = text.replace(OLD_IMPORT, NEW_IMPORT, 1)
    text = text.replace(OLD_PROBE, NEW_PROBE, 1)
    text = text.replace(PASSES_BIOME_MARKER, SURFACE_HELPER + PASSES_BIOME_MARKER, 1)
    return text


def validate(text: str) -> None:
    missing = [marker for marker in REQUIRED if marker not in text]
    if missing:
        raise SystemExit(f'[NeverFolia][vanilla fast locate surface] missing markers: {missing}')
    leaked = [marker for marker in FORBIDDEN if marker in text]
    if leaked:
        raise SystemExit(f'[NeverFolia][vanilla fast locate surface] expensive/chunk-loading primitive leaked: {leaked}')


def apply(root: Path) -> None:
    helper = root / HELPER_REL
    if not helper.is_file():
        raise SystemExit(f'NeverOverworld vanilla fast-locate helper not found: {helper}')

    text = optimize_text(helper.read_text(encoding='utf-8'))
    validate(text)
    helper.write_text(text, encoding='utf-8')

    print('[NeverFolia][NeverOverworld vanilla fast locate] preliminary-surface optimization applied')
    print(f'  helper: {helper}')
    print('  dry footprint: 25 single-point preliminarySurfaceLevel evaluations; zero vertical column scans')


def self_test() -> None:
    fixture = '''package net.minecraft.world.level.chunk;
import net.minecraft.world.level.levelgen.Heightmap;
final class NeverOverworldVanillaFastLocate {
    private static final int MIN_DRY_BASE_HEIGHT = 129;
    private static boolean probe(ChunkGenerator generator, ServerLevel level, ChunkGeneratorStructureState state, int centerX, int centerZ) {
        final int[] offsets = {-96, -48, 0, 48, 96};
        for (final int dx : offsets) {
            for (final int dz : offsets) {
                final int base = generator.getBaseHeight(
                    centerX + dx,
                    centerZ + dz,
                    Heightmap.Types.WORLD_SURFACE_WG,
                    level,
                    state.randomState()
                );
                if (base < MIN_DRY_BASE_HEIGHT) {
                    return false;
                }
            }
        }
        return true;
    }

    private static boolean passesBiome(
        ChunkGenerator generator,
        ChunkGeneratorStructureState state,
        ChunkPos chunkPos,
        Holder structureHolder
    ) { return true; }
}
'''
    with tempfile.TemporaryDirectory(prefix='nr-vanilla-fast-locate-surface-') as tmp:
        root = Path(tmp)
        helper = root / HELPER_REL
        helper.parent.mkdir(parents=True, exist_ok=True)
        helper.write_text(fixture, encoding='utf-8')
        apply(root)
        optimized = helper.read_text(encoding='utf-8')
        validate(optimized)
        if optimized.count('preliminarySurfaceY(') != 2:
            raise SystemExit('[NeverFolia][vanilla fast locate surface self-test] expected one call and one helper definition')
        if 'new DensityFunction.SinglePointContext(blockX, 0, blockZ)' not in optimized:
            raise SystemExit('[NeverFolia][vanilla fast locate surface self-test] single-point context mismatch')
    print('[NeverFolia][NeverOverworld vanilla fast locate surface] SELF-TEST OK')


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
