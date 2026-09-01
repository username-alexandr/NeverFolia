#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = ROOT / "worldgen-spec" / "never-nether-structures.json"

JIGSAW_REL = Path(
    "folia-server/src/minecraft/java/net/minecraft/world/level/levelgen/structure/structures/JigsawStructure.java"
)
HELPER_REL = Path(
    "folia-server/src/minecraft/java/net/minecraft/world/level/levelgen/structure/structures/NeverNetherStructurePlacement.java"
)


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][NeverNether placement hook] {message}")


def alias_id(structure_id: str) -> str:
    namespace, path = structure_id.split(":", 1)
    safe = f"{namespace}__{path}".replace("/", "__")
    return f"neverfolia:never_nether/start/{safe}"


def java_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def build_profiles(spec: dict) -> list[tuple[str, str, dict, bool]]:
    profiles = spec["vertical_profiles"]
    result: list[tuple[str, str, dict, bool]] = []
    for group in spec["placement_groups"].values():
        for entry in group["structures"]:
            profile_name = entry["vertical_profile"]
            profile = profiles[profile_name]
            result.append(
                (
                    alias_id(entry["id"]),
                    profile_name,
                    profile,
                    bool(entry.get("requires_large_lava_basin", False)),
                )
            )
    if len(result) != 20:
        fail(f"expected 20 custom structure profiles, got {len(result)}")
    return sorted(result)


