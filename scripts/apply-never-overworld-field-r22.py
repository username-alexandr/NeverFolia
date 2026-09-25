#!/usr/bin/env python3
"""FIELD-R22: scheduling-independent prospective ocean seeds for seam reconciliation.

R21 moved seam reconciliation into Folia's real Moonrise LIGHT runtime, but it
classified a FEATURES neighbour as ocean-connected only when that neighbour had
already been flooded and therefore already contained WATER at Y=128. LIGHT task
order could consequently leave deterministic WATER/AIR walls.

R22 keeps an already-present Y=128 WATER block as an authoritative ocean seed
and additionally derives a *prospective* seed from OCEAN_FLOOR_WG when the
FEATURES neighbour has not been flooded yet. Crucially, proximity to an ocean
is not a flood seed: sealed cave components stay dry unless connectivity to an
actual/prospective surface-ocean component is proven across the FEATURES cache.
"""
from __future__ import annotations

import argparse
from pathlib import Path

JAVA = Path("folia-server/src/minecraft/java")
FLOOD = JAVA / "net/minecraft/world/level/chunk/NeverOverworldFlood.java"
FLOOD15 = JAVA / "net/minecraft/world/level/chunk/NeverOverworldFloodConnectivityR15.java"
R8_CALL = "        floodLargeBoundaryConnectedCaverns(chunk, minY, FLOOD_LEVEL, water);\n"
R15_CALL = "NeverOverworldFloodConnectivityR15.apply(level, chunk);"

IMPORT = "import net.minecraft.world.level.levelgen.Heightmap;\n"
IMPORT_ANCHOR = "import net.minecraft.world.level.block.state.BlockState;\n"

OLD_SEEDS = """        for (int z = 0; z < 16; ++z) for (int x = 0; x < 16; ++x) {
            pos.set(baseX + x, SCAN_MAX_Y, baseZ + z);
            if (!chunk.getBlockState(pos).is(Blocks.WATER)) continue;
            final int e = encode(x, SCAN_MAX_Y, z, minY);
            connected[e] = true;
            queue[tail++] = e;
        }
"""

NEW_SEEDS = """        for (int z = 0; z < 16; ++z) for (int x = 0; x < 16; ++x) {
            final int surfaceY = chunk.getHeight(Heightmap.Types.OCEAN_FLOOR_WG, x, z);
            pos.set(baseX + x, SCAN_MAX_Y, baseZ + z);
            final BlockState state = chunk.getBlockState(pos);
            if (!surfaceOceanSeed(surfaceY, state)) continue;
            if (!traversable(chunk, pos)) continue;
            final int e = encode(x, SCAN_MAX_Y, z, minY);
            connected[e] = true;
            queue[tail++] = e;
        }
"""

HELPER = """    static boolean prospectiveOceanSurfaceSeed(final int surfaceY, final BlockState state) {
        return surfaceY < SCAN_MAX_Y && isFloodable(state);
    }

    static boolean surfaceOceanSeed(final int surfaceY, final BlockState state) {
        return state.is(Blocks.WATER) || prospectiveOceanSurfaceSeed(surfaceY, state);
    }

"""

HELPER_ANCHOR = "    static boolean[] oceanConnectedFloodable(final ChunkAccess chunk, final int minY, final int maxY) {\n"

PROXIMITY_METHODS_ANCHOR = "    private static int seedFromNeighbor(\n"

def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError("[FIELD-R22] " + message)

def patch_r8(text: str) -> str:
    """Retire the pre-R21 geometry-only cavern heuristic.

    R8 treated a large chunk-border cavern as ocean-open using only component
    size/boundary/vertical-span thresholds. Once R21/R22 has real neighbour
    connectivity, that heuristic is both redundant and unsafe: it can create
    deep source-water in a non-ocean component, which the verified R15 audit
    intentionally does not propagate into the adjacent chunk. The result is the
    exact WATER/AIR wall seen in the user seed.

    Keep the historical helper method in source for auditability, but remove its
    production call. New-world generation then has a single authority for deep
    flooding: verified R15/R22 ocean connectivity.
    """
    if R8_CALL not in text:
        return text
    require(text.count(R8_CALL) == 1, "R8 cavern fallback call duplicated/drifted")
    require("floodLargeBoundaryConnectedCaverns(" in text,
            "R8 helper method missing while its call is present")
    require(R15_CALL in text, "final R15 verified-ocean flood call missing")
    return text.replace(R8_CALL, "", 1)

