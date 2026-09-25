#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import tempfile
from pathlib import Path

CHUNK_REL = Path('folia-server/src/minecraft/java/net/minecraft/world/level/chunk/ChunkGenerator.java')
FAST_REL = Path('folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldVanillaFastLocate.java')
POLICY_REL = Path('folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldVanillaStructurePolicy.java')
SAFETY_REL = Path('folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldGeneratedVillageSafety.java')

GEN_MARKER = '// NeverFolia: validate the actual generated village bbox before persisting the start.'
POLICY_MARKER = '// NeverFolia: village prefilter is center-only; generated bbox safety is authoritative.'
FAST_MARKER = '// NeverFolia: village safety uses the actual deterministic StructureStart bbox.'
FAST_POLICY_SIG = '    private static boolean passesNeverOverworldPolicy('
POLICY_SIG = '    static boolean allows('

SAFETY_HELPER = r'''package net.minecraft.world.level.chunk;

import net.minecraft.core.Holder;
import net.minecraft.resources.ResourceKey;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.level.ChunkPos;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.LevelHeightAccessor;
import net.minecraft.world.level.levelgen.Heightmap;
import net.minecraft.world.level.levelgen.RandomState;
import net.minecraft.world.level.levelgen.structure.BoundingBox;
import net.minecraft.world.level.levelgen.structure.Structure;
import net.minecraft.world.level.levelgen.structure.StructureStart;

/**
 * Exact village safety for the flooded NeverOverworld.
 *
 * <p>Village placement first uses only a cheap dry-centre prefilter. The
 * authoritative runtime decision is made after Structure#generate has produced
 * the deterministic StructureStart, when the real Jigsaw bounding box is known.
 * Every horizontal block column in that actual bounding box must have
 * WORLD_SURFACE_WG base height >= 129, which guarantees the Y=128 flood plane
 * cannot occupy any column later covered by the persisted village bbox.</p>
 *
 * <p>Fast locate calls the same Structure#generate path as a read-only preview
 * with references=0. Structure#generate uses references only when constructing
 * StructureStart metadata; it does not affect Jigsaw piece selection/layout.
 * No chunk loading primitive is used here.</p>
 */
final class NeverOverworldGeneratedVillageSafety {
    private static final int EXPECTED_MIN_Y = -512;
    private static final int EXPECTED_HEIGHT = 1024;
    private static final int MIN_DRY_BASE_HEIGHT = 129;
    private static final int MAX_VILLAGE_BBOX_SPAN = 256;
    private static final long MAX_VILLAGE_BBOX_AREA = 65536L;

    private NeverOverworldGeneratedVillageSafety() {}

    static boolean allowsGenerated(
        final ChunkGenerator generator,
        final Holder<Structure> structureHolder,
        final RandomState randomState,
        final LevelHeightAccessor heightAccessor,
        final StructureStart start,
        final ResourceKey<Level> dimension
    ) {
        if (!isNeverOverworld(dimension, heightAccessor) || !isVillage(structureHolder)) {
            return true;
        }
        if (!start.isValid()) {
            return false;
        }
        return inspectBoundingBox(generator, randomState, heightAccessor, start.getBoundingBox()).dry();
    }

    static Preview preview(
        final ChunkGenerator generator,
        final ServerLevel level,
        final ChunkGeneratorStructureState state,
        final ChunkPos chunkPos,
        final Holder<Structure> structureHolder
    ) {
        if (!isNeverOverworld(level.dimension(), level) || !isVillage(structureHolder)) {
            return Preview.acceptedExternal();
        }

        final Structure structure = structureHolder.value();
        final StructureStart start = structure.generate(
            structureHolder,
            level.dimension(),
            level.registryAccess(),
            generator,
            generator.getBiomeSource(),
            state.randomState(),
            level.getStructureManager(),
            state.getLevelSeed(),
            chunkPos,
            0,
            level,
            structure.biomes()::contains
        );
        if (!start.isValid()) {
            return Preview.invalid();
        }
        return inspectBoundingBox(generator, state.randomState(), level, start.getBoundingBox());
    }

    private static Preview inspectBoundingBox(
        final ChunkGenerator generator,
        final RandomState randomState,
        final LevelHeightAccessor heightAccessor,
        final BoundingBox box
    ) {
        final int minX = box.minX();
        final int minZ = box.minZ();
        final int maxX = box.maxX();
        final int maxZ = box.maxZ();
        final long width = (long)maxX - minX + 1L;
        final long depth = (long)maxZ - minZ + 1L;
        final long area = width * depth;
        if (width <= 0L || depth <= 0L
            || width > MAX_VILLAGE_BBOX_SPAN
            || depth > MAX_VILLAGE_BBOX_SPAN
            || area > MAX_VILLAGE_BBOX_AREA) {
            return Preview.oversized(minX, minZ, maxX, maxZ);
        }

        for (int z = minZ; z <= maxZ; ++z) {
            for (int x = minX; x <= maxX; ++x) {
                final int base = generator.getBaseHeight(
                    x,
                    z,
                    Heightmap.Types.WORLD_SURFACE_WG,
                    heightAccessor,
                    randomState
                );
                if (base < MIN_DRY_BASE_HEIGHT) {
                    return Preview.wet(minX, minZ, maxX, maxZ, x, z, base);
                }
            }
        }
        return Preview.dry(minX, minZ, maxX, maxZ);
    }

    private static boolean isNeverOverworld(
        final ResourceKey<Level> dimension,
        final LevelHeightAccessor heightAccessor
    ) {
        return Level.OVERWORLD.equals(dimension)
            && heightAccessor.getMinY() == EXPECTED_MIN_Y
            && heightAccessor.getHeight() == EXPECTED_HEIGHT;
    }

    private static boolean isVillage(final Holder<Structure> structureHolder) {
        return structureHolder.unwrapKey()
            .map(key -> key.identifier().toString().startsWith("minecraft:village_"))
            .orElse(false);
    }

    static record Preview(
        boolean valid,
        boolean dry,
        int minX,
        int minZ,
        int maxX,
        int maxZ,
        int firstWetX,
        int firstWetZ,
        int firstWetBase,
        String rejection
    ) {
        static Preview acceptedExternal() {
            return new Preview(true, true, 0, 0, 0, 0, 0, 0, Integer.MAX_VALUE, "external");
        }

        static Preview invalid() {
            return new Preview(false, false, 0, 0, 0, 0, 0, 0, Integer.MIN_VALUE, "invalid-start");
        }

        static Preview oversized(final int minX, final int minZ, final int maxX, final int maxZ) {
            return new Preview(true, false, minX, minZ, maxX, maxZ, 0, 0, Integer.MIN_VALUE, "bbox-span-limit");
        }

        static Preview wet(
            final int minX,
            final int minZ,
            final int maxX,
            final int maxZ,
            final int wetX,
            final int wetZ,
            final int wetBase
        ) {
            return new Preview(true, false, minX, minZ, maxX, maxZ, wetX, wetZ, wetBase, "wet-column");
        }

        static Preview dry(final int minX, final int minZ, final int maxX, final int maxZ) {
            return new Preview(true, true, minX, minZ, maxX, maxZ, 0, 0, Integer.MAX_VALUE, "none");
        }

        boolean accepted() {
            return this.valid && this.dry;
        }

        String detail() {
            if (!this.valid) {
                return "invalid-structure-start";
            }
            final String bbox = "bbox=" + this.minX + "," + this.minZ + ".." + this.maxX + "," + this.maxZ;
            if (this.dry) {
                return bbox + ",exact-all-columns-dry";
            }
            if ("wet-column".equals(this.rejection)) {
                return bbox + ",firstWet=" + this.firstWetX + "," + this.firstWetZ + ",base=" + this.firstWetBase;
            }
            return bbox + ",rejection=" + this.rejection;
        }
    }
}
'''

