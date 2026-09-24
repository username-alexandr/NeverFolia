#!/usr/bin/env python3
"""FIELD-R22: scheduling-independent prospective ocean seeds for seam reconciliation.

R21 moved seam reconciliation into Folia's real Moonrise LIGHT runtime, but it
classified a FEATURES neighbour as ocean-connected only when that neighbour had
already been flooded and therefore already contained WATER at Y=128. LIGHT task
order could consequently leave deterministic WATER/AIR walls.

R22 keeps an already-present Y=128 WATER block as an authoritative ocean seed
and additionally derives a *prospective* seed from OCEAN_FLOOR_WG when the
FEATURES neighbour has not been flooded yet. It reads only the already-built
FEATURES ChunkAccess from R21's StaticCache2D, never synchronously loads a chunk,
and never writes the neighbour.
"""
from __future__ import annotations

import argparse
from pathlib import Path

JAVA = Path("folia-server/src/minecraft/java")
FLOOD = JAVA / "net/minecraft/world/level/chunk/NeverOverworldFlood.java"
FLOOD15 = JAVA / "net/minecraft/world/level/chunk/NeverOverworldFloodConnectivityR15.java"
R8_CALL = "        floodLargeBoundaryConnectedCaverns(chunk, minY, FLOOD_LEVEL, water);\n"
R15_CALL = "NeverOverworldFloodConnectivityR15.apply(level, chunk);"
PROXIMITY_RADIUS = 12
PROXIMITY_MIN_SIZE = 768
PROXIMITY_MIN_BOUNDARY = 48
PROXIMITY_MIN_SPAN = 24

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

    static boolean proximityFallbackAllowed(
        final int componentSize,
        final int boundaryCells,
        final int verticalSpan,
        final boolean nearOcean
    ) {
        return nearOcean
            && componentSize >= 768
            && boundaryCells >= 48
            && verticalSpan >= 24;
    }

"""

HELPER_ANCHOR = "    static boolean[] oceanConnectedFloodable(final ChunkAccess chunk, final int minY, final int maxY) {\n"

PROXIMITY_METHODS = """    private static int seedOceanProximityFallback(
        final StaticCache2D<GenerationChunkHolder> cache,
        final ChunkAccess owner,
        final int minY,
        final int maxY,
        final boolean[] externalSeeds
    ) {
        final boolean[] nearOcean = nearOceanColumns(cache, owner);
        final int baseX = owner.getPos().getMinBlockX();
        final int baseZ = owner.getPos().getMinBlockZ();
        final BlockPos.MutableBlockPos pos = new BlockPos.MutableBlockPos();
        int marked = 0;
        for (int z = 0; z < 16; ++z) {
            for (int x = 0; x < 16; ++x) {
                if (!nearOcean[(z << 4) | x] || (x != 0 && x != 15 && z != 0 && z != 15)) continue;
                for (int y = minY; y < SCAN_MAX_Y; ++y) {
                    pos.set(baseX + x, y, baseZ + z);
                    if (!traversable(owner, pos)) continue;
                    final int e = encode(x, y, z, minY);
                    if (!externalSeeds[e]) {
                        externalSeeds[e] = true;
                        ++marked;
                    }
                }
            }
        }
        return marked;
    }

    private static boolean[] nearOceanColumns(
        final StaticCache2D<GenerationChunkHolder> cache,
        final ChunkAccess owner
    ) {
        final int radius = 12;
        final int width = 16 + 2 * radius;
        final boolean[] ocean = new boolean[width * width];
        final boolean[] near = new boolean[256];
        final ChunkPos ownerPos = owner.getPos();
        final int ownerBaseX = ownerPos.getMinBlockX();
        final int ownerBaseZ = ownerPos.getMinBlockZ();
        final BlockPos.MutableBlockPos pos = new BlockPos.MutableBlockPos();

        for (int gz = 0; gz < width; ++gz) {
            final int worldZ = ownerBaseZ - radius + gz;
            final int chunkZ = Math.floorDiv(worldZ, 16);
            final int localZ = Math.floorMod(worldZ, 16);
            for (int gx = 0; gx < width; ++gx) {
                final int worldX = ownerBaseX - radius + gx;
                final int chunkX = Math.floorDiv(worldX, 16);
                final int localX = Math.floorMod(worldX, 16);
                final ChunkAccess source = cachedFeaturesChunk(cache, owner, chunkX, chunkZ);
                if (source == null) continue;
                final int surfaceY = source.getHeight(Heightmap.Types.OCEAN_FLOOR_WG, localX, localZ);
                pos.set(worldX, SCAN_MAX_Y, worldZ);
                ocean[gz * width + gx] =
                    surfaceOceanSeed(surfaceY, source.getBlockState(pos));
            }
        }

        for (int z = 0; z < 16; ++z) {
            for (int x = 0; x < 16; ++x) {
                boolean found = false;
                final int centerX = x + radius;
                final int centerZ = z + radius;
                for (int dz = -radius; dz <= radius && !found; ++dz) {
                    final int row = (centerZ + dz) * width;
                    for (int dx = -radius; dx <= radius; ++dx) {
                        if (ocean[row + centerX + dx]) {
                            found = true;
                            break;
                        }
                    }
                }
                near[(z << 4) | x] = found;
            }
        }
        return near;
    }

    private static ChunkAccess cachedFeaturesChunk(
        final StaticCache2D<GenerationChunkHolder> cache,
        final ChunkAccess owner,
        final int chunkX,
        final int chunkZ
    ) {
        final ChunkPos ownerPos = owner.getPos();
        if (ownerPos.x() == chunkX && ownerPos.z() == chunkZ) return owner;
        if (!cache.contains(chunkX, chunkZ)) return null;
        final GenerationChunkHolder holder = cache.get(chunkX, chunkZ);
        return holder == null ? null : holder.getChunkIfPresent(ChunkStatus.FEATURES);
    }

