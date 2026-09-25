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

CACHE_RECONCILE = """    public static int reconcileSeams(
        final WorldGenLevel level,
        final StaticCache2D<GenerationChunkHolder> cache,
        final ChunkAccess owner
    ) {
        if (level == null || cache == null || owner == null) return 0;
        if (!level.getLevel().dimension().equals(Level.OVERWORLD)
            || level.getMinY() != -512 || level.getHeight() != 1024) return 0;
        final int minY = Math.max(SCAN_MIN_Y, owner.getMinY() + 1);
        final int maxY = Math.min(SCAN_MAX_Y, owner.getMaxY() - 1);
        if (minY > maxY) return 0;

        final boolean[] connected = cacheOceanConnectedOwner(cache, owner, minY, maxY);
        final int west = countOwnerEdge(connected, minY, maxY, 0, true);
        final int east = countOwnerEdge(connected, minY, maxY, 15, true);
        final int north = countOwnerEdge(connected, minY, maxY, 0, false);
        final int south = countOwnerEdge(connected, minY, maxY, 15, false);
        final int changed = floodConnectedOwner(owner, connected, minY, maxY);

        if (Boolean.getBoolean("neverfolia.debugFloodSeams")) {
            System.out.println(
                "[NeverFolia][R22Seam] chunk=" + owner.getPos().x() + "," + owner.getPos().z()
                + " seeds=" + west + "," + east + "," + north + "," + south
                + " total=" + (west + east + north + south) + " changed=" + changed
            );
        }
        return changed;
    }

"""