POLICY_METHOD = r'''    static boolean allows(
        final ChunkGenerator generator,
        final Holder<Structure> structure,
        final RandomState randomState,
        final ChunkAccess heightAccessor,
        final ChunkPos chunkPos,
        final ResourceKey<Level> dimension
    ) {
        if (!Level.OVERWORLD.equals(dimension)
            || heightAccessor.getMinY() != EXPECTED_MIN_Y
            || heightAccessor.getHeight() != EXPECTED_HEIGHT) {
            return true;
        }

        final String id = structure.unwrapKey()
            .map(key -> key.identifier().toString())
            .orElse("");
        if ("minecraft:stronghold".equals(id)) {
            return false;
        }
        if (!DRY_LAND_ONLY.contains(id)) {
            return true;
        }

        final int centerX = chunkPos.getMiddleBlockX();
        final int centerZ = chunkPos.getMiddleBlockZ();
        final int centerBase = generator.getBaseHeight(
            centerX,
            centerZ,
            Heightmap.Types.WORLD_SURFACE_WG,
            heightAccessor,
            randomState
        );

        if (id.startsWith("minecraft:village_")) {
            // NeverFolia: village prefilter is center-only; generated bbox safety is authoritative.
            return centerBase >= MIN_DRY_BASE_HEIGHT;
        }
        if (centerBase < MIN_DRY_BASE_HEIGHT) {
            return false;
        }

        final int radius = sampleRadius(id);
        int drySamples = 1;
        final int[] offsets = {-radius, 0, radius};
        for (final int dx : offsets) {
            for (final int dz : offsets) {
                if (dx == 0 && dz == 0) {
                    continue;
                }
                final int base = generator.getBaseHeight(
                    centerX + dx,
                    centerZ + dz,
                    Heightmap.Types.WORLD_SURFACE_WG,
                    heightAccessor,
                    randomState
                );
                if (base >= MIN_DRY_BASE_HEIGHT) {
                    ++drySamples;
                }
            }
        }
        return drySamples >= minDrySamples(id);
    }
'''