"""
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

    if "reconcileSeams(" in text:
        if "seedOceanProximityFallback(" not in text:
            require(PROXIMITY_METHODS_ANCHOR in text, "R22 proximity method anchor missing")
            text = text.replace(PROXIMITY_METHODS_ANCHOR, PROXIMITY_METHODS + PROXIMITY_METHODS_ANCHOR, 1)

        if "final int proximity = seedOceanProximityFallback(" not in text:
            anchor = "        final int seeded = west + east + north + south;\n"
            require(anchor in text, "R22 reconcile seeded-count anchor missing")
            text = text.replace(
                anchor,
                anchor + "        final int proximity = seedOceanProximityFallback(cache, owner, minY, maxY, externalSeeds);\n",
                1,
            )

        old_scan_seed = "        int head=0,tail=0;boolean hasOceanSeed=false,touchesHorizontalSeam=false;\n"
        new_scan_seed = "        int head=0,tail=0;boolean hasOceanSeed=false,hasProximitySeed=false,touchesHorizontalSeam=false;\n"
        if new_scan_seed not in text:
            require(text.count(old_scan_seed) == 1, "R22 scan state anchor missing")
            text = text.replace(old_scan_seed, new_scan_seed, 1)

        old_external = "            if(externalSeeds!=null&&externalSeeds[e]&&chunk.getBlockState(pos).is(Blocks.WATER))hasOceanSeed=true;\n"
        new_external = """            if(externalSeeds!=null&&externalSeeds[e]){
                    if(chunk.getBlockState(pos).is(Blocks.WATER))hasOceanSeed=true;
                    else hasProximitySeed=true;
                }
    """
        if new_external not in text:
            require(text.count(old_external) == 1, "R22 external seed classification anchor missing")
            text = text.replace(old_external, new_external, 1)

        old_guard = """        if(!hasOceanSeed){
                if(allowSeams&&touchesHorizontalSeam&&tail>=64&&boundaryCells>=8
                    &&Boolean.getBoolean("neverfolia.debugFloodSeams")){
                    System.out.println(
                        "[NeverFolia][R22DrySeam] chunk="+chunk.getPos().x()+","+chunk.getPos().z()
                        +" size="+tail+" boundary="+boundaryCells
                        +" y="+componentMinY+":"+componentMaxY
                        +" sample="+sampleSeamX+","+sampleSeamY+","+sampleSeamZ
                    );
                }
                return 0;
            }
    """
        new_guard = """        if(!hasOceanSeed){
                final int verticalSpan=componentMaxY-componentMinY+1;
                final boolean proximityFallback=allowSeams&&touchesHorizontalSeam
                    &&proximityFallbackAllowed(tail,boundaryCells,verticalSpan,hasProximitySeed);
                if(!proximityFallback){
                    if(allowSeams&&touchesHorizontalSeam&&tail>=64&&boundaryCells>=8
                        &&Boolean.getBoolean("neverfolia.debugFloodSeams")){
                        System.out.println(
                            "[NeverFolia][R22DrySeam] chunk="+chunk.getPos().x()+","+chunk.getPos().z()
                            +" size="+tail+" boundary="+boundaryCells
                            +" y="+componentMinY+":"+componentMaxY
                            +" sample="+sampleSeamX+","+sampleSeamY+","+sampleSeamZ
                        );
                    }
                    return 0;
                }
                if(Boolean.getBoolean("neverfolia.debugFloodSeams")){
                    System.out.println(
                        "[NeverFolia][R22ProximityFlood] chunk="+chunk.getPos().x()+","+chunk.getPos().z()
                        +" size="+tail+" boundary="+boundaryCells
                        +" span="+verticalSpan+" nearOcean=true"
                    );
                }
            }
    """
        if new_guard not in text:
            require(text.count(old_guard) == 1, "R22 dry-seam guard anchor missing")
            text = text.replace(old_guard, new_guard, 1)
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
        "seedOceanProximityFallback",
        "nearOceanColumns",
        "proximityFallbackAllowed",
        "componentSize >= 768",
        "boundaryCells >= 48",
        "verticalSpan >= 24",
    ):
        require(marker in text, "R22 marker missing: " + marker)
    require("if (!chunk.getBlockState(pos).is(Blocks.WATER)) continue;" not in text,
            "R21 scheduling-dependent WATER-only seed survived")
    require("if (seeded == 0) return 0;" not in text,
            "R22 must not skip owner-local ocean components when neighbours add no seed")
    require("final int radius = 12;" in text,
            "R22 proximity radius drifted from measured 12-block bound")
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
    require("seedOceanProximityFallback" in PROXIMITY_METHODS,
            "SELF-TEST proximity seed pass missing")
    require("final int radius = 12;" in PROXIMITY_METHODS,
            "SELF-TEST proximity radius missing")
    require("componentSize >= 768" in HELPER
            and "boundaryCells >= 48" in HELPER
            and "verticalSpan >= 24" in HELPER,
            "SELF-TEST bounded proximity fallback policy missing")
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
    print("[FIELD-R22] installed: prospective seam seeds + obsolete R8 cavern fallback retired")

if __name__ == "__main__":
    main()
