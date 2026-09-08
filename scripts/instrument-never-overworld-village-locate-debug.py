#!/usr/bin/env python3
from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

HELPER_REL = Path(
    'folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldVanillaFastLocate.java'
)

POLICY_SIG = '    private static boolean passesNeverOverworldPolicy('
RING_MARKER = '    private static final int MAX_CANDIDATE_RINGS = 64;\n'
DEBUG_MARKER = '    private static final boolean DEBUG_VILLAGE_LOCATE = Boolean.getBoolean("neverfolia.debugVillageLocate");'

DEBUG_SUPPORT = r'''    private static final boolean DEBUG_VILLAGE_LOCATE = Boolean.getBoolean("neverfolia.debugVillageLocate");
    private static final int DEBUG_VILLAGE_LIMIT = 48;
    private static final java.util.concurrent.ConcurrentHashMap<String, java.util.concurrent.atomic.AtomicInteger> DEBUG_VILLAGE_COUNTS =
        new java.util.concurrent.ConcurrentHashMap<>();

    private static void debugVillage(
        final String id,
        final String reason,
        final ChunkPos chunkPos,
        final int centerSurfaceY,
        final String detail
    ) {
        if (!DEBUG_VILLAGE_LOCATE || id == null || !id.startsWith("minecraft:village_")) {
            return;
        }
        final String key = id + "|" + reason;
        final int seen = DEBUG_VILLAGE_COUNTS
            .computeIfAbsent(key, ignored -> new java.util.concurrent.atomic.AtomicInteger())
            .incrementAndGet();
        if (seen > DEBUG_VILLAGE_LIMIT) {
            return;
        }
        System.err.println(
            "[NeverFolia][VillageLocateDebug] id=" + id
                + " reason=" + reason
                + " chunk=" + chunkPos.x() + "," + chunkPos.z()
                + " centerY=" + centerSurfaceY
                + " detail=" + detail
                + " sample=" + seen
        );
    }

    private static void debugVillageSearch(final Set<String> wantedIds, final String reason) {
        if (!DEBUG_VILLAGE_LOCATE) {
            return;
        }
        for (final String id : wantedIds) {
            if (id != null && id.startsWith("minecraft:village_")) {
                System.err.println(
                    "[NeverFolia][VillageLocateDebug] id=" + id
                        + " reason=" + reason
                        + " chunk=NA centerY=NA detail=search"
                );
            }
        }
    }

'''

NEW_POLICY = r'''    private static boolean passesNeverOverworldPolicy(
        final ChunkGenerator generator,
        final ServerLevel level,
        final ChunkGeneratorStructureState state,
        final ChunkPos chunkPos,
        final Holder<Structure> structureHolder,
        final String id
    ) {
        if (SWAMP_HUT.equals(id)) {
            return passesBiomeAtY(generator, state, chunkPos, structureHolder, FLOOD_LEVEL + 1);
        }
        if (!DRY_LAND_ONLY.contains(id)) {
            return false;
        }

        final int centerX = chunkPos.getMiddleBlockX();
        final int centerZ = chunkPos.getMiddleBlockZ();
        final int centerSurfaceY = preliminarySurfaceY(state, centerX, centerZ);
        if (centerSurfaceY < MIN_DRY_BASE_HEIGHT) {
            debugVillage(id, "CENTER_DRY_REJECT", chunkPos, centerSurfaceY, "min=" + MIN_DRY_BASE_HEIGHT);
            return false;
        }
        if (!passesBiomeAtY(generator, state, chunkPos, structureHolder, centerSurfaceY)) {
            debugVillage(id, "BIOME_REJECT", chunkPos, centerSurfaceY, "biomeY=" + centerSurfaceY);
            return false;
        }

        final int radius = sampleRadius(id);
        if (id.startsWith("minecraft:village_")) {
            // Final candidate contract at this stage: dense 5x5, fixed radius32.
            // Debugging is opt-in and does not alter the production decision.
            final int villageRadius = 32;
            final int halfRadius = 16;
            final int[] villageOffsets = {-villageRadius, -halfRadius, 0, halfRadius, villageRadius};
            for (final int dx : villageOffsets) {
                for (final int dz : villageOffsets) {
                    if (dx == 0 && dz == 0) {
                        continue;
                    }
                    final int probeSurfaceY = preliminarySurfaceY(state, centerX + dx, centerZ + dz);
                    if (probeSurfaceY < MIN_DRY_BASE_HEIGHT) {
                        debugVillage(
                            id,
                            "FOOTPRINT_DRY_REJECT",
                            chunkPos,
                            centerSurfaceY,
                            "dx=" + dx + ",dz=" + dz + ",probeY=" + probeSurfaceY
                        );
                        return false;
                    }
                }
            }
            debugVillage(id, "ACCEPT", chunkPos, centerSurfaceY, "dense5x5-radius32");
            return true;
        }

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

SETS_EMPTY_OLD = '''        if (sets.isEmpty()) {
            return null;
        }
'''
SETS_EMPTY_NEW = '''        if (sets.isEmpty()) {
            debugVillageSearch(wantedIds, "NO_RELEVANT_SET");
            return null;
        }