FAST_POLICY_METHOD = r'''    private static boolean passesNeverOverworldPolicy(
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

        if (id.startsWith("minecraft:village_")) {
            // NeverFolia: village safety uses the actual deterministic StructureStart bbox.
            final NeverOverworldGeneratedVillageSafety.Preview preview =
                NeverOverworldGeneratedVillageSafety.preview(generator, level, state, chunkPos, structureHolder);
            if (!preview.valid()) {
                debugVillage(id, "LAYOUT_INVALID_REJECT", chunkPos, centerSurfaceY, preview.detail());
                return false;
            }
            if (!preview.dry()) {
                debugVillage(id, "LAYOUT_DRY_REJECT", chunkPos, centerSurfaceY, preview.detail());
                return false;
            }
            debugVillage(id, "ACCEPT", chunkPos, centerSurfaceY, preview.detail());
            return true;
        }

        if (!passesBiomeAtY(generator, state, chunkPos, structureHolder, centerSurfaceY)) {
            return false;
        }

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


def fail(message: str) -> None:
    raise SystemExit(f'[NeverFolia][village layout safety] {message}')


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
            if ch == '\n': in_line_comment = False
            i += 1; continue
        if in_block_comment:
            if ch == '*' and nxt == '/': in_block_comment = False; i += 2
            else: i += 1
            continue
        if in_string:
            if escaped: escaped = False
            elif ch == '\\': escaped = True
            elif ch == '"': in_string = False
            i += 1; continue
        if in_char:
            if escaped: escaped = False
            elif ch == '\\': escaped = True
            elif ch == "'": in_char = False
            i += 1; continue
        if ch == '/' and nxt == '/': in_line_comment = True; i += 2; continue
        if ch == '/' and nxt == '*': in_block_comment = True; i += 2; continue
        if ch == '"': in_string = True; i += 1; continue
        if ch == "'": in_char = True; i += 1; continue
        if ch == '{': depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                end = i + 1
                if end < len(text) and text[end] == '\n': end += 1
                return start, end
        i += 1
    fail(f'unterminated method: {signature.strip()}')


def replace_method(text: str, signature: str, replacement: str) -> str:
    start, end = find_method_end(text, signature)
    return text[:start] + replacement + text[end:]


def param_name(params: str, type_pattern: str) -> str:
    match = re.search(type_pattern + r'\s+([A-Za-z_$][A-Za-z0-9_$]*)', params)
    if match is None: fail(f'could not infer parameter for {type_pattern}')
    return match.group(1)


def patch_chunk(text: str) -> str:
    if GEN_MARKER in text:
        validate_chunk(text); return text
    signature = '    private boolean tryGenerateStructure('
    method_start, method_end = find_method_end(text, signature)
    params_open = text.find('(', method_start)
    params_close = text.find(')', params_open)
    params = text[params_open + 1:params_close]
    selected = param_name(params, r'(?:StructureSet\.)?StructureSelectionEntry')
    random_state = param_name(params, r'RandomState')
    height_accessor = param_name(params, r'ChunkAccess')
    dimension = param_name(params, r'ResourceKey\s*<\s*Level\s*>')
    body = text[method_start:method_end]
    start_match = re.search(r'(?P<indent>^[ \t]*)StructureStart\s+(?P<start>[A-Za-z_$][A-Za-z0-9_$]*)\s*=\s*[A-Za-z_$][A-Za-z0-9_$]*\.generate\s*\(', body, re.MULTILINE)
    if start_match is None: fail('tryGenerateStructure: StructureStart generation assignment not found')
    start_var = start_match.group('start')
    valid_match = re.compile(rf'(?P<indent>^[ \t]*)if\s*\(\s*{re.escape(start_var)}\.isValid\(\)\s*\)\s*\{{', re.MULTILINE).search(body, start_match.end())
    if valid_match is None: fail('tryGenerateStructure: start.isValid block not found')
    insert_at = method_start + valid_match.end()
    indent = valid_match.group('indent') + '    '
    guard = ('\n' + f'{indent}{GEN_MARKER}\n' + f'{indent}if (!NeverOverworldGeneratedVillageSafety.allowsGenerated(\n' + f'{indent}    this,\n' + f'{indent}    {selected}.structure(),\n' + f'{indent}    {random_state},\n' + f'{indent}    {height_accessor},\n' + f'{indent}    {start_var},\n' + f'{indent}    {dimension}\n' + f'{indent})) {{\n' + f'{indent}    return false;\n' + f'{indent}}}')
    out = text[:insert_at] + guard + text[insert_at:]
    validate_chunk(out)
    return out


def validate_chunk(text: str) -> None:
    if text.count(GEN_MARKER) != 1: fail('generation bbox guard marker count mismatch')
    marker = text.find(GEN_MARKER)
    if text.find('setStartForStructure', marker) < 0: fail('generation bbox guard is not before setStartForStructure')
    for required in ('NeverOverworldGeneratedVillageSafety.allowsGenerated(', '.structure(),', '.isValid()'):
        if required not in text: fail(f'generation bbox guard missing: {required}')


def patch_policy(text: str) -> str:
    if POLICY_MARKER in text:
        validate_policy(text); return text
    if 'final int villageReach = 96;' not in text: fail('generation policy does not contain the expected reach96 village block')
    out = replace_method(text, POLICY_SIG, POLICY_METHOD)
    validate_policy(out)
    return out


def validate_policy(text: str) -> None:
    for marker in (POLICY_MARKER, 'return centerBase >= MIN_DRY_BASE_HEIGHT;', 'return drySamples >= minDrySamples(id);'):
        if marker not in text: fail(f'generation policy missing exact-layout marker: {marker}')
    method_start, method_end = find_method_end(text, POLICY_SIG)
    method = text[method_start:method_end]
    for forbidden in ('final int villageReach = 96;', 'final int[] villageOffsets = {-96'):
        if forbidden in method: fail(f'generation policy still contains reach96 prefilter: {forbidden}')


def patch_fast(text: str) -> str:
    if FAST_MARKER in text:
        validate_fast(text); return text
    if 'final int villageReach = 96;' not in text: fail('fast locate does not contain the expected instrumented reach96 village block')
    if 'debugVillage(' not in text: fail('fast locate diagnostics must be installed before exact-layout transform')
    out = replace_method(text, FAST_POLICY_SIG, FAST_POLICY_METHOD)
    validate_fast(out)
    return out


def validate_fast(text: str) -> None:
    required = (FAST_MARKER, 'NeverOverworldGeneratedVillageSafety.preview(generator, level, state, chunkPos, structureHolder)', '"LAYOUT_INVALID_REJECT"', '"LAYOUT_DRY_REJECT"', 'preview.detail()', 'return drySamples >= minDrySamples(id);')
    missing = [marker for marker in required if marker not in text]
    if missing: fail(f'fast locate missing exact-layout markers: {missing}')
    method_start, method_end = find_method_end(text, FAST_POLICY_SIG)
    method = text[method_start:method_end]
    for forbidden in ('final int villageReach = 96;', 'final int villageStep = 16;', 'FOOTPRINT_DRY_REJECT', 'reach96-step16-13x13'):
        if forbidden in method: fail(f'fast locate still contains reach96 village logic: {forbidden}')


def validate_helper() -> None:
    required = ('StructureStart start = structure.generate(', 'structure.biomes()::contains', 'final int MAX_VILLAGE_BBOX_SPAN = 256;', 'final long MAX_VILLAGE_BBOX_AREA = 65536L;', 'for (int z = minZ; z <= maxZ; ++z)', 'for (int x = minX; x <= maxX; ++x)', 'Heightmap.Types.WORLD_SURFACE_WG', 'base < MIN_DRY_BASE_HEIGHT', 'record Preview(')
    missing = [marker for marker in required if marker not in SAFETY_HELPER]
    if missing: fail(f'safety helper contract missing: {missing}')
    for forbidden in ('getChunk(', 'moonrise$syncLoadNonFull', 'save-all'):
        if forbidden in SAFETY_HELPER: fail(f'chunk-loading/persistence primitive leaked into safety helper: {forbidden}')


def apply(root: Path) -> None:
    chunk = root / CHUNK_REL
    fast = root / FAST_REL
    policy = root / POLICY_REL
    safety = root / SAFETY_REL
    for label, path in (('ChunkGenerator', chunk), ('fast locate', fast), ('generation policy', policy)):
        if not path.is_file(): fail(f'{label} source not found: {path}')
    validate_helper()
    chunk.write_text(patch_chunk(chunk.read_text(encoding='utf-8')), encoding='utf-8')
    policy.write_text(patch_policy(policy.read_text(encoding='utf-8')), encoding='utf-8')
    fast.write_text(patch_fast(fast.read_text(encoding='utf-8')), encoding='utf-8')
    safety.parent.mkdir(parents=True, exist_ok=True)
    safety.write_text(SAFETY_HELPER, encoding='utf-8')
    print('[NeverFolia][village layout safety] EXACT GENERATED-BBOX POLICY APPLIED')
    print('  village prefilter: candidate centre WORLD_SURFACE_WG >= 129 only')
    print('  generation: actual StructureStart bbox checked before setStartForStructure')
    print('  fast locate: same Structure#generate layout preview with references=0')
    print('  bbox gate: every X/Z column, WORLD_SURFACE_WG >= 129')
    print('  max accepted bbox: 256x256 columns')
    print('  no chunk-loading primitive in preview helper')
    print('  persisted all-block Y=128 zero-water bbox audit remains final arbiter')


def policy_fixture() -> str:
    return r'''package net.minecraft.world.level.chunk;
