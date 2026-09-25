#!/usr/bin/env python3
from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

HELPER_REL = Path(
    'folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldVanillaFastLocate.java'
)

POLICY_SIG = '    private static boolean passesNeverOverworldPolicy('
BIOME_SIG = '    private static boolean passesBiome('
OLD_RING = '    private static final int MAX_CANDIDATE_RINGS = 256;'
NEW_RING = '    private static final int MAX_CANDIDATE_RINGS = 64;'

NEW_POLICY = '''    private static boolean passesNeverOverworldPolicy(
        final ChunkGenerator generator,
        final ServerLevel level,
        final ChunkGeneratorStructureState state,
        final ChunkPos chunkPos,
        final Holder<Structure> structureHolder,
        final String id
    ) {
        // Swamp huts are flood-adapted at generation time, so they only need a
        // cheap biome check at the new waterline. Do not evaluate surface density.
        if (SWAMP_HUT.equals(id)) {
            return passesBiomeAtY(generator, state, chunkPos, structureHolder, FLOOD_LEVEL + 1);
        }
        if (!DRY_LAND_ONLY.contains(id)) {
            return false;
        }

        // Reject the overwhelmingly common submerged candidates before biome
        // lookup or footprint work. The old implementation evaluated the same
        // expensive preliminary-surface density twice per candidate: once in
        // passesBiome() and again for the dry center. That was enough to trip the
        // Folia global-region watchdog during village locate scans.
        final int centerX = chunkPos.getMiddleBlockX();
        final int centerZ = chunkPos.getMiddleBlockZ();
        final int centerSurfaceY = preliminarySurfaceY(state, centerX, centerZ);
        if (centerSurfaceY < MIN_DRY_BASE_HEIGHT) {
            return false;
        }
        if (!passesBiomeAtY(generator, state, chunkPos, structureHolder, centerSurfaceY)) {
            return false;
        }

        // Keep the same field-r2 3x3 dry-footprint contract as real generation,
        // but only pay for the remaining eight probes after the center is already
        // known to be dry and the biome is valid.
        final int radius = sampleRadius(id);
        int drySamples = 1;
        final int[] offsets = {-radius, 0, radius};
        for (final int dx : offsets) {
            for (final int dz : offsets) {
                if (dx == 0 && dz == 0) {
                    continue;
                }
                if (preliminarySurfaceY(state, centerX + dx, centerZ + dz) >= MIN_DRY_BASE_HEIGHT) {
                    ++drySamples;
                }
            }
        }
        return drySamples >= minDrySamples(id);
    }
'''

NEW_BIOME = '''    private static boolean passesBiomeAtY(
        final ChunkGenerator generator,
        final ChunkGeneratorStructureState state,
        final ChunkPos chunkPos,
        final Holder<Structure> structureHolder,
        final int biomeY
    ) {
        final int blockX = chunkPos.getMiddleBlockX();
        final int blockZ = chunkPos.getMiddleBlockZ();
        final Holder<Biome> biome = generator.getBiomeSource().getNoiseBiome(
            QuartPos.fromBlock(blockX),
            QuartPos.fromBlock(biomeY),
            QuartPos.fromBlock(blockZ),
            state.randomState().sampler()
        );
        return structureHolder.value().biomes().contains(biome);
    }
'''


def fail(message: str) -> None:
    raise SystemExit(f'[NeverFolia][bounded vanilla locate] {message}')


def find_method_end(text: str, signature: str) -> tuple[int, int]:
    start = text.find(signature)
    if start < 0:
        fail(f'method signature not found: {signature.strip()}')
    if text.find(signature, start + 1) >= 0:
        fail(f'method signature occurs more than once: {signature.strip()}')
    opening = text.find('{', start)
    if opening < 0:
        fail(f'opening brace not found: {signature.strip()}')

    depth = 0
    in_string = False
    in_char = False
    in_line_comment = False
    in_block_comment = False
    escaped = False
    i = opening
    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ''
        if in_line_comment:
            if ch == '\n':
                in_line_comment = False
            i += 1
            continue
        if in_block_comment:
            if ch == '*' and nxt == '/':
                in_block_comment = False
                i += 2
            else:
                i += 1
            continue
        if in_string:
            if escaped:
                escaped = False
            elif ch == '\\':
                escaped = True
            elif ch == '"':
                in_string = False
            i += 1
            continue
        if in_char:
            if escaped:
                escaped = False
            elif ch == '\\':
                escaped = True
            elif ch == "'":
                in_char = False
            i += 1
            continue
        if ch == '/' and nxt == '/':
            in_line_comment = True
            i += 2
            continue
        if ch == '/' and nxt == '*':
            in_block_comment = True
            i += 2
            continue
        if ch == '"':
            in_string = True
            i += 1
            continue
        if ch == "'":
            in_char = True
            i += 1
            continue
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                end = i + 1
                if end < len(text) and text[end] == '\n':
                    end += 1
                return start, end
        i += 1
    fail(f'unterminated method: {signature.strip()}')


def replace_method(text: str, signature: str, replacement: str) -> str:
    start, end = find_method_end(text, signature)
    return text[:start] + replacement + text[end:]


