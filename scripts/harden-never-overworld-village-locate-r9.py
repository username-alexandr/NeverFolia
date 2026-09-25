#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

FAST_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldVanillaFastLocate.java")
POLICY_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldVanillaStructurePolicy.java")
SAFETY_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldGeneratedVillageSafety.java")

FAST_SIG = "    private static boolean passesNeverOverworldPolicy("
POLICY_SIG = "    static boolean allows("
SAFETY_SIG = "    static boolean allowsGenerated("
SAMPLE_RADIUS_SIG = "    private static int sampleRadius(final String id) {"

MARKER = "// NeverFolia R9-v4: shared 5x5 preliminary village envelope; no Jigsaw preview in locate."
VILLAGE_REACH = 96
VILLAGE_OFFSETS = (-96, -48, 0, 48, 96)
OFFSETS_JAVA = "{" + ", ".join(str(value) for value in VILLAGE_OFFSETS) + "}"

FAST_POLICY = rf'''    private static boolean passesNeverOverworldPolicy(
        final ChunkGenerator generator,
        final ServerLevel level,
        final ChunkGeneratorStructureState state,
        final ChunkPos chunkPos,
        final Holder<Structure> structureHolder,
        final String id
    ) {{
        if (SWAMP_HUT.equals(id)) {{
            return passesBiomeAtY(generator, state, chunkPos, structureHolder, FLOOD_LEVEL + 1);
        }}
        if (!DRY_LAND_ONLY.contains(id)) {{
            return false;
        }}

        final int centerX = chunkPos.getMiddleBlockX();
        final int centerZ = chunkPos.getMiddleBlockZ();
        final int centerSurfaceY = preliminarySurfaceY(state, centerX, centerZ);
        if (centerSurfaceY < MIN_DRY_BASE_HEIGHT) {{
            debugVillage(id, "R9V4_CENTER_DRY_REJECT", chunkPos, centerSurfaceY, "min=" + MIN_DRY_BASE_HEIGHT);
            return false;
        }}
        if (!passesBiomeAtY(generator, state, chunkPos, structureHolder, centerSurfaceY)) {{
            debugVillage(id, "R9V4_BIOME_REJECT", chunkPos, centerSurfaceY, "shared-preliminary-envelope");
            return false;
        }}

        if (id.startsWith("minecraft:village_")) {{
            {MARKER}
            // Locate and real generation now use this exact same deterministic
            // preliminary-surface contract. This deliberately trades the old
            // generated-bbox preview for a conservative fixed envelope covering
            // vanilla village Jigsaw reach (80) plus one chunk of overhang (16).
            // Persisted bbox QA remains the independent release gate and will
            // force this envelope tighter if a shoreline gap ever escapes it.
            final int villageReach = {VILLAGE_REACH};
            final int[] villageOffsets = {OFFSETS_JAVA};
            for (final int dx : villageOffsets) {{
                for (final int dz : villageOffsets) {{
                    if (dx == 0 && dz == 0) {{
                        continue;
                    }}
                    final int surfaceY = preliminarySurfaceY(state, centerX + dx, centerZ + dz);
                    if (surfaceY < MIN_DRY_BASE_HEIGHT) {{
                        debugVillage(
                            id,
                            "R9V4_ENVELOPE_REJECT",
                            chunkPos,
                            centerSurfaceY,
                            "sample=" + dx + "," + dz + ",surface=" + surfaceY + ",reach=" + villageReach
                        );
                        return false;
                    }}
                }}
            }}
            debugVillage(id, "R9V4_ACCEPT", chunkPos, centerSurfaceY, "5x5-preliminary-reach=" + villageReach);
            return true;
        }}

        final int radius = sampleRadius(id);
        int drySamples = 1;
        final int[] offsets = {{-radius, 0, radius}};
        for (final int dx : offsets) {{
            for (final int dz : offsets) {{
                if (dx == 0 && dz == 0) {{
                    continue;
                }}
                if (preliminarySurfaceY(state, centerX + dx, centerZ + dz) >= MIN_DRY_BASE_HEIGHT) {{
                    ++drySamples;
                }}
            }}
        }}
        return drySamples >= minDrySamples(id);
    }}
'''