final class NeverOverworldVanillaStructurePolicy {
    private static final int EXPECTED_MIN_Y = -512;
    private static final int EXPECTED_HEIGHT = 1024;
    private static final int MIN_DRY_BASE_HEIGHT = 129;
    private static final java.util.Set<String> DRY_LAND_ONLY = java.util.Set.of("minecraft:village_plains");
    static boolean allows(final ChunkGenerator generator, final Holder<Structure> structure, final RandomState randomState, final ChunkAccess heightAccessor, final ChunkPos chunkPos, final ResourceKey<Level> dimension) {
        final String id = "minecraft:village_plains";
        final int radius = sampleRadius(id);
        final int centerX = chunkPos.getMiddleBlockX();
        final int centerZ = chunkPos.getMiddleBlockZ();
        if (id.startsWith("minecraft:village_")) {
            final int villageReach = 96;
            final int villageStep = 16;
            final int[] villageOffsets = {-96, 96, -80, 80, -64, 64, -48, 48, -32, 32, -16, 16, 0};
            return villageOffsets.length == 13;
        }
        return radius > 0;
    }
    private static int sampleRadius(String id) { return 48; }
    private static int minDrySamples(String id) { return 9; }
}
'''


def fast_fixture() -> str:
    return r'''package net.minecraft.world.level.chunk;
