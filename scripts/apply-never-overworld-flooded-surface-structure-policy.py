#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path

CHUNK_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/chunk/ChunkGenerator.java")
HELPER_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldVanillaStructurePolicy.java")
MARKER = "// NeverFolia: reject submerged dry-land structure starts before generation."

HELPER = r'''package net.minecraft.world.level.chunk;

import java.util.Set;
import net.minecraft.core.Holder;
import net.minecraft.resources.ResourceKey;
import net.minecraft.world.level.ChunkPos;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.levelgen.Heightmap;
import net.minecraft.world.level.levelgen.RandomState;
import net.minecraft.world.level.levelgen.structure.Structure;

/**
 * Field-r1 policy for vanilla structures in the flooded NeverOverworld.
 *
 * <p>All decisions use only immutable registry identity plus ChunkGenerator
 * base-height sampling. No generated chunk is loaded and no neighboring mutable
 * state is observed, preserving Folia ownership and chunk-order determinism.</p>
 *
 * <p>Large dry structures use a conservative 5x5 terrain footprint. The purpose
 * is to reject a candidate before Jigsaw/piece generation when any representative
 * part of the possible structure envelope would sit at or below Y=128.</p>
 *
 * <p>Swamp huts are intentionally not in DRY_LAND_ONLY. They are re-anchored
 * separately to the Y=129 flooded waterline.</p>
 */
final class NeverOverworldVanillaStructurePolicy {
    private static final int EXPECTED_MIN_Y = -512;
    private static final int EXPECTED_HEIGHT = 1024;
    private static final int FLOOD_LEVEL = 128;
    private static final int MIN_DRY_BASE_HEIGHT = FLOOD_LEVEL + 1;

    private static final Set<String> DRY_LAND_ONLY = Set.of(
        "minecraft:village_plains",
        "minecraft:village_desert",
        "minecraft:village_savanna",
        "minecraft:village_snowy",
        "minecraft:village_taiga",
        "minecraft:woodland_mansion",
        "minecraft:pillager_outpost",
        "minecraft:desert_pyramid",
        "minecraft:jungle_pyramid",
        "minecraft:igloo"
    );

    private NeverOverworldVanillaStructurePolicy() {}

    static boolean allows(
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

        // NeverLand progression owns End access. A second datapack-level guard
        // empties the stronghold biome tag, but generation rejects it here too.
        if ("minecraft:stronghold".equals(id)) {
            return false;
        }
        if (!DRY_LAND_ONLY.contains(id)) {
            return true;
        }

        final int radius = sampleRadius(id);
        final int halfRadius = Math.max(1, radius / 2);
        final int centerX = chunkPos.getMiddleBlockX();
        final int centerZ = chunkPos.getMiddleBlockZ();
        final int[] offsets = {-radius, -halfRadius, 0, halfRadius, radius};
        for (final int dx : offsets) {
            for (final int dz : offsets) {
                final int base = generator.getBaseHeight(
                    centerX + dx,
                    centerZ + dz,
                    Heightmap.Types.WORLD_SURFACE_WG,
                    heightAccessor,
                    randomState
                );
                if (base < MIN_DRY_BASE_HEIGHT) {
                    return false;
                }
            }
        }
        return true;
    }

    private static int sampleRadius(final String id) {
        if ("minecraft:woodland_mansion".equals(id)) {
            return 80;
        }
        if (id.startsWith("minecraft:village_")) {
            return 96;
        }
        if ("minecraft:pillager_outpost".equals(id)) {
            return 64;
        }
        if ("minecraft:desert_pyramid".equals(id) || "minecraft:jungle_pyramid".equals(id)) {
            return 32;
        }
        if ("minecraft:igloo".equals(id)) {
            return 24;
        }
        return 32;
    }
}
'''


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][flooded surface structures] {message}")


