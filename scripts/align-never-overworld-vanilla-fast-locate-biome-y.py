#!/usr/bin/env python3
from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

HELPER_REL = Path(
    'folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldVanillaFastLocate.java'
)

OLD = '''        final Holder<Biome> biome = generator.getBiomeSource().getNoiseBiome(
            QuartPos.fromBlock(blockX),
            QuartPos.fromBlock(FLOOD_LEVEL),
            QuartPos.fromBlock(blockZ),
            state.randomState().sampler()
        );
'''

NEW = '''        // Structure#findValidGenerationPoint validates the biome at the
        // generation stub Y, not at the flood plane. For surface structures the
        // cheap preliminary surface is the closest no-generation predictor of
        // that Y and avoids falsely rejecting high dry candidates whose 3D biome
        // differs at Y=128.
        final int biomeY = preliminarySurfaceY(state, blockX, blockZ);
        if (biomeY == Integer.MIN_VALUE) {
            return false;
        }
        final Holder<Biome> biome = generator.getBiomeSource().getNoiseBiome(
            QuartPos.fromBlock(blockX),
            QuartPos.fromBlock(biomeY),
            QuartPos.fromBlock(blockZ),
            state.randomState().sampler()
        );
'''


def patch(text: str) -> str:
    if 'QuartPos.fromBlock(biomeY)' in text:
        return text
    if OLD not in text:
        raise SystemExit('[NeverFolia][vanilla fast locate biome-y] fixed-Y biome marker not found')
    text = text.replace(OLD, NEW, 1)
    if text.count('QuartPos.fromBlock(biomeY)') != 1:
        raise SystemExit('[NeverFolia][vanilla fast locate biome-y] biome-Y replacement count mismatch')
    return text


def validate(text: str) -> None:
    required = (
        'final int biomeY = preliminarySurfaceY(state, blockX, blockZ);',
        'biomeY == Integer.MIN_VALUE',
        'QuartPos.fromBlock(biomeY)',
        'structureHolder.value().biomes().contains(biome)',
    )
    missing = [marker for marker in required if marker not in text]
    if missing:
        raise SystemExit(f'[NeverFolia][vanilla fast locate biome-y] missing markers: {missing}')
    if 'QuartPos.fromBlock(FLOOD_LEVEL)' in text:
        raise SystemExit('[NeverFolia][vanilla fast locate biome-y] fixed flood-plane biome probe leaked')


def apply(root: Path) -> None:
    helper = root / HELPER_REL
    if not helper.is_file():
        raise SystemExit(f'NeverOverworld vanilla fast-locate helper not found: {helper}')
    text = patch(helper.read_text(encoding='utf-8'))
    validate(text)
    helper.write_text(text, encoding='utf-8')
    print('[NeverFolia][NeverOverworld vanilla fast locate] biome probe aligned to predicted surface Y')
    print(f'  helper: {helper}')


def self_test() -> None:
    fixture = '''final class NeverOverworldVanillaFastLocate {
    static int preliminarySurfaceY(Object state, int x, int z) { return 150; }
    private static boolean passesBiome(Object generator, Object state, Object chunkPos, Object structureHolder) {
        final int blockX = chunkPos.getMiddleBlockX();
        final int blockZ = chunkPos.getMiddleBlockZ();
        final Holder<Biome> biome = generator.getBiomeSource().getNoiseBiome(
            QuartPos.fromBlock(blockX),
            QuartPos.fromBlock(FLOOD_LEVEL),
            QuartPos.fromBlock(blockZ),
            state.randomState().sampler()
        );
        return structureHolder.value().biomes().contains(biome);
    }
}
'''
    with tempfile.TemporaryDirectory(prefix='nr-vanilla-fast-locate-biome-y-') as tmp:
        root = Path(tmp)
        helper = root / HELPER_REL
        helper.parent.mkdir(parents=True, exist_ok=True)
        helper.write_text(fixture, encoding='utf-8')
        apply(root)
        validate(helper.read_text(encoding='utf-8'))
    print('[NeverFolia][NeverOverworld vanilla fast locate biome-y] SELF-TEST OK')


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