def patch(text: str) -> str:
    if NEW_RING in text and 'passesBiomeAtY(' in text and 'centerSurfaceY' in text:
        return text
    if text.count(OLD_RING) != 1:
        fail(f'expected one legacy ring cap, got {text.count(OLD_RING)}')
    text = text.replace(OLD_RING, NEW_RING, 1)
    text = replace_method(text, POLICY_SIG, NEW_POLICY)
    text = replace_method(text, BIOME_SIG, NEW_BIOME)
    return text


def validate(text: str) -> None:
    required = (
        NEW_RING,
        'final int centerSurfaceY = preliminarySurfaceY(state, centerX, centerZ);',
        'passesBiomeAtY(generator, state, chunkPos, structureHolder, centerSurfaceY)',
        'passesBiomeAtY(generator, state, chunkPos, structureHolder, FLOOD_LEVEL + 1)',
        'return drySamples >= minDrySamples(id);',
    )
    missing = [marker for marker in required if marker not in text]
    if missing:
        fail(f'missing optimized markers: {missing}')
    if POLICY_SIG not in text:
        fail('optimized policy method disappeared')
    if BIOME_SIG in text:
        fail('legacy passesBiome method survived')
    if text.count('    private static boolean passesBiomeAtY(') != 1:
        fail('passesBiomeAtY definition count mismatch')
    policy_start, policy_end = find_method_end(text, POLICY_SIG)
    policy = text[policy_start:policy_end]
    if policy.count('preliminarySurfaceY(state, centerX, centerZ)') != 1:
        fail('dry center is not evaluated exactly once')
    dry_biome_call = 'passesBiomeAtY(generator, state, chunkPos, structureHolder, centerSurfaceY)'
    if policy.find('centerSurfaceY < MIN_DRY_BASE_HEIGHT') > policy.find(dry_biome_call):
        fail('dry biome validation occurs before cheap dry-center rejection')


def apply(root: Path) -> None:
    helper = root / HELPER_REL
    if not helper.is_file():
        fail(f'helper not found: {helper}')
    text = patch(helper.read_text(encoding='utf-8'))
    validate(text)
    helper.write_text(text, encoding='utf-8')
    print('[NeverFolia][bounded vanilla locate] flooded locate cost guard applied')
    print('  max candidate rings: 64')
    print('  submerged candidate: one preliminary-surface probe, zero biome lookups')
    print('  dry candidate: center probe reused for biome validation')


def self_test() -> None:
    fixture = '''package net.minecraft.world.level.chunk;
final class NeverOverworldVanillaFastLocate {
    private static final int MAX_CANDIDATE_RINGS = 256;
    private static final int FLOOD_LEVEL = 128;
    private static final int MIN_DRY_BASE_HEIGHT = 129;
    private static final String SWAMP_HUT = "minecraft:swamp_hut";
    private static final java.util.Set<String> DRY_LAND_ONLY = java.util.Set.of("minecraft:village_plains");

    private static boolean passesNeverOverworldPolicy(
        final ChunkGenerator generator,
        final ServerLevel level,
        final ChunkGeneratorStructureState state,
        final ChunkPos chunkPos,
        final Holder<Structure> structureHolder,
        final String id
    ) {
        if (!passesBiome(generator, state, chunkPos, structureHolder)) return false;
        if (SWAMP_HUT.equals(id)) return true;
        if (!DRY_LAND_ONLY.contains(id)) return false;
        final int radius = sampleRadius(id);
        final int centerX = chunkPos.getMiddleBlockX();
        final int centerZ = chunkPos.getMiddleBlockZ();
        if (preliminarySurfaceY(state, centerX, centerZ) < MIN_DRY_BASE_HEIGHT) return false;
        int drySamples = 1;
        final int[] offsets = {-radius, 0, radius};
        for (final int dx : offsets) {
            for (final int dz : offsets) {
                if (dx == 0 && dz == 0) continue;
                if (preliminarySurfaceY(state, centerX + dx, centerZ + dz) >= MIN_DRY_BASE_HEIGHT) ++drySamples;
            }
        }
        return drySamples >= minDrySamples(id);
    }

    private static int preliminarySurfaceY(final ChunkGeneratorStructureState state, final int x, final int z) { return 140; }

    private static boolean passesBiome(
        final ChunkGenerator generator,
        final ChunkGeneratorStructureState state,
        final ChunkPos chunkPos,
        final Holder<Structure> structureHolder
    ) {
        final int blockX = chunkPos.getMiddleBlockX();
        final int blockZ = chunkPos.getMiddleBlockZ();
        final int biomeY = preliminarySurfaceY(state, blockX, blockZ);
        final Holder<Biome> biome = generator.getBiomeSource().getNoiseBiome(
            QuartPos.fromBlock(blockX), QuartPos.fromBlock(biomeY), QuartPos.fromBlock(blockZ), state.randomState().sampler());
        return structureHolder.value().biomes().contains(biome);
    }
    private static int sampleRadius(String id) { return 48; }
    private static int minDrySamples(String id) { return 7; }
}
'''
    with tempfile.TemporaryDirectory(prefix='nr-bounded-vanilla-locate-') as tmp:
        root = Path(tmp)
        helper = root / HELPER_REL
        helper.parent.mkdir(parents=True, exist_ok=True)
        helper.write_text(fixture, encoding='utf-8')
        apply(root)
        validate(helper.read_text(encoding='utf-8'))
    print('[NeverFolia][bounded vanilla locate] SELF-TEST OK')


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