GENERATION_POLICY = rf'''    static boolean allows(
        final ChunkGenerator generator,
        final Holder<Structure> structure,
        final RandomState randomState,
        final ChunkAccess heightAccessor,
        final ChunkPos chunkPos,
        final ResourceKey<Level> dimension
    ) {{
        if (!Level.OVERWORLD.equals(dimension)
            || heightAccessor.getMinY() != EXPECTED_MIN_Y
            || heightAccessor.getHeight() != EXPECTED_HEIGHT) {{
            return true;
        }}

        final String id = structure.unwrapKey()
            .map(key -> key.identifier().toString())
            .orElse("");
        if ("minecraft:stronghold".equals(id)) {{
            return false;
        }}
        if (!DRY_LAND_ONLY.contains(id)) {{
            return true;
        }}

        final int centerX = chunkPos.getMiddleBlockX();
        final int centerZ = chunkPos.getMiddleBlockZ();

        if (id.startsWith("minecraft:village_")) {{
            {MARKER}
            final int centerSurfaceY = preliminarySurfaceY(randomState, centerX, centerZ);
            if (centerSurfaceY < MIN_DRY_BASE_HEIGHT) {{
                return false;
            }}
            final int villageReach = {VILLAGE_REACH};
            final int[] villageOffsets = {OFFSETS_JAVA};
            for (final int dx : villageOffsets) {{
                for (final int dz : villageOffsets) {{
                    if (dx == 0 && dz == 0) {{
                        continue;
                    }}
                    if (preliminarySurfaceY(randomState, centerX + dx, centerZ + dz) < MIN_DRY_BASE_HEIGHT) {{
                        return false;
                    }}
                }}
            }}
            return villageReach == {VILLAGE_REACH};
        }}

        // Unrelated dry-land structures retain their established exact 3x3
        // generation-side surface contract.
        final int centerBase = generator.getBaseHeight(
            centerX,
            centerZ,
            Heightmap.Types.WORLD_SURFACE_WG,
            heightAccessor,
            randomState
        );
        if (centerBase < MIN_DRY_BASE_HEIGHT) {{
            return false;
        }}
        final int radius = sampleRadius(id);
        int drySamples = 1;
        final int[] offsets = {{-radius, 0, radius}};
        for (final int dx : offsets) {{
            for (final int dz : offsets) {{
                if (dx == 0 && dz == 0) {{
                    continue;
                }}
                final int base = generator.getBaseHeight(
                    centerX + dx,
                    centerZ + dz,
                    Heightmap.Types.WORLD_SURFACE_WG,
                    heightAccessor,
                    randomState
                );
                if (base >= MIN_DRY_BASE_HEIGHT) {{
                    ++drySamples;
                }}
            }}
        }}
        return drySamples >= minDrySamples(id);
    }}
'''

GENERATION_PRELIMINARY = '''    /** Same density-router probe used by R9-v4 village locate. */
    private static int preliminarySurfaceY(
        final RandomState randomState,
        final int blockX,
        final int blockZ
    ) {
        final double estimated = randomState
            .router()
            .preliminarySurfaceLevel()
            .compute(new DensityFunction.SinglePointContext(blockX, 0, blockZ));
        if (!Double.isFinite(estimated)) {
            return Integer.MIN_VALUE;
        }
        return (int)Math.floor(estimated);
    }

'''

SAFETY_POLICY = r'''    static boolean allowsGenerated(
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
        // NeverFolia R9-v4: the shared candidate envelope is authoritative for
        // prediction/generation agreement. Do not re-run an expensive all-column
        // bbox height scan after Structure.generate(), because /locate cannot
        // reproduce that decision without triggering the Folia watchdog.
        return start.isValid();
    }
'''


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][R9 village locate v4] {message}")