def helper_source(spec: dict) -> str:
    profile_entries = []
    for alias, name, profile, large_lava in build_profiles(spec):
        preferred = profile["preferred_y"]
        hard = profile["hard_y"]
        placement = profile["placement"]
        mode = "LAVA_BASIN" if placement == "large_lava_basin_floor" else "CAVERN_FLOOR"
        profile_entries.append(
            "        Map.entry("
            + java_string(alias)
            + ", new Profile("
            + java_string(name)
            + f", {preferred[0]}, {preferred[1]}, {hard[0]}, {hard[1]}, Mode.{mode}, "
            + ("true" if large_lava else "false")
            + "))"
        )

    entries = ",\n".join(profile_entries)
    return f'''package net.minecraft.world.level.levelgen.structure.structures;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import net.minecraft.core.Holder;
import net.minecraft.tags.FluidTags;
import net.minecraft.world.level.ChunkPos;
import net.minecraft.world.level.NoiseColumn;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.levelgen.structure.Structure;
import net.minecraft.world.level.levelgen.structure.pools.StructureTemplatePool;

/**
 * NeverFolia-owned deterministic vertical placement for imported NeverNether jigsaws.
 *
 * <p>This helper only samples ChunkGenerator#getBaseColumn. It must never request,
 * load, or generate a neighboring chunk. Returning REJECT_Y tells JigsawStructure
 * to reject this candidate without searching for a replacement nearby.</p>
 */
final class NeverNetherStructurePlacement {{
    static final int REJECT_Y = Integer.MIN_VALUE + 31926;
    private static final int LAVA_SURFACE_Y = 32;
    private static final int MIN_SAFE_Y = -123;
    private static final int MAX_SAFE_Y = 378;
    private static final int MIN_CLEARANCE = 8;

    private enum Mode {{ CAVERN_FLOOR, LAVA_BASIN }}

    private record Profile(
        String name,
        int preferredMinY,
        int preferredMaxY,
        int hardMinY,
        int hardMaxY,
        Mode mode,
        boolean requireLargeLavaBasin
    ) {{}}

    private static final Map<String, Profile> PROFILES = Map.ofEntries(
{entries}
    );

    private NeverNetherStructurePlacement() {{}}

    static int resolveStartY(
        Structure.GenerationContext context,
        Holder<StructureTemplatePool> startPool,
        int vanillaStartY
    ) {{
        final String poolId = startPool.unwrapKey()
            .map(key -> key.location().toString())
            .orElse("");
        final Profile profile = PROFILES.get(poolId);
        if (profile == null) {{
            return vanillaStartY;
        }}

        final ChunkPos chunkPos = context.chunkPos();
        final int anchorX = chunkPos.getMinBlockX();
        final int anchorZ = chunkPos.getMinBlockZ();
        final long hash = mix64(
            context.seed()
                ^ ((long) chunkPos.x * 0x9E3779B97F4A7C15L)
                ^ ((long) chunkPos.z * 0xC2B2AE3D27D4EB4FL)
                ^ poolId.hashCode()
        );

        if (profile.mode == Mode.LAVA_BASIN) {{
            if (profile.requireLargeLavaBasin && !hasLargeLavaBasin(context, anchorX, anchorZ)) {{
                return REJECT_Y;
            }}
            final int lavaFloor = findLavaFloor(context, anchorX, anchorZ, profile);
            return isSafe(lavaFloor) ? lavaFloor : REJECT_Y;
        }}

        final NoiseColumn column = context.chunkGenerator().getBaseColumn(
            anchorX,
            anchorZ,
            context.heightAccessor(),
            context.randomState()
        );

        int y = chooseCavernFloor(column, profile.preferredMinY, profile.preferredMaxY, hash);
        if (y == REJECT_Y) {{
            y = chooseCavernFloor(column, profile.hardMinY, profile.hardMaxY, mix64(hash));
        }}
        return isSafe(y) ? y : REJECT_Y;
    }}

    private static int chooseCavernFloor(NoiseColumn column, int minY, int maxY, long hash) {{
        final int lo = Math.max(MIN_SAFE_Y, minY);
        final int hi = Math.min(MAX_SAFE_Y, maxY);
        if (lo > hi) {{
            return REJECT_Y;
        }}

        final List<Integer> candidates = new ArrayList<>();
        for (int y = lo; y <= hi; ++y) {{
            if (isDryFloorWithClearance(column, y)) {{
                candidates.add(y + 1);
            }}
        }}
        if (candidates.isEmpty()) {{
            return REJECT_Y;
        }}
        return candidates.get(Math.floorMod((int) (hash ^ (hash >>> 32)), candidates.size()));
    }}

    private static boolean isDryFloorWithClearance(NoiseColumn column, int floorY) {{
        final BlockState floor = column.getBlock(floorY);
        if (floor.isAir() || !floor.getFluidState().isEmpty()) {{
            return false;
        }}
        for (int dy = 1; dy <= MIN_CLEARANCE; ++dy) {{
            final BlockState state = column.getBlock(floorY + dy);
            if (!state.isAir()) {{
                return false;
            }}
        }}
        return true;
    }}

    private static boolean hasLargeLavaBasin(
        Structure.GenerationContext context,
        int anchorX,
        int anchorZ
    ) {{
        // 3x3 deterministic footprint, 24 blocks apart. A rare monument requires
        // at least 7/9 columns to contain lava at the global sea-level band.
        int lavaColumns = 0;
        for (int dx = -24; dx <= 24; dx += 24) {{
            for (int dz = -24; dz <= 24; dz += 24) {{
                final NoiseColumn column = context.chunkGenerator().getBaseColumn(
                    anchorX + dx,
                    anchorZ + dz,
                    context.heightAccessor(),
                    context.randomState()
                );
                if (isLava(column.getBlock(LAVA_SURFACE_Y - 1))) {{
                    ++lavaColumns;
                }}
            }}
        }}
        return lavaColumns >= 7;
    }}

    private static int findLavaFloor(
        Structure.GenerationContext context,
        int anchorX,
        int anchorZ,
        Profile profile
    ) {{
        final NoiseColumn column = context.chunkGenerator().getBaseColumn(
            anchorX,
            anchorZ,
            context.heightAccessor(),
            context.randomState()
        );
        final int minY = Math.max(MIN_SAFE_Y, profile.hardMinY);
        final int maxY = Math.min(LAVA_SURFACE_Y - 1, profile.hardMaxY);
        boolean sawLava = false;
        for (int y = maxY; y >= minY; --y) {{
            final BlockState state = column.getBlock(y);
            if (isLava(state)) {{
                sawLava = true;
                continue;
            }}
            if (sawLava && !state.isAir() && state.getFluidState().isEmpty()) {{
                return y + 1;
            }}
            if (sawLava && state.isAir()) {{
                return REJECT_Y;
            }}
        }}
        return REJECT_Y;
    }}

    private static boolean isLava(BlockState state) {{
        return state.getFluidState().is(FluidTags.LAVA);
    }}

    private static boolean isSafe(int y) {{
        return y != REJECT_Y && y >= MIN_SAFE_Y && y <= MAX_SAFE_Y;
    }}

    private static long mix64(long z) {{
        z = (z ^ (z >>> 30)) * 0xBF58476D1CE4E5B9L;
        z = (z ^ (z >>> 27)) * 0x94D049BB133111EBL;
        return z ^ (z >>> 31);
    }}
}}
'''