CACHE_METHODS = """    private static final int CACHE_GRID_WIDTH = 48;
    private static final int CACHE_OWNER_OFFSET = 16;

    private static boolean[] cacheOceanConnectedOwner(
        final StaticCache2D<GenerationChunkHolder> cache,
        final ChunkAccess owner,
        final int minY,
        final int maxY
    ) {
        final int layers = maxY - minY + 1;
        final int area = CACHE_GRID_WIDTH * CACHE_GRID_WIDTH;
        final int capacity = layers * area;
        final boolean[] connected = new boolean[capacity];
        final int[] queue = new int[capacity];
        int head = 0;
        int tail = 0;
        final int ownerBaseX = owner.getPos().getMinBlockX();
        final int ownerBaseZ = owner.getPos().getMinBlockZ();
        final BlockPos.MutableBlockPos pos = new BlockPos.MutableBlockPos();

        for (int gz = 0; gz < CACHE_GRID_WIDTH; ++gz) {
            final int worldZ = ownerBaseZ - CACHE_OWNER_OFFSET + gz;
            final int chunkZ = Math.floorDiv(worldZ, 16);
            final int localZ = Math.floorMod(worldZ, 16);
            for (int gx = 0; gx < CACHE_GRID_WIDTH; ++gx) {
                final int worldX = ownerBaseX - CACHE_OWNER_OFFSET + gx;
                final int chunkX = Math.floorDiv(worldX, 16);
                final int localX = Math.floorMod(worldX, 16);
                final ChunkAccess source = cachedFeaturesChunk(cache, owner, chunkX, chunkZ);
                if (source == null) continue;
                final int surfaceY = source.getHeight(Heightmap.Types.OCEAN_FLOOR_WG, localX, localZ);
                pos.set(worldX, SCAN_MAX_Y, worldZ);
                final BlockState state = source.getBlockState(pos);
                if (!surfaceOceanSeed(surfaceY, state) || !traversable(source, pos)) continue;
                final int e = cacheEncode(gx, SCAN_MAX_Y, gz, minY);
                if (!connected[e]) {
                    connected[e] = true;
                    queue[tail++] = e;
                }
            }
        }

        while (head < tail) {
            final int e = queue[head++];
            final int layer = e / area;
            final int rem = e - layer * area;
            final int gz = rem / CACHE_GRID_WIDTH;
            final int gx = rem - gz * CACHE_GRID_WIDTH;
            final int y = minY + layer;
            tail = enqueueCached(cache, owner, connected, queue, tail, gx - 1, y, gz, minY, maxY);
            tail = enqueueCached(cache, owner, connected, queue, tail, gx + 1, y, gz, minY, maxY);
            tail = enqueueCached(cache, owner, connected, queue, tail, gx, y, gz - 1, minY, maxY);
            tail = enqueueCached(cache, owner, connected, queue, tail, gx, y, gz + 1, minY, maxY);
            tail = enqueueCached(cache, owner, connected, queue, tail, gx, y - 1, gz, minY, maxY);
            tail = enqueueCached(cache, owner, connected, queue, tail, gx, y + 1, gz, minY, maxY);
        }

        final boolean[] ownerConnected = new boolean[layers * 256];
        for (int y = minY; y <= maxY; ++y) {
            for (int z = 0; z < 16; ++z) {
                for (int x = 0; x < 16; ++x) {
                    final int ge = cacheEncode(
                        CACHE_OWNER_OFFSET + x, y, CACHE_OWNER_OFFSET + z, minY
                    );
                    if (connected[ge]) ownerConnected[encode(x, y, z, minY)] = true;
                }
            }
        }
        return ownerConnected;
    }

    private static int enqueueCached(
        final StaticCache2D<GenerationChunkHolder> cache,
        final ChunkAccess owner,
        final boolean[] connected,
        final int[] queue,
        final int tailIn,
        final int gx,
        final int y,
        final int gz,
        final int minY,
        final int maxY
    ) {
        if (gx < 0 || gx >= CACHE_GRID_WIDTH || gz < 0 || gz >= CACHE_GRID_WIDTH
            || y < minY || y > maxY) return tailIn;
        final int e = cacheEncode(gx, y, gz, minY);
        if (connected[e]) return tailIn;

        final int worldX = owner.getPos().getMinBlockX() - CACHE_OWNER_OFFSET + gx;
        final int worldZ = owner.getPos().getMinBlockZ() - CACHE_OWNER_OFFSET + gz;
        final int chunkX = Math.floorDiv(worldX, 16);
        final int chunkZ = Math.floorDiv(worldZ, 16);
        final ChunkAccess source = cachedFeaturesChunk(cache, owner, chunkX, chunkZ);
        if (source == null) return tailIn;

        final BlockPos pos = new BlockPos(worldX, y, worldZ);
        if (!traversable(source, pos)) return tailIn;
        connected[e] = true;
        queue[tailIn] = e;
        return tailIn + 1;
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

    private static int floodConnectedOwner(
        final ChunkAccess owner,
        final boolean[] connected,
        final int minY,
        final int maxY
    ) {
        int changed = 0;
        final int baseX = owner.getPos().getMinBlockX();
        final int baseZ = owner.getPos().getMinBlockZ();
        final BlockPos.MutableBlockPos pos = new BlockPos.MutableBlockPos();
        final BlockState water = Blocks.WATER.defaultBlockState();
        for (int y = minY; y <= maxY; ++y) {
            for (int z = 0; z < 16; ++z) {
                for (int x = 0; x < 16; ++x) {
                    final int e = encode(x, y, z, minY);
                    if (!connected[e]) continue;
                    pos.set(baseX + x, y, baseZ + z);
                    final BlockState state = owner.getBlockState(pos);
                    if (!state.is(Blocks.WATER) && traversable(owner, pos)) {
                        owner.setBlockState(pos, water, 0);
                        ++changed;
                    }
                }
            }
        }
        return changed;
    }

    private static int countOwnerEdge(
        final boolean[] connected,
        final int minY,
        final int maxY,
        final int edge,
        final boolean xAxis
    ) {
        int count = 0;
        for (int y = minY; y < SCAN_MAX_Y; ++y) {
            for (int lateral = 0; lateral < 16; ++lateral) {
                final int x = xAxis ? edge : lateral;
                final int z = xAxis ? lateral : edge;
                if (connected[encode(x, y, z, minY)]) ++count;
            }
        }
        return count;
    }

    private static int cacheEncode(
        final int gx,
        final int y,
        final int gz,
        final int minY
    ) {
        return ((y - minY) * CACHE_GRID_WIDTH * CACHE_GRID_WIDTH)
            + gz * CACHE_GRID_WIDTH + gx;
    }

"""

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

    if "cacheOceanConnectedOwner(" not in text:
        start = text.find("    public static int reconcileSeams(")
        end = text.find("    private static int seedFromNeighbor(", start)
        require(start >= 0 and end > start, "R21 reconcileSeams block missing/drifted")
        text = text[:start] + CACHE_RECONCILE + CACHE_METHODS + text[end:]

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
        "cacheOceanConnectedOwner",
        "cachedFeaturesChunk",
        "CACHE_GRID_WIDTH = 48",
        "getChunkIfPresent(ChunkStatus.FEATURES)",
        "floodConnectedOwner",
    ):
        require(marker in text, "R22 marker missing: " + marker)
    require("if (!chunk.getBlockState(pos).is(Blocks.WATER)) continue;" not in text,
            "R21 scheduling-dependent WATER-only seed survived")
    require("if (seeded == 0) return 0;" not in text,
            "R22 must not skip owner-local ocean components when neighbours add no seed")
    for forbidden in (
        "seedOceanProximityFallback",
        "nearOceanColumns",
        "proximityFallbackAllowed",
        "proximityConnectedFloodable",
        "neighborProximityWater",
        "hasProximitySeed",
        "R22ProximityFlood",
    ):
        require(forbidden not in text,
                "R22 must not infer ocean connectivity from proximity: " + forbidden)
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
    require("CACHE_GRID_WIDTH = 48" in CACHE_METHODS
            and "cacheOceanConnectedOwner" in CACHE_METHODS
            and "getChunkIfPresent(ChunkStatus.FEATURES)" in CACHE_METHODS,
            "SELF-TEST 3x3 cache connectivity helper missing")
    require("floodConnectedOwner" in CACHE_RECONCILE,
            "SELF-TEST reconcile must use cache-proven connectivity")
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
