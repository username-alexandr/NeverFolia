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
import net.minecraft.world.level.ChunkPos;
import net.minecraft.world.level.levelgen.DensityFunction;
import net.minecraft.world.level.levelgen.structure.Structure;
import net.minecraft.world.level.levelgen.structure.pools.StructureTemplatePool;

/**
 * NeverFolia-owned deterministic vertical placement for imported NeverNether jigsaws.
 *
 * <p>R39.38 never builds a complete NoiseColumn while checking a structure
 * candidate. It scans final density at an 8-block stride, refines only intervals
 * that contain a solid-to-cavity transition, and performs the same bounded
 * resolver for normal generation and fast locate.</p>
 */
public final class NeverNetherStructurePlacement {{
    public static final int REJECT_Y = Integer.MIN_VALUE + 31926;
    private static final int LAVA_SURFACE_Y = 32;
    private static final int MIN_SAFE_Y = -123;
    private static final int MAX_SAFE_Y = 378;
    private static final int MIN_CLEARANCE = 8;
    private static final int COARSE_STEP = 8;
    private static final ThreadLocal<Long> LOCATE_CACHE_KEY = new ThreadLocal<>();
    private static final ThreadLocal<Integer> LOCATE_CACHE_Y = new ThreadLocal<>();

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

    public static int resolveStartY(
        Structure.GenerationContext context,
        Holder<StructureTemplatePool> startPool,
        int vanillaStartY
    ) {{
        final String poolId = startPool.unwrapKey()
            .map(key -> key.identifier().toString())
            .orElse("");
        final Profile profile = PROFILES.get(poolId);
        if (profile == null) {{
            return vanillaStartY;
        }}

        final long cacheKey = locateKey(context, poolId);
        final Long cachedKey = LOCATE_CACHE_KEY.get();
        if (cachedKey != null && cachedKey.longValue() == cacheKey) {{
            final Integer cachedY = LOCATE_CACHE_Y.get();
            LOCATE_CACHE_KEY.remove();
            LOCATE_CACHE_Y.remove();
            if (cachedY != null) {{
                return cachedY.intValue();
            }}
        }}

        final ChunkPos chunkPos = context.chunkPos();
        final int anchorX = chunkPos.getMinBlockX();
        final int anchorZ = chunkPos.getMinBlockZ();
        final int chunkX = anchorX >> 4;
        final int chunkZ = anchorZ >> 4;
        final long hash = mix64(
            context.seed()
                ^ ((long) chunkX * 0x9E3779B97F4A7C15L)
                ^ ((long) chunkZ * 0xC2B2AE3D27D4EB4FL)
                ^ poolId.hashCode()
        );

        if (profile.mode == Mode.LAVA_BASIN) {{
            if (profile.requireLargeLavaBasin
                && !hasLargeLavaBasin(context, anchorX, anchorZ)) {{
                return REJECT_Y;
            }}
            final int floor = findLavaFloor(context, anchorX, anchorZ, profile, hash);
            return isSafe(floor) ? floor : REJECT_Y;
        }}

        int y = chooseCavernFloor(
            context,
            anchorX,
            anchorZ,
            profile.preferredMinY,
            profile.preferredMaxY,
            hash
        );
        if (y == REJECT_Y) {{
            y = chooseCavernFloor(
                context,
                anchorX,
                anchorZ,
                profile.hardMinY,
                profile.hardMaxY,
                mix64(hash)
            );
        }}
        return isSafe(y) ? y : REJECT_Y;
    }}

    public static boolean fastLocatePasses(
        Structure.GenerationContext context,
        Holder<StructureTemplatePool> startPool
    ) {{
        final String poolId = startPool.unwrapKey()
            .map(key -> key.identifier().toString())
            .orElse("");
        final int y = resolveStartY(context, startPool, 0);
        if (y == REJECT_Y || !PROFILES.containsKey(poolId)) {{
            LOCATE_CACHE_KEY.remove();
            LOCATE_CACHE_Y.remove();
            return false;
        }}
        // findValidGenerationPoint() immediately calls resolveStartY() again for
        // the same candidate. Hand that exact deterministic result across once
        // instead of repeating the density scan on the Folia scheduler thread.
        LOCATE_CACHE_KEY.set(locateKey(context, poolId));
        LOCATE_CACHE_Y.set(y);
        return true;
    }}

    private static int chooseCavernFloor(
        Structure.GenerationContext context,
        int x,
        int z,
        int minY,
        int maxY,
        long hash
    ) {{
        final int lo = Math.max(Math.max(MIN_SAFE_Y, minY), LAVA_SURFACE_Y);
        final int hi = Math.min(MAX_SAFE_Y - MIN_CLEARANCE, maxY);
        if (lo > hi) {{
            return REJECT_Y;
        }}

        final DensityFunction density = context.randomState().router().finalDensity();
        final List<Integer> candidates = new ArrayList<>();

        int previousY = lo;
        double previous = density(density, x, previousY, z);

        for (int probeY = lo + COARSE_STEP; probeY <= hi + COARSE_STEP; probeY += COARSE_STEP) {{
            final int currentY = Math.min(probeY, hi + 1);
            final double current = density(density, x, currentY, z);

            if (previous > 0.0 && current <= 0.0) {{
                final int refineEnd = Math.min(currentY - 1, hi);
                for (int floorY = previousY; floorY <= refineEnd; ++floorY) {{
                    if (isDryFloorWithClearance(density, x, floorY, z)) {{
                        candidates.add(floorY + 1);
                    }}
                }}
            }}

            if (currentY >= hi + 1) {{
                break;
            }}
            previousY = currentY;
            previous = current;
        }}

        if (candidates.isEmpty()) {{
            return REJECT_Y;
        }}
        return candidates.get(
            Math.floorMod((int) (hash ^ (hash >>> 32)), candidates.size())
        );
    }}

