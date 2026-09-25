#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = ROOT / "worldgen-spec" / "never-overworld-structures.json"

JIGSAW_REL = Path(
    "folia-server/src/minecraft/java/net/minecraft/world/level/levelgen/structure/structures/JigsawStructure.java"
)
HELPER_REL = Path(
    "folia-server/src/minecraft/java/net/minecraft/world/level/levelgen/structure/structures/NeverOverworldStructurePlacement.java"
)
HOOK = "NeverOverworldStructurePlacement.resolveStartY"
NETHER_HOOK = "NeverNetherStructurePlacement.resolveStartY"
REJECT_SENTINEL = "Integer.MIN_VALUE + 31926"


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][NeverOverworld placement hook] {message}")


def alias_id(structure_id: str) -> str:
    namespace, path = structure_id.split(":", 1)
    safe = f"{namespace}__{path}".replace("/", "__")
    return f"neverfolia:never_overworld/start/{safe}"


def java_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def mode_for(profile: dict) -> str:
    placement = profile["placement"]
    mapping = {
        "deterministic_solid_volume_anchor": "ROCK_MASS",
        "deterministic_cavern_wall_or_ledge": "CAVERN_EDGE",
        "deterministic_cavity_floor": "CAVERN_FLOOR",
        "deterministic_water_boundary_anchor": "WATER_BOUNDARY",
        "surface_or_flooded_cavity_floor": "FLOODED_FLOOR",
    }
    try:
        return mapping[placement]
    except KeyError as exc:
        fail(f"unsupported placement mode: {placement}")
        raise exc