final class NeverOverworldVanillaFastLocate {
    private static final int FLOOD_LEVEL = 128;
    private static final int MIN_DRY_BASE_HEIGHT = 129;
    private static final String SWAMP_HUT = "minecraft:swamp_hut";
    private static final java.util.Set<String> DRY_LAND_ONLY = java.util.Set.of("minecraft:village_plains");
    private static void debugVillage(String a, String b, ChunkPos c, int d, String e) {}
    private static boolean passesNeverOverworldPolicy(final ChunkGenerator generator, final ServerLevel level, final ChunkGeneratorStructureState state, final ChunkPos chunkPos, final Holder<Structure> structureHolder, final String id) {
        final int centerX = chunkPos.getMiddleBlockX();
        final int centerZ = chunkPos.getMiddleBlockZ();
        final int centerSurfaceY = preliminarySurfaceY(state, centerX, centerZ);
        if (id.startsWith("minecraft:village_")) {
            final int villageReach = 96;
            final int villageStep = 16;
            final int[] villageOffsets = {-96, 96, -80, 80, -64, 64, -48, 48, -32, 32, -16, 16, 0};
            debugVillage(id, "FOOTPRINT_DRY_REJECT", chunkPos, centerSurfaceY, "x");
            return villageOffsets.length == 13;
        }
        return true;
    }
    private static int preliminarySurfaceY(Object a, int x, int z) { return 140; }
    private static boolean passesBiomeAtY(Object a, Object b, Object c, Object d, int y) { return true; }
    private static int sampleRadius(String id) { return 48; }
    private static int minDrySamples(String id) { return 9; }
}
'''


def chunk_fixture() -> str:
    return r'''class ChunkGenerator {
    private boolean tryGenerateStructure(StructureSet.StructureSelectionEntry selected, StructureManager structureManager, RegistryAccess registryAccess, RandomState randomState, StructureTemplateManager structureTemplateManager, long seed, ChunkAccess centerChunk, ChunkPos sourceChunkPos, SectionPos sectionPos, ResourceKey<Level> level) {
        Structure structure = selected.structure().value();
        StructureStart start = structure.generate(selected.structure(), level, registryAccess, this, this.biomeSource, randomState, structureTemplateManager, seed, sourceChunkPos, 0, centerChunk, x -> true);
        if (start.isValid()) {
            BoundingBox box = start.getBoundingBox();
            structureManager.setStartForStructure(sectionPos, structure, start, centerChunk);
            return true;
        }
        return false;
    }
}
'''


def self_test() -> None:
    validate_helper()
    with tempfile.TemporaryDirectory(prefix='nr-village-layout-safety-') as tmp:
        root = Path(tmp)
        chunk = root / CHUNK_REL
        fast = root / FAST_REL
        policy = root / POLICY_REL
        chunk.parent.mkdir(parents=True, exist_ok=True)
        chunk.write_text(chunk_fixture(), encoding='utf-8')
        fast.write_text(fast_fixture(), encoding='utf-8')
        policy.write_text(policy_fixture(), encoding='utf-8')
        first_chunk = patch_chunk(chunk.read_text(encoding='utf-8'))
        first_fast = patch_fast(fast.read_text(encoding='utf-8'))
        first_policy = patch_policy(policy.read_text(encoding='utf-8'))
        validate_chunk(first_chunk); validate_fast(first_fast); validate_policy(first_policy)
        if patch_chunk(first_chunk) != first_chunk: fail('SELF-TEST: generation guard is not idempotent')
        if patch_fast(first_fast) != first_fast: fail('SELF-TEST: fast policy is not idempotent')
        if patch_policy(first_policy) != first_policy: fail('SELF-TEST: generation policy is not idempotent')
    print('[NeverFolia][village layout safety] SELF-TEST OK')


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('folia_root', nargs='?', type=Path)
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    if args.self_test:
        self_test(); return
    if args.folia_root is None: parser.error('folia_root is required unless --self-test is used')
    self_test(); apply(args.folia_root.resolve())


if __name__ == '__main__':
    main()