def find_method_end(text: str, signature: str) -> tuple[int, int]:
    start = text.find(signature)
    if start < 0:
        fail(f"method signature not found: {signature.strip()}")
    if text.find(signature, start + 1) >= 0:
        fail(f"method signature occurs more than once: {signature.strip()}")
    opening = text.find("{", start)
    if opening < 0:
        fail(f"opening brace not found: {signature.strip()}")
    depth = 0
    in_string = in_char = in_line_comment = in_block_comment = escaped = False
    i = opening
    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""
        if in_line_comment:
            if ch == "\n": in_line_comment = False
            i += 1; continue
        if in_block_comment:
            if ch == "*" and nxt == "/": in_block_comment = False; i += 2
            else: i += 1
            continue
        if in_string:
            if escaped: escaped = False
            elif ch == "\\": escaped = True
            elif ch == '"': in_string = False
            i += 1; continue
        if in_char:
            if escaped: escaped = False
            elif ch == "\\": escaped = True
            elif ch == "'": in_char = False
            i += 1; continue
        if ch == "/" and nxt == "/": in_line_comment = True; i += 2; continue
        if ch == "/" and nxt == "*": in_block_comment = True; i += 2; continue
        if ch == '"': in_string = True; i += 1; continue
        if ch == "'": in_char = True; i += 1; continue
        if ch == "{": depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                if end < len(text) and text[end] == "\n": end += 1
                return start, end
        i += 1
    fail(f"unterminated method: {signature.strip()}")


def replace_method(text: str, signature: str, replacement: str) -> str:
    start, end = find_method_end(text, signature)
    return text[:start] + replacement + text[end:]


def patch_fast(text: str) -> str:
    return replace_method(text, FAST_SIG, FAST_POLICY)


def patch_generation_policy(text: str) -> str:
    text = replace_method(text, POLICY_SIG, GENERATION_POLICY)
    if "import net.minecraft.world.level.levelgen.DensityFunction;" not in text:
        anchor = "import net.minecraft.world.level.levelgen.Heightmap;\n"
        if anchor not in text:
            fail("generation policy Heightmap import anchor missing")
        text = text.replace(anchor, "import net.minecraft.world.level.levelgen.DensityFunction;\n" + anchor, 1)
    if "private static int preliminarySurfaceY(" not in text:
        if SAMPLE_RADIUS_SIG not in text:
            fail("generation policy sampleRadius insertion anchor missing")
        text = text.replace(SAMPLE_RADIUS_SIG, GENERATION_PRELIMINARY + SAMPLE_RADIUS_SIG, 1)
    return text


def patch_generated_safety(text: str) -> str:
    return replace_method(text, SAFETY_SIG, SAFETY_POLICY)


def method_text(text: str, signature: str) -> str:
    start, end = find_method_end(text, signature)
    return text[start:end]


def validate(fast: str, policy: str, safety: str) -> None:
    fast_method = method_text(fast, FAST_SIG)
    generation_method = method_text(policy, POLICY_SIG)
    safety_method = method_text(safety, SAFETY_SIG)

    for label, body in (("fast", fast_method), ("generation", generation_method)):
        if MARKER not in body:
            fail(f"{label}: shared-envelope marker missing")
        if OFFSETS_JAVA not in body or f"villageReach = {VILLAGE_REACH}" not in body:
            fail(f"{label}: 5x5 reach96 contract missing")
        if body.count("preliminarySurfaceY(") < 2:
            fail(f"{label}: preliminary-surface village probes missing")

    village_start = fast_method.find('if (id.startsWith("minecraft:village_"))')
    non_village = fast_method.find("final int radius = sampleRadius(id);", village_start)
    village_fast = fast_method[village_start:non_village]
    forbidden_fast = (
        "NeverOverworldGeneratedVillageSafety.preview",
        "Structure.generate(",
        ".generate(",
        "getBaseHeight(",
        "inspectBoundingBox(",
        "R9V3_",
    )
    leaked = [needle for needle in forbidden_fast if needle in village_fast]
    if leaked:
        fail(f"fast village branch still contains watchdog path: {leaked}")

    village_generation_start = generation_method.find('if (id.startsWith("minecraft:village_"))')
    generation_non_village = generation_method.find("final int centerBase = generator.getBaseHeight(", village_generation_start)
    village_generation = generation_method[village_generation_start:generation_non_village]
    if "getBaseHeight(" in village_generation:
        fail("generation village branch still uses exact height scans")
    if "preliminarySurfaceY(randomState" not in village_generation:
        fail("generation village branch is not using the shared preliminary probe")

    if "DensityFunction.SinglePointContext" not in policy or ".preliminarySurfaceLevel()" not in policy:
        fail("generation policy preliminary helper missing")
    if "inspectBoundingBox(" in safety_method or ".dry()" in safety_method:
        fail("post-generation exact bbox reject survived in allowsGenerated")
    if "return start.isValid();" not in safety_method:
        fail("post-generation validity guard missing")