def matching_brace(source: str, opening: int) -> int:
    depth = 0
    for index in range(opening, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return index
    fail("unterminated tryGenerateStructure method")


def param_name(params: str, type_pattern: str) -> str:
    match = re.search(type_pattern + r"\s+([A-Za-z_$][A-Za-z0-9_$]*)", params)
    if match is None:
        fail(f"could not infer parameter for {type_pattern}")
    return match.group(1)


def patch_source(source: str) -> str:
    if MARKER in source:
        fail("flooded surface structure policy already applied")
    method = source.find("private boolean tryGenerateStructure(")
    if method < 0:
        fail("tryGenerateStructure method not found")
    params_open = source.find("(", method)
    params_close = source.find(")", params_open)
    if params_close < 0:
        fail("tryGenerateStructure parameter list not found")
    params = source[params_open + 1:params_close]
    entry = param_name(params, r"(?:StructureSet\.)?StructureSelectionEntry")
    random_state = param_name(params, r"RandomState")
    chunk = param_name(params, r"ChunkAccess")
    chunk_pos = param_name(params, r"ChunkPos")
    dimension = param_name(params, r"ResourceKey\s*<\s*Level\s*>")

    body_open = source.find("{", params_close)
    body_close = matching_brace(source, body_open)
    body = source[body_open + 1:body_close]
    structure_match = re.search(
        rf"(?P<indent>^[ \t]*)Structure\s+(?P<var>[A-Za-z_$][A-Za-z0-9_$]*)\s*=\s*{re.escape(entry)}\.structure\(\)\.value\(\);",
        body,
        re.MULTILINE,
    )
    if structure_match is None:
        fail("structure declaration in tryGenerateStructure not found")
    indent = structure_match.group("indent")
    declaration_end = body_open + 1 + structure_match.end()
    guard = (
        "\n"
        f"{indent}{MARKER}\n"
        f"{indent}if (!NeverOverworldVanillaStructurePolicy.allows(this, {entry}.structure(), {random_state}, {chunk}, {chunk_pos}, {dimension})) {{\n"
        f"{indent}    return false;\n"
        f"{indent}}}"
    )
    patched = source[:declaration_end] + guard + source[declaration_end:]
    if patched.count(MARKER) != 1:
        fail("surface structure guard was not injected exactly once")
    return patched


def self_test() -> None:
    fixture = '''class ChunkGenerator {
    private boolean tryGenerateStructure(
        StructureSet.StructureSelectionEntry entry,
        StructureManager manager,
        RegistryAccess access,
        RandomState randomState,
        StructureTemplateManager templates,
        long seed,
        ChunkAccess chunk,
        ChunkPos chunkPos,
        SectionPos sectionPos,
        ResourceKey<Level> dimension
    ) {
        Structure structure = entry.structure().value();
        return true;
    }
}
'''
    patched = patch_source(fixture)
    for marker in (MARKER, "entry.structure()", "randomState, chunk, chunkPos, dimension"):
        if marker not in patched:
            fail(f"SELF-TEST missing {marker}")
    for marker in (
        "minecraft:stronghold",
        "minecraft:woodland_mansion",
        "MIN_DRY_BASE_HEIGHT",
        "{-radius, -halfRadius, 0, halfRadius, radius}",
        "return 96;",
        "return 80;",
    ):
        if marker not in HELPER:
            fail(f"SELF-TEST helper missing {marker}")
    if '"minecraft:swamp_hut"' in HELPER:
        fail("SELF-TEST: swamp hut must not be dry-land-only")
    print("[NeverFolia][flooded surface structures] SELF-TEST OK")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("folia", nargs="?", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if args.folia is None:
        parser.error("folia worktree is required unless --self-test is used")
    self_test()
    folia = args.folia.resolve()
    chunk = folia / CHUNK_REL
    helper = folia / HELPER_REL
    if not chunk.is_file():
        fail(f"ChunkGenerator source not found: {chunk}")
    chunk.write_text(patch_source(chunk.read_text(encoding="utf-8")), encoding="utf-8")
    helper.parent.mkdir(parents=True, exist_ok=True)
    helper.write_text(HELPER, encoding="utf-8")
    print("[NeverFolia][flooded surface structures] conservative dry-footprint rejection applied")
    print("  flood plane: Y=128")
    print("  sample grid: 5x5")
    print("  village radius: 96 blocks; mansion radius: 80 blocks")
    print("  swamp hut: delegated to flood-adapted waterline placement")
    print("  stronghold/end portal: rejected")
    print(f"  generator: {chunk}")
    print(f"  helper: {helper}")


if __name__ == "__main__":
    main()