def patch(text: str) -> str:
    if IMPORT not in text:
        require(IMPORT_ANCHOR in text, "Heightmap import anchor missing")
        text = text.replace(IMPORT_ANCHOR, IMPORT_ANCHOR + IMPORT, 1)

    if "static boolean surfaceOceanSeed(" not in text:
        require("static boolean prospectiveOceanSurfaceSeed(" not in text,
                "partial R22 helper set found")
        require(HELPER_ANCHOR in text, "oceanConnectedFloodable anchor missing")
        text = text.replace(HELPER_ANCHOR, HELPER + HELPER_ANCHOR, 1)

    if NEW_SEEDS not in text:
        require(text.count(OLD_SEEDS) == 1, "R21 existing-water seed block missing/drifted")
        text = text.replace(OLD_SEEDS, NEW_SEEDS, 1)

    # R21 already propagates only ocean-connected neighbour components.
    # NEW_SEEDS above makes that classification scheduling-independent without
    # inventing any proximity-based cave seed. Keep the strict R15 guard:
    # a component without an actual/prospective ocean seed remains dry.
    return text

def verify(folia: Path) -> None:
    flood_path = folia / FLOOD
    path = folia / FLOOD15
    require(flood_path.is_file(), "NeverOverworldFlood missing")
    require(path.is_file(), "R15/R21 flood helper missing")
    flood = flood_path.read_text(encoding="utf-8")
    text = path.read_text(encoding="utf-8")
    require(R8_CALL.strip() not in flood,
            "obsolete R8 geometry-only cavern flood call survived R22")
    require("floodLargeBoundaryConnectedCaverns(" in flood,
            "historical R8 helper unexpectedly disappeared; only the call should be retired")
    require(R15_CALL in flood,
            "final verified R15 ocean-connectivity flood call missing")
    for marker in (
        "import net.minecraft.world.level.levelgen.Heightmap;",
        "prospectiveOceanSurfaceSeed",
        "surfaceOceanSeed",
        "chunk.getHeight(Heightmap.Types.OCEAN_FLOOR_WG, x, z)",
        "surfaceY < SCAN_MAX_Y && isFloodable(state)",
        "state.is(Blocks.WATER) || prospectiveOceanSurfaceSeed(surfaceY, state)",
        "if (!surfaceOceanSeed(surfaceY, state)) continue;",
        "if (!traversable(chunk, pos)) continue;",
        "getChunkIfPresent(ChunkStatus.FEATURES)",
        "reconcileSeams",
    ):
        require(marker in text, "R22 marker missing: " + marker)
    for forbidden in (
        "seedOceanProximityFallback",
        "nearOceanColumns",
        "proximityFallbackAllowed",
        "proximityConnectedFloodable",
        "neighborProximityWater",
        "hasProximitySeed",
        "R22ProximityFlood",
    ):
        require(forbidden not in text, "unsafe R22 proximity cave flood survived: " + forbidden)
    require("if (!chunk.getBlockState(pos).is(Blocks.WATER)) continue;" not in text,
            "R21 scheduling-dependent WATER-only seed survived")
    require("if (seeded == 0) return 0;" not in text,
            "R22 must not skip owner-local ocean components when neighbours add no seed")
    require(
        "return floodVerifiedComponents(owner, externalSeeds, true);" in text
        or "final int changed = floodVerifiedComponents(owner, externalSeeds, true);" in text,
        "R22 seam-capable owner pass missing"
    )
    require("getChunk(" not in text and "level.getBlockState(" not in text,
            "R22 must not synchronously load/read neighbours through level")
    print("[FIELD-R22] existing + prospective OCEAN_FLOOR_WG seam seeds invariants OK")