    private static boolean isDryFloorWithClearance(
        DensityFunction density,
        int x,
        int floorY,
        int z
    ) {{
        return density(density, x, floorY, z) > 0.0
            && density(density, x, floorY + 1, z) <= 0.0
            && density(density, x, floorY + 4, z) <= 0.0
            && density(density, x, floorY + MIN_CLEARANCE, z) <= 0.0;
    }}

    private static boolean hasLargeLavaBasin(
        Structure.GenerationContext context,
        int anchorX,
        int anchorZ
    ) {{
        final DensityFunction density = context.randomState().router().finalDensity();
        int openColumns = 0;
        for (int dx = -24; dx <= 24; dx += 24) {{
            for (int dz = -24; dz <= 24; dz += 24) {{
                if (density(density, anchorX + dx, LAVA_SURFACE_Y - 1, anchorZ + dz) <= 0.0) {{
                    ++openColumns;
                }}
            }}
        }}
        return openColumns >= 7;
    }}

    private static int findLavaFloor(
        Structure.GenerationContext context,
        int x,
        int z,
        Profile profile,
        long hash
    ) {{
        final int lo = Math.max(MIN_SAFE_Y, profile.hardMinY);
        final int hi = Math.min(LAVA_SURFACE_Y - 2, profile.hardMaxY);
        if (lo > hi) {{
            return REJECT_Y;
        }}

        final DensityFunction density = context.randomState().router().finalDensity();
        if (density(density, x, LAVA_SURFACE_Y - 1, z) > 0.0) {{
            return REJECT_Y;
        }}

        final int offset = Math.floorMod((int) mix64(hash), 4);
        for (int probeY = hi - offset; probeY >= lo; probeY -= 4) {{
            if (density(density, x, probeY, z) <= 0.0) {{
                continue;
            }}
            final int refineTop = Math.min(hi, probeY + 3);
            for (int floorY = refineTop; floorY >= probeY; --floorY) {{
                if (density(density, x, floorY, z) > 0.0
                    && density(density, x, floorY + 1, z) <= 0.0) {{
                    return floorY + 1;
                }}
            }}
        }}
        return REJECT_Y;
    }}

    private static double density(DensityFunction density, int x, int y, int z) {{
        return density.compute(new DensityFunction.SinglePointContext(x, y, z));
    }}

    private static boolean isSafe(int y) {{
        return y != REJECT_Y && y >= MIN_SAFE_Y && y <= MAX_SAFE_Y;
    }}

    private static long locateKey(
        Structure.GenerationContext context,
        String poolId
    ) {{
        final ChunkPos chunkPos = context.chunkPos();
        return mix64(
            context.seed()
                ^ ((long) chunkPos.x() * 0x9E3779B97F4A7C15L)
                ^ ((long) chunkPos.z() * 0xC2B2AE3D27D4EB4FL)
                ^ poolId.hashCode()
        );
    }}

    private static long mix64(long z) {{
        z = (z ^ (z >>> 30)) * 0xBF58476D1CE4E5B9L;
        z = (z ^ (z >>> 27)) * 0x94D049BB133111EBL;
        return z ^ (z >>> 31);
    }}
}}
'''

def patch_jigsaw(source: str) -> tuple[str, str, str]:
    if "NeverNetherStructurePlacement.resolveStartY" in source:
        fail("JigsawStructure is already patched")

    assignment = re.compile(
        r"(?P<indent>^[ \t]*)int\s+(?P<var>[A-Za-z_$][A-Za-z0-9_$]*)\s*=\s*"
        r"(?P<sample>this\.startHeight\.sample\([\s\S]*?\))\s*;",
        re.MULTILINE,
    )
    matches = list(assignment.finditer(source))
    if len(matches) != 1:
        fail(f"expected exactly one this.startHeight.sample assignment, got {len(matches)}")
    m = matches[0]

    method_start = source.rfind("findGenerationPoint", 0, m.start())
    if method_start < 0:
        fail("startHeight sample is not inside findGenerationPoint")
    header_and_prefix = source[method_start : m.start()]

    context_candidates = re.findall(
        r"(?:Structure\.)?GenerationContext\s+([A-Za-z_$][A-Za-z0-9_$]*)",
        header_and_prefix,
    )
    if not context_candidates:
        context_candidates = re.findall(
            r"([A-Za-z_$][A-Za-z0-9_$]*)\.(?:chunkPos|chunkGenerator|heightAccessor|randomState|random)\(\)",
            header_and_prefix + m.group("sample"),
        )
    if not context_candidates:
        fail("could not infer GenerationContext local name near startHeight sample")
    context_name = context_candidates[-1]

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
    return source[: m.start()] + replacement + source[m.end() :], var, context_name


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
    patched, variable, context_name = patch_jigsaw(source)
    jigsaw.write_text(patched, encoding="utf-8")
    helper.write_text(helper_source(spec), encoding="utf-8")

    print("[NeverFolia][NeverNether placement hook] applied")
    print(f"  JigsawStructure: {jigsaw}")
    print(f"  helper: {helper}")
    print(f"  GenerationContext local: {context_name}")
    print(f"  patched local start-Y variable: {variable}")
    print("  custom profiles: 20")


if __name__ == "__main__":
    main()