def self_test() -> None:
    fast_fixture = r'''final class NeverOverworldVanillaFastLocate {
    private static boolean passesNeverOverworldPolicy(
        final ChunkGenerator generator, final ServerLevel level, final ChunkGeneratorStructureState state,
        final ChunkPos chunkPos, final Holder<Structure> structureHolder, final String id
    ) { return true; }
}
'''
    policy_fixture = r'''package net.minecraft.world.level.chunk;
import net.minecraft.world.level.levelgen.Heightmap;
import net.minecraft.world.level.levelgen.RandomState;
final class NeverOverworldVanillaStructurePolicy {
    static boolean allows(
        final ChunkGenerator generator, final Holder<Structure> structure, final RandomState randomState,
        final ChunkAccess heightAccessor, final ChunkPos chunkPos, final ResourceKey<Level> dimension
    ) { return true; }
    private static int sampleRadius(final String id) { return 48; }
    private static int minDrySamples(final String id) { return 7; }
}
'''
    safety_fixture = r'''final class NeverOverworldGeneratedVillageSafety {
    static boolean allowsGenerated(
        final ChunkGenerator generator, final Holder<Structure> structureHolder, final RandomState randomState,
        final LevelHeightAccessor heightAccessor, final StructureStart start, final ResourceKey<Level> dimension
    ) { return inspectBoundingBox().dry(); }
}
'''
    fast = patch_fast(fast_fixture)
    policy = patch_generation_policy(policy_fixture)
    safety = patch_generated_safety(safety_fixture)
    validate(fast, policy, safety)
    if patch_fast(fast) != fast:
        fail("SELF-TEST: fast transformer is not idempotent")
    if patch_generation_policy(policy) != policy:
        fail("SELF-TEST: generation transformer is not idempotent")
    if patch_generated_safety(safety) != safety:
        fail("SELF-TEST: safety transformer is not idempotent")
    if len(VILLAGE_OFFSETS) != 5 or set(VILLAGE_OFFSETS) != {-96, -48, 0, 48, 96}:
        fail("SELF-TEST: village 5x5 offsets drifted")
    print("[NeverFolia][R9 village locate v4] SELF-TEST OK")
    print("  locate + generation: identical 5x5 preliminarySurfaceLevel envelope")
    print("  reach: 96 blocks = vanilla Jigsaw 80 + one chunk margin")
    print("  locate: zero Structure.generate / generated-bbox preview / getBaseHeight")
    print("  generation: no post-generation all-column bbox rejection")
    print("  persisted bbox QA remains the independent safety arbiter")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("folia", nargs="?", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test(); return
    if args.folia is None:
        parser.error("folia worktree path is required")
    self_test()
    root = args.folia.resolve()
    fast_path = root / FAST_REL
    policy_path = root / POLICY_REL
    safety_path = root / SAFETY_REL
    for path in (fast_path, policy_path, safety_path):
        if not path.is_file():
            fail(f"materialized helper missing: {path}")
    fast = patch_fast(fast_path.read_text(encoding="utf-8"))
    policy = patch_generation_policy(policy_path.read_text(encoding="utf-8"))
    safety = patch_generated_safety(safety_path.read_text(encoding="utf-8"))
    validate(fast, policy, safety)
    fast_path.write_text(fast, encoding="utf-8")
    policy_path.write_text(policy, encoding="utf-8")
    safety_path.write_text(safety, encoding="utf-8")
    print("[NeverFolia][R9 village locate v4] shared prediction/generation envelope applied")
    print(f"  fast locate: {fast_path}")
    print(f"  generation policy: {policy_path}")
    print(f"  generated safety: {safety_path}")

if __name__ == "__main__":
    main()