def profile_args(profile: dict) -> tuple[int, int, int, bool]:
    mode = mode_for(profile)
    if mode == "ROCK_MASS":
        return (
            int(profile.get("minimum_rock_above", 12)),
            int(profile.get("minimum_rock_below", 8)),
            0,
            False,
        )
    if mode == "CAVERN_EDGE":
        shell = int(profile.get("minimum_rock_shell", 12))
        return (shell, max(6, shell // 2), 6, False)
    if mode == "CAVERN_FLOOR":
        return (
            0,
            int(profile.get("minimum_floor_thickness", 6)),
            int(profile.get("minimum_headroom", 7)),
            False,
        )
    if mode == "WATER_BOUNDARY":
        return (
            int(profile.get("minimum_rock_shell", 12)),
            max(6, int(profile.get("minimum_rock_shell", 12)) // 2),
            4,
            True,
        )
    if mode == "FLOODED_FLOOR":
        return (0, int(profile.get("minimum_floor_thickness", 6)), 4, True)
    fail(f"unhandled mode {mode}")
    raise AssertionError(mode)


def build_profiles(spec: dict) -> list[tuple[str, str, dict]]:
    profiles = spec["vertical_profiles"]
    out: list[tuple[str, str, dict]] = []
    for group in spec["placement_groups"].values():
        for entry in group["structures"]:
            name = entry["vertical_profile"]
            out.append((alias_id(entry["id"]), name, profiles[name]))
    if len(out) != 8:
        fail(f"expected 8 custom NeverOverworld structure profiles, got {len(out)}")
    return sorted(out)


def helper_source(spec: dict) -> str:
    rejection = spec["candidate_rejection"]
    min_safe = int(rejection["reject_if_bounding_box_min_y_below"])
    max_safe = int(rejection["reject_if_bounding_box_max_y_above"])

    entries: list[str] = []
    for alias, name, profile in build_profiles(spec):
        preferred = profile["preferred_y"]
        hard = profile["hard_y"]
        rock_above, rock_below, headroom, water_allowed = profile_args(profile)
        entries.append(
            "        Map.entry("
            + java_string(alias)
            + ", new Profile("
            + java_string(name)
            + f", {preferred[0]}, {preferred[1]}, {hard[0]}, {hard[1]}, Mode.{mode_for(profile)}, "
            + f"{rock_above}, {rock_below}, {headroom}, "
            + ("true" if water_allowed else "false")
            + "))"
        )
    map_entries = ",\n".join(entries)

    return f'''package net.minecraft.world.level.levelgen.structure.structures;

import java.util.Map;
import net.minecraft.core.Holder;
import net.minecraft.tags.FluidTags;
import net.minecraft.world.level.ChunkPos;
import net.minecraft.world.level.NoiseColumn;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.levelgen.structure.Structure;
import net.minecraft.world.level.levelgen.structure.pools.StructureTemplatePool;

/**
 * Deterministic NR-DEV-1 placement precheck for NeverOverworld jigsaws.
 *
 * <p>The resolver samples only ChunkGenerator#getBaseColumn at absolute coordinates.
 * It never requests or loads a generated chunk and therefore remains safe for Folia
 * region-threaded generation. Exact bounding-box checks are intentionally a later
 * structure-start phase; this class rejects obviously invalid candidates early.</p>
 */
final class NeverOverworldStructurePlacement {{
    static final int REJECT_Y = {REJECT_SENTINEL};
    private static final int MIN_SAFE_Y = {min_safe};
    private static final int MAX_SAFE_Y = {max_safe};

    private enum Mode {{ ROCK_MASS, CAVERN_EDGE, CAVERN_FLOOR, WATER_BOUNDARY, FLOODED_FLOOR }}

    private record Profile(
        String name,
        int preferredMinY,
        int preferredMaxY,
        int hardMinY,
        int hardMaxY,
        Mode mode,
        int rockAbove,
        int rockBelow,
        int headroom,
        boolean waterAllowed
    ) {{}}

    private static final Map<String, Profile> PROFILES = Map.ofEntries(
{map_entries}
    );

    private NeverOverworldStructurePlacement() {{}}

    static int resolveStartY(
        Structure.GenerationContext context,
        Holder<StructureTemplatePool> startPool,
        int previousStartY
    ) {{
        final String poolId = startPool.unwrapKey()
            .map(key -> key.identifier().toString())
            .orElse("");
        final Profile profile = PROFILES.get(poolId);
        if (profile == null) {{
            return previousStartY;
        }}
        if (previousStartY == REJECT_Y) {{
            return REJECT_Y;
        }}

        final ChunkPos chunkPos = context.chunkPos();
        final int anchorX = chunkPos.getMinBlockX() + 8;
        final int anchorZ = chunkPos.getMinBlockZ() + 8;
        final long hash = mix64(
            context.seed()
                ^ ((long)chunkPos.x * 0x9E3779B97F4A7C15L)
                ^ ((long)chunkPos.z * 0xC2B2AE3D27D4EB4FL)
                ^ poolId.hashCode()
        );

        int y = choose(context, anchorX, anchorZ, profile, profile.preferredMinY, profile.preferredMaxY, hash);
        if (y == REJECT_Y) {{
            y = choose(context, anchorX, anchorZ, profile, profile.hardMinY, profile.hardMaxY, mix64(hash));
        }}
        return isSafe(y) ? y : REJECT_Y;
    }}

    private static int choose(
        Structure.GenerationContext context,
        int x,
        int z,
        Profile profile,
        int minY,
        int maxY,
        long hash
    ) {{
        final int lo = Math.max(MIN_SAFE_Y, minY);
        final int hi = Math.min(MAX_SAFE_Y, maxY);
        if (lo > hi) {{
            return REJECT_Y;
        }}
        final int span = hi - lo + 1;
        final int start = Math.floorMod((int)(hash ^ (hash >>> 32)), span);
        final NoiseColumn center = column(context, x, z);
        for (int offset = 0; offset < span; ++offset) {{
            final int y = lo + ((start + offset) % span);
            if (matches(context, center, x, z, y, profile)) {{
                return profile.mode == Mode.ROCK_MASS ? y : y + 1;
            }}
        }}
        return REJECT_Y;
    }}

    private static boolean matches(
        Structure.GenerationContext context,
        NoiseColumn center,
        int x,
        int z,
        int y,
        Profile profile
    ) {{
        return switch (profile.mode) {{
            case ROCK_MASS -> isRockMass(center, y, profile.rockBelow, profile.rockAbove);
            case CAVERN_FLOOR -> isCavernFloor(center, y, profile.rockBelow, profile.headroom, false);
            case FLOODED_FLOOR -> isCavernFloor(center, y, profile.rockBelow, profile.headroom, true);
            case WATER_BOUNDARY -> isWaterBoundary(center, y, profile.rockBelow, profile.headroom);
            case CAVERN_EDGE -> isCavernEdge(context, center, x, z, y, profile);
        }};
    }}

    private static boolean isRockMass(NoiseColumn column, int y, int below, int above) {{
        for (int dy = -below; dy <= above; ++dy) {{
            if (!isDryHost(column.getBlock(y + dy))) {{
                return false;
            }}
        }}
        return true;
    }}

    private static boolean isCavernFloor(NoiseColumn column, int floorY, int floorThickness, int headroom, boolean allowWater) {{
        for (int dy = 0; dy < Math.max(1, floorThickness); ++dy) {{
            if (!isDryHost(column.getBlock(floorY - dy))) {{
                return false;
            }}
        }}
        boolean sawOpen = false;
        for (int dy = 1; dy <= Math.max(1, headroom); ++dy) {{
            final BlockState state = column.getBlock(floorY + dy);
            if (state.isAir()) {{
                sawOpen = true;
                continue;
            }}
            if (allowWater && isWater(state)) {{
                sawOpen = true;
                continue;
            }}
            return false;
        }}
        return sawOpen;
    }}

    private static boolean isWaterBoundary(NoiseColumn column, int floorY, int shell, int headroom) {{
        if (!isCavernFloor(column, floorY, Math.max(1, shell / 2), Math.max(1, headroom), true)) {{
            return false;
        }}
        for (int dy = 1; dy <= Math.max(2, headroom + 2); ++dy) {{
            if (isWater(column.getBlock(floorY + dy))) {{
                return true;
            }}
        }}
        return false;
    }}

    private static boolean isCavernEdge(
        Structure.GenerationContext context,
        NoiseColumn center,
        int x,
        int z,
        int floorY,
        Profile profile
    ) {{
        if (!isCavernFloor(center, floorY, Math.max(4, profile.rockBelow / 2), Math.max(5, profile.headroom), false)) {{
            return false;
        }}
        int solidNeighbors = 0;
        int openNeighbors = 0;
        final int[] offsets = {{-8, 0, 8}};
        for (int dx : offsets) {{
            for (int dz : offsets) {{
                if (dx == 0 && dz == 0) {{
                    continue;
                }}
                final NoiseColumn nearby = column(context, x + dx, z + dz);
                if (isDryHost(nearby.getBlock(floorY + 3))) {{
                    ++solidNeighbors;
                }} else if (nearby.getBlock(floorY + 3).isAir()) {{
                    ++openNeighbors;
                }}
            }}
        }}
        return solidNeighbors >= 2 && openNeighbors >= 2;
    }}

    private static NoiseColumn column(Structure.GenerationContext context, int x, int z) {{
        return context.chunkGenerator().getBaseColumn(
            x,
            z,
            context.heightAccessor(),
            context.randomState()
        );
    }}

    private static boolean isDryHost(BlockState state) {{
        return !state.isAir() && state.getFluidState().isEmpty();
    }}

    private static boolean isWater(BlockState state) {{
        return state.getFluidState().is(FluidTags.WATER);
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


def patch_jigsaw(source: str) -> str:
    if HOOK in source:
        fail("JigsawStructure is already patched for NeverOverworld")
    if NETHER_HOOK not in source:
        fail("NeverNether placement hook must be applied before NeverOverworld hook")

    assignment = re.compile(
        r"(?P<indent>^[ \t]*)int\s+(?P<var>[A-Za-z_$][A-Za-z0-9_$]*)\s*=\s*"
        r"(?P<call>NeverNetherStructurePlacement\.resolveStartY\([\s\S]*?\))\s*;",
        re.MULTILINE,
    )
    matches = list(assignment.finditer(source))
    if len(matches) != 1:
        fail(f"expected exactly one NeverNether resolver assignment, got {len(matches)}")
    m = matches[0]

    method_start = source.rfind("findGenerationPoint", 0, m.start())
    if method_start < 0:
        fail("NeverNether resolver is not inside findGenerationPoint")
    prefix = source[method_start:m.start()]
    context_candidates = re.findall(
        r"(?:Structure\.)?GenerationContext\s+([A-Za-z_$][A-Za-z0-9_$]*)",
        prefix,
    )
    if not context_candidates:
        fail("could not infer GenerationContext variable")
    context = context_candidates[-1]

    replacement = (
        f"{m.group('indent')}int {m.group('var')} = {HOOK}(\n"
        f"{m.group('indent')}    {context}, this.startPool, {m.group('call')}\n"
        f"{m.group('indent')});"
    )
    patched = source[:m.start()] + replacement + source[m.end():]
    if patched.count(HOOK) != 1:
        fail("NeverOverworld resolver was not injected exactly once")
    return patched


def self_test() -> None:
    spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    fixture = '''class JigsawStructure {
    Optional findGenerationPoint(Structure.GenerationContext context) {
        int startY = NeverNetherStructurePlacement.resolveStartY(context, this.startPool, this.startHeight.sample(context.random(), new WorldGenerationContext(context.chunkGenerator(), context.heightAccessor())));
        if (startY == NeverNetherStructurePlacement.REJECT_Y) {
            return Optional.empty();
        }
        return Optional.empty();
    }
}
'''
    patched = patch_jigsaw(fixture)
    if patched.count(HOOK) != 1 or patched.count(NETHER_HOOK) != 1:
        fail("SELF-TEST: resolver chain was not preserved")
    helper = helper_source(spec)
    for marker in (
        "neverfolia:never_overworld/start/neverfolia__buried_sanctum",
        "neverfolia:never_overworld/start/neverfolia__flooded_ruins",
        "Mode.ROCK_MASS",
        "Mode.CAVERN_EDGE",
        "Mode.CAVERN_FLOOR",
        "Mode.WATER_BOUNDARY",
        "Mode.FLOODED_FLOOR",
        "getBaseColumn(",
        "FluidTags.WATER",
        f"REJECT_Y = {REJECT_SENTINEL}",
    ):
        if marker not in helper:
            fail(f"SELF-TEST: helper missing {marker!r}")
    for forbidden in ("getChunk(", "getChunkNow(", "getChunkAt(", "setBlock(", "setBlockState("):
        if forbidden in helper:
            fail(f"SELF-TEST: generation-time chunk dependency present: {forbidden!r}")
    print("[NeverFolia][NeverOverworld placement hook] SELF-TEST OK")


def main() -> None:
    if len(sys.argv) == 2 and sys.argv[1] == "--self-test":
        self_test()
        return
    if len(sys.argv) != 2:
        fail("usage: apply-never-overworld-placement-hook.py /path/to/.work/Folia | --self-test")

    folia = Path(sys.argv[1]).resolve()
    jigsaw = folia / JIGSAW_REL
    helper = folia / HELPER_REL
    if not jigsaw.is_file():
        fail(f"JigsawStructure source not found: {jigsaw}")

    spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    jigsaw.write_text(patch_jigsaw(jigsaw.read_text(encoding="utf-8")), encoding="utf-8")
    helper.write_text(helper_source(spec), encoding="utf-8")
    print("[NeverFolia][NeverOverworld placement hook] applied")
    print(f"  JigsawStructure: {jigsaw}")
    print(f"  helper: {helper}")
    print("  chained after NeverNether resolver: yes")
    print("  custom profiles: 8")


if __name__ == "__main__":
    main()