def self_test() -> None:
    fixture = """package net.minecraft.world.level.chunk;
import net.minecraft.world.level.block.state.BlockState;
class X {
    static final int SCAN_MAX_Y = 128;
    static boolean isFloodable(BlockState state){ return true; }
    static boolean traversable(ChunkAccess chunk, BlockPos pos){ return true; }
    static boolean[] oceanConnectedFloodable(final ChunkAccess chunk, final int minY, final int maxY) {
        final int capacity = (maxY - minY + 1) * 256;
        final boolean[] connected = new boolean[capacity];
        final int[] queue = new int[capacity];
        int head = 0, tail = 0;
        final int baseX = chunk.getPos().getMinBlockX();
        final int baseZ = chunk.getPos().getMinBlockZ();
        final BlockPos.MutableBlockPos pos = new BlockPos.MutableBlockPos();

        for (int z = 0; z < 16; ++z) for (int x = 0; x < 16; ++x) {
            pos.set(baseX + x, SCAN_MAX_Y, baseZ + z);
            if (!chunk.getBlockState(pos).is(Blocks.WATER)) continue;
            final int e = encode(x, SCAN_MAX_Y, z, minY);
            connected[e] = true;
            queue[tail++] = e;
        }
        return connected;
    }
}
"""
    out = patch(fixture)
    require("OCEAN_FLOOR_WG" in out, "SELF-TEST prospective seed not installed")
    require("surfaceOceanSeed" in out, "SELF-TEST combined seed predicate not installed")
    require("state.is(Blocks.WATER) || prospectiveOceanSurfaceSeed" in out,
            "SELF-TEST existing WATER preservation missing")
    require("if (!chunk.getBlockState(pos).is(Blocks.WATER)) continue;" not in out,
            "SELF-TEST old WATER-only seed survived")
    for forbidden in (
        "seedOceanProximityFallback",
        "proximityConnectedFloodable",
        "proximityFallbackAllowed",
        "neighborProximityWater",
        "hasProximitySeed",
    ):
        require(forbidden not in out, "SELF-TEST unsafe proximity flood installed: "+forbidden)
    require(patch(out) == out, "SELF-TEST transformer is not idempotent")

    flood_fixture = """class NeverOverworldFlood {
    void apply() {
        floodSurfaceConnectedVolume(chunk, minY, FLOOD_LEVEL, water);
        floodLargeBoundaryConnectedCaverns(chunk, minY, FLOOD_LEVEL, water);
        NeverOverworldFloodConnectivityR15.apply(level, chunk);
    }
    void floodLargeBoundaryConnectedCaverns(Object chunk, int minY, int maxY, Object water) {}
}
"""
    retired = patch_r8(flood_fixture)
    require(R8_CALL.strip() not in retired, "SELF-TEST R8 production call survived")
    require("void floodLargeBoundaryConnectedCaverns(" in retired,
            "SELF-TEST historical R8 helper should remain")
    require(R15_CALL in retired, "SELF-TEST final R15 call was lost")
    require(patch_r8(retired) == retired, "SELF-TEST R8 retirement is not idempotent")
    print("[FIELD-R22] SELF-TEST OK")

def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("folia", nargs="?", type=Path)
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--check-only", action="store_true")
    a = p.parse_args()
    if a.self_test:
        self_test()
        return
    if a.folia is None:
        p.error("folia worktree is required")
    folia = a.folia.resolve()
    if a.check_only:
        verify(folia)
        return
    self_test()
    flood_path = folia / FLOOD
    path = folia / FLOOD15
    require(flood_path.is_file(), "NeverOverworldFlood missing")
    require(path.is_file(), "R15/R21 flood helper missing")
    flood_path.write_text(patch_r8(flood_path.read_text(encoding="utf-8")), encoding="utf-8")
    path.write_text(patch(path.read_text(encoding="utf-8")), encoding="utf-8")
    verify(folia)
    print("[FIELD-R22] installed: strict ocean-connected prospective seam seeds; proximity cave flood disabled")

if __name__ == "__main__":
    main()