def patch_jigsaw(source: str) -> tuple[str, str]:
    if "NeverNetherStructurePlacement.resolveStartY" in source:
        fail("JigsawStructure is already patched")

    method_match = re.search(
        r"findGenerationPoint\s*\(\s*(?:Structure\.)?GenerationContext\s+(\w+)\s*\)",
        source,
    )
    if not method_match:
        fail("could not locate JigsawStructure.findGenerationPoint GenerationContext parameter")
    context_name = method_match.group(1)

    # Mojang's implementation samples startHeight once before calling JigsawPlacement.
    # Capture the whole assignment independent of local variable name and formatting.
    assignment = re.compile(
        r"(?P<indent>^[ \t]*)int\s+(?P<var>[A-Za-z_$][A-Za-z0-9_$]*)\s*=\s*"
        r"(?P<sample>this\.startHeight\.sample\([\s\S]*?\))\s*;",
        re.MULTILINE,
    )
    matches = list(assignment.finditer(source))
    # Restrict to the findGenerationPoint body region to avoid future unrelated samples.
    method_start = method_match.start()
    method_matches = [m for m in matches if m.start() > method_start]
    if len(method_matches) != 1:
        fail(f"expected exactly one startHeight assignment after findGenerationPoint, got {len(method_matches)}")

    m = method_matches[0]
    indent = m.group("indent")
    var = m.group("var")
    sample = m.group("sample")
    replacement = (
        f"{indent}int {var} = NeverNetherStructurePlacement.resolveStartY("
        f"{context_name}, this.startPool, {sample});\n"
        f"{indent}if ({var} == NeverNetherStructurePlacement.REJECT_Y) {{\n"
        f"{indent}    return Optional.empty();\n"
        f"{indent}}}"
    )
    return source[: m.start()] + replacement + source[m.end() :], var


def main() -> None:
    if len(sys.argv) != 2:
        fail("usage: apply-never-nether-placement-hook.py /path/to/.work/Folia")
    folia = Path(sys.argv[1]).resolve()
    jigsaw = folia / JIGSAW_REL
    helper = folia / HELPER_REL
    if not jigsaw.is_file():
        fail(f"JigsawStructure source not found: {jigsaw}")

    spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    source = jigsaw.read_text(encoding="utf-8")
    patched, variable = patch_jigsaw(source)
    jigsaw.write_text(patched, encoding="utf-8")
    helper.write_text(helper_source(spec), encoding="utf-8")

    print("[NeverFolia][NeverNether placement hook] applied")
    print(f"  JigsawStructure: {jigsaw}")
    print(f"  helper: {helper}")
    print(f"  patched local start-Y variable: {variable}")
    print("  custom profiles: 20")


if __name__ == "__main__":
    main()