'''

SEARCH_END_OLD = '''        }
        return null;
    }

    private static List<SetRef> collectRelevantSets('''
SEARCH_END_NEW = '''        }
        debugVillageSearch(wantedIds, "EXHAUSTED");
        return null;
    }

    private static List<SetRef> collectRelevantSets('''


def fail(message: str) -> None:
    raise SystemExit(f'[NeverFolia][village locate debug] {message}')


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
    if DEBUG_MARKER in text:
        validate(text)
        return text
    if text.count(RING_MARKER) != 1:
        fail(f'expected one bounded-ring marker, got {text.count(RING_MARKER)}')
    if 'final int villageRadius = 32;' not in text:
        fail('radius32 dense village contract is not present before instrumentation')
    if 'final int[] villageOffsets = {-villageRadius, -halfRadius, 0, halfRadius, villageRadius};' not in text:
        fail('dense village offset marker missing before instrumentation')

    text = text.replace(RING_MARKER, RING_MARKER + DEBUG_SUPPORT, 1)
    text = replace_method(text, POLICY_SIG, NEW_POLICY)

    if text.count(SETS_EMPTY_OLD) != 1:
        fail(f'expected one sets-empty block, got {text.count(SETS_EMPTY_OLD)}')
    text = text.replace(SETS_EMPTY_OLD, SETS_EMPTY_NEW, 1)

    if text.count(SEARCH_END_OLD) != 1:
        fail(f'expected one search terminal block, got {text.count(SEARCH_END_OLD)}')
    text = text.replace(SEARCH_END_OLD, SEARCH_END_NEW, 1)
    validate(text)
    return text


def validate(text: str) -> None:
    required = (
        DEBUG_MARKER,
        'Boolean.getBoolean("neverfolia.debugVillageLocate")',
        '+ " reason=" + reason',
        '"CENTER_DRY_REJECT"',
        '"BIOME_REJECT"',
        '"FOOTPRINT_DRY_REJECT"',
        '"ACCEPT"',
        'debugVillageSearch(wantedIds, "NO_RELEVANT_SET")',
        'debugVillageSearch(wantedIds, "EXHAUSTED")',
        'final int villageRadius = 32;',
        'final int halfRadius = 16;',
        'final int[] villageOffsets = {-villageRadius, -halfRadius, 0, halfRadius, villageRadius};',
    )
    missing = [marker for marker in required if marker not in text]
    if missing:
        fail(f'missing debug markers: {missing}')
    if text.count(DEBUG_MARKER) != 1:
        fail('debug flag definition count mismatch')
    if text.count(POLICY_SIG) != 1:
        fail('policy method definition count mismatch')


def apply(root: Path) -> None:
    helper = root / HELPER_REL
    if not helper.is_file():
        fail(f'helper not found: {helper}')
    helper.write_text(patch(helper.read_text(encoding='utf-8')), encoding='utf-8')
    print('[NeverFolia][village locate debug] optional rejection diagnostics installed')
    print('  default: disabled')
    print('  QA enable: -Dneverfolia.debugVillageLocate=true')
    print('  reasons: CENTER_DRY_REJECT, BIOME_REJECT, FOOTPRINT_DRY_REJECT, ACCEPT, EXHAUSTED')


def fixture() -> str:
    return r'''package net.minecraft.world.level.chunk;
import java.util.List;
import java.util.Set;
final class NeverOverworldVanillaFastLocate {
    private static final int MAX_CANDIDATE_RINGS = 64;
    private static final int FLOOD_LEVEL = 128;
    private static final int MIN_DRY_BASE_HEIGHT = 129;
    private static final String SWAMP_HUT = "minecraft:swamp_hut";
    private static final Set<String> DRY_LAND_ONLY = Set.of("minecraft:village_plains");

    static Object find(Set<String> wantedIds) {
        final List<String> sets = List.of("x");
        if (sets.isEmpty()) {
            return null;
        }
        for (int radius = 0; radius <= 1; ++radius) {
        }
        return null;
    }

    private static List<SetRef> collectRelevantSets(
        final ChunkGeneratorStructureState state,
        final Set<String> wantedIds
    ) {
        return List.of();
    }

    private static boolean passesNeverOverworldPolicy(
        final ChunkGenerator generator,
        final ServerLevel level,
        final ChunkGeneratorStructureState state,
        final ChunkPos chunkPos,
        final Holder<Structure> structureHolder,
        final String id
    ) {
        if (SWAMP_HUT.equals(id)) return true;
        if (!DRY_LAND_ONLY.contains(id)) return false;
        final int centerX = chunkPos.getMiddleBlockX();
        final int centerZ = chunkPos.getMiddleBlockZ();
        final int centerSurfaceY = preliminarySurfaceY(state, centerX, centerZ);
        if (centerSurfaceY < MIN_DRY_BASE_HEIGHT) return false;
        if (!passesBiomeAtY(generator, state, chunkPos, structureHolder, centerSurfaceY)) return false;
        final int radius = sampleRadius(id);
        if (id.startsWith("minecraft:village_")) {
            final int villageRadius = 32;
            final int halfRadius = 16;
            final int[] villageOffsets = {-villageRadius, -halfRadius, 0, halfRadius, villageRadius};
            for (final int dx : villageOffsets) for (final int dz : villageOffsets) {
                if (dx == 0 && dz == 0) continue;
                if (preliminarySurfaceY(state, centerX + dx, centerZ + dz) < MIN_DRY_BASE_HEIGHT) return false;
            }
            return true;
        }
        return radius > 0;
    }

    private static int sampleRadius(String id) { return 48; }
    private static int preliminarySurfaceY(Object state, int x, int z) { return 140; }
    private static boolean passesBiomeAtY(Object a, Object b, Object c, Object d, int y) { return true; }
    private record SetRef() {}
}
'''


def self_test() -> None:
    with tempfile.TemporaryDirectory(prefix='nr-village-locate-debug-') as tmp:
        root = Path(tmp)
        helper = root / HELPER_REL
        helper.parent.mkdir(parents=True, exist_ok=True)
        helper.write_text(fixture(), encoding='utf-8')
        first = patch(helper.read_text(encoding='utf-8'))
        validate(first)
        second = patch(first)
        if second != first:
            fail('SELF-TEST: idempotent reapply changed output')
    print('[NeverFolia][village locate debug] SELF-TEST OK')


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
