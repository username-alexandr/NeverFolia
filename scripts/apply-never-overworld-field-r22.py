#!/usr/bin/env python3
"""FIELD-R22: scheduling-independent prospective ocean seeds for seam reconciliation.

R21 moved seam reconciliation into Folia's real Moonrise LIGHT runtime, but it
classified a FEATURES neighbour as ocean-connected only when that neighbour had
already been flooded and therefore already contained WATER at Y=128. LIGHT task
order could consequently leave deterministic WATER/AIR walls.

R22 keeps an already-present Y=128 WATER block as an authoritative ocean seed
and additionally derives a *prospective* seed from OCEAN_FLOOR_WG when the
FEATURES neighbour has not been flooded yet. A cave component is flood-eligible
only when a continuous floodable path reaches one of those Y=128 ocean seeds.
Horizontal distance/proximity to an ocean column is deliberately NOT evidence
of connectivity. The implementation reads only already-built FEATURES
ChunkAccess instances from R21's StaticCache2D, never synchronously loads a
chunk, and never writes a neighbour.
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

SEAM_SCAN_DECL_OLD = "        int head=0,tail=0;boolean hasOceanSeed=false,touchesHorizontalSeam=false;\n"
SEAM_SCAN_DECL_NEW = "        int head=0,tail=0;boolean hasOceanSeed=false,hasExternalSeed=false,touchesHorizontalSeam=false;\n"
SEAM_EXTERNAL_OLD = "            if(externalSeeds!=null&&externalSeeds[e]&&chunk.getBlockState(pos).is(Blocks.WATER))hasOceanSeed=true;\n"
SEAM_EXTERNAL_NEW = """            if(externalSeeds!=null&&externalSeeds[e]&&chunk.getBlockState(pos).is(Blocks.WATER)){
                hasOceanSeed=true;
                hasExternalSeed=true;
            }
"""
SEAM_CONFIRM_ANCHOR = "        if(!allowSeams&&touchesHorizontalSeam)return 0;\n"
SEAM_CONFIRM_NEW = """        if(allowSeams&&touchesHorizontalSeam&&!hasExternalSeed)return 0;
        if(!allowSeams&&touchesHorizontalSeam)return 0;
"""


CACHE_METHODS = r'''    /**
     * Compute each already-present radius-1 FEATURES chunk's ocean-connected
     * cells from only real/prospective Y128 ocean seeds. These local masks are
     * immutable inputs for the symmetric per-seam domains below.
     */
    private static boolean[][] localOceanConnectedMasks(
        final StaticCache2D<GenerationChunkHolder> cache,
        final ChunkAccess owner,
        final int minY,
        final int maxY
    ) {
        final boolean[][] masks = new boolean[9][];
        final ChunkPos cp = owner.getPos();
        for (int dz = -1; dz <= 1; ++dz) {
            for (int dx = -1; dx <= 1; ++dx) {
                final int index = cacheMaskIndex(dx, dz);
                final ChunkAccess chunk = cachedFeaturesChunk(cache, owner, cp.x() + dx, cp.z() + dz);
                if (chunk != null) {
                    masks[index] = oceanConnectedFloodable(chunk, minY, maxY);
                }
            }
        }
        return masks;
    }

    /**
     * Return the neighbour-side ocean mask for one owner<->neighbour seam.
     *
     * Both LIGHT tasks for the same seam must make the same decision. Their
     * radius-1 caches overlap in exactly 2x3 chunks for an X seam or 3x2 for a
     * Z seam. Restrict cross-chunk propagation to that common domain, while
     * starting from the same per-chunk Y128 seed masks. The result is therefore
     * scheduling-independent without any distance/proximity heuristic.
     */
    private static boolean[] pairNeighborOceanMask(
        final StaticCache2D<GenerationChunkHolder> cache,
        final ChunkAccess owner,
        final int neighborChunkX,
        final int neighborChunkZ,
        final int minY,
        final int maxY,
        final boolean[][] localMasks
    ) {
        final ChunkPos cp = owner.getPos();
        final int deltaX = neighborChunkX - cp.x();
        final int deltaZ = neighborChunkZ - cp.z();
        if (Math.abs(deltaX) + Math.abs(deltaZ) != 1) return null;

        final boolean xAxis = deltaX != 0;
        final int minChunkX = xAxis ? Math.min(cp.x(), neighborChunkX) : cp.x() - 1;
        final int maxChunkX = xAxis ? Math.max(cp.x(), neighborChunkX) : cp.x() + 1;
        final int minChunkZ = xAxis ? cp.z() - 1 : Math.min(cp.z(), neighborChunkZ);
        final int maxChunkZ = xAxis ? cp.z() + 1 : Math.max(cp.z(), neighborChunkZ);
        final int width = maxChunkX - minChunkX + 1;
        final int height = maxChunkZ - minChunkZ + 1;
        if (width * height != 6) return null;

        final ChunkAccess[] chunks = new ChunkAccess[6];
        final boolean[][] masks = new boolean[6][];
        for (int chunkZ = minChunkZ; chunkZ <= maxChunkZ; ++chunkZ) {
            for (int chunkX = minChunkX; chunkX <= maxChunkX; ++chunkX) {
                final int index = (chunkZ - minChunkZ) * width + (chunkX - minChunkX);
                final ChunkAccess chunk = cachedFeaturesChunk(cache, owner, chunkX, chunkZ);
                if (chunk == null) return null;
                final int localIndex = cacheMaskIndex(chunkX - cp.x(), chunkZ - cp.z());
                if (localIndex < 0 || localMasks[localIndex] == null) return null;
                chunks[index] = chunk;
                masks[index] = localMasks[localIndex].clone();
            }
        }

        final int capacity = (maxY - minY + 1) * 256;
        final int[] queue = new int[capacity];
        boolean changed;
        do {
            changed = false;
            for (int z = 0; z < height; ++z) {
                for (int x = 0; x + 1 < width; ++x) {
                    final int first = z * width + x;
                    final int second = first + 1;
                    changed |= bridgeMasks(
                        chunks[first], masks[first], 15,
                        chunks[second], masks[second], 0,
                        true, minY, maxY, queue
                    );
                }
            }
            for (int z = 0; z + 1 < height; ++z) {
                for (int x = 0; x < width; ++x) {
                    final int first = z * width + x;
                    final int second = first + width;
                    changed |= bridgeMasks(
                        chunks[first], masks[first], 15,
                        chunks[second], masks[second], 0,
                        false, minY, maxY, queue
                    );
                }
            }
        } while (changed);

        final int neighborIndex =
            (neighborChunkZ - minChunkZ) * width + (neighborChunkX - minChunkX);
        return masks[neighborIndex];
    }

    private static boolean bridgeMasks(
        final ChunkAccess first,
        final boolean[] firstMask,
        final int firstEdge,
        final ChunkAccess second,
        final boolean[] secondMask,
        final int secondEdge,
        final boolean xAxis,
        final int minY,
        final int maxY,
        final int[] queue
    ) {
        boolean changed = false;
        for (int y = minY; y < SCAN_MAX_Y; ++y) {
            for (int lateral = 0; lateral < 16; ++lateral) {
                final int fx = xAxis ? firstEdge : lateral;
                final int fz = xAxis ? lateral : firstEdge;
                final int sx = xAxis ? secondEdge : lateral;
                final int sz = xAxis ? lateral : secondEdge;
                final int fe = encode(fx, y, fz, minY);
                final int se = encode(sx, y, sz, minY);
                if (firstMask[fe] && !secondMask[se]) {
                    changed |= expandMaskFromSeed(second, secondMask, queue, sx, y, sz, minY, maxY);
                }
                if (secondMask[se] && !firstMask[fe]) {
                    changed |= expandMaskFromSeed(first, firstMask, queue, fx, y, fz, minY, maxY);
                }
            }
        }
        return changed;
    }

    private static boolean expandMaskFromSeed(
        final ChunkAccess chunk,
        final boolean[] connected,
        final int[] queue,
        final int seedX,
        final int seedY,
        final int seedZ,
        final int minY,
        final int maxY
    ) {
        final int seed = encode(seedX, seedY, seedZ, minY);
        if (connected[seed]) return false;
        final BlockPos seedPos = new BlockPos(
            chunk.getPos().getMinBlockX() + seedX,
            seedY,
            chunk.getPos().getMinBlockZ() + seedZ
        );
        if (!traversable(chunk, seedPos)) return false;

        int head = 0;
        int tail = 0;
        connected[seed] = true;
        queue[tail++] = seed;
        while (head < tail) {
            final int e = queue[head++];
            final int x = e & 15;
            final int z = (e >>> 4) & 15;
            final int y = minY + (e >>> 8);
            tail = enqueueFloodable(chunk, connected, queue, tail, x - 1, y, z, minY, maxY);
            tail = enqueueFloodable(chunk, connected, queue, tail, x + 1, y, z, minY, maxY);
            tail = enqueueFloodable(chunk, connected, queue, tail, x, y, z - 1, minY, maxY);
            tail = enqueueFloodable(chunk, connected, queue, tail, x, y, z + 1, minY, maxY);
            tail = enqueueFloodable(chunk, connected, queue, tail, x, y - 1, z, minY, maxY);
            tail = enqueueFloodable(chunk, connected, queue, tail, x, y + 1, z, minY, maxY);
        }
        return true;
    }

    private static ChunkAccess cachedFeaturesChunk(
        final StaticCache2D<GenerationChunkHolder> cache,
        final ChunkAccess owner,
        final int chunkX,
        final int chunkZ
    ) {
        final ChunkPos cp = owner.getPos();
        if (cp.x() == chunkX && cp.z() == chunkZ) return owner;
        if (!cache.contains(chunkX, chunkZ)) return null;
        final GenerationChunkHolder holder = cache.get(chunkX, chunkZ);
        return holder == null ? null : holder.getChunkIfPresent(ChunkStatus.FEATURES);
    }

    private static int cacheMaskIndex(final int dx, final int dz) {
        if (dx < -1 || dx > 1 || dz < -1 || dz > 1) return -1;
        return (dz + 1) * 3 + (dx + 1);
    }

'''
CACHE_METHODS_ANCHOR = "    private static int seedFromNeighbor(\n"


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

    # R22 must not infer ocean connectivity from distance, component size or a
    # seam touch. Compute local Y128 seed masks once, then make each seam
    # decision inside the 2x3/3x2 FEATURES-cache intersection shared by both
    # adjacent LIGHT tasks.
    if "reconcileSeams(" in text:
        if "pairNeighborOceanMask(" not in text:
            require(CACHE_METHODS_ANCHOR in text, "R22 pair-mask insertion anchor missing")
            text = text.replace(CACHE_METHODS_ANCHOR, CACHE_METHODS + CACHE_METHODS_ANCHOR, 1)

        cache_anchor = "        final boolean[] externalSeeds = new boolean[(maxY - minY + 1) * 256];\n"
        cache_line = "        final boolean[][] localOceanMasks = localOceanConnectedMasks(cache, owner, minY, maxY);\n"
        if cache_line not in text:
            require(text.count(cache_anchor) == 1, "R22 local-mask reconcile anchor missing")
            text = text.replace(cache_anchor, cache_anchor + cache_line, 1)

        old_calls = ", minY, maxY, externalSeeds);"
        new_calls = ", minY, maxY, externalSeeds, localOceanMasks);"
        if new_calls not in text:
            require(text.count(old_calls) == 4, "R22 neighbour seed call count drifted")
            text = text.replace(old_calls, new_calls)

        old_signature = """        final int maxY,
        final boolean[] externalSeeds
    ) {"""
        new_signature = """        final int maxY,
        final boolean[] externalSeeds,
        final boolean[][] localOceanMasks
    ) {"""
        if new_signature not in text:
            require(text.count(old_signature) == 1, "R22 seedFromNeighbor signature anchor missing")
            text = text.replace(old_signature, new_signature, 1)

        old_mask = "        final boolean[] neighborOceanWater = oceanConnectedFloodable(neighbor, minY, maxY);\n"
        new_mask = """        final boolean[] neighborOceanWater = pairNeighborOceanMask(
            cache, owner, neighborChunkX, neighborChunkZ, minY, maxY, localOceanMasks
        );
        if (neighborOceanWater == null) return 0;
"""
        if new_mask not in text:
            require(text.count(old_mask) == 1, "R22 local-neighbour mask anchor missing")
            text = text.replace(old_mask, new_mask, 1)
    if SEAM_SCAN_DECL_NEW not in text:
        require(text.count(SEAM_SCAN_DECL_OLD) == 1, "R22 seam scan declaration anchor missing")
        text = text.replace(SEAM_SCAN_DECL_OLD, SEAM_SCAN_DECL_NEW, 1)
    if SEAM_EXTERNAL_NEW not in text:
        require(text.count(SEAM_EXTERNAL_OLD) == 1, "R22 external-seed scan anchor missing")
        text = text.replace(SEAM_EXTERNAL_OLD, SEAM_EXTERNAL_NEW, 1)
    if SEAM_CONFIRM_NEW not in text:
        require(text.count(SEAM_CONFIRM_ANCHOR) == 1, "R22 seam confirmation anchor missing")
        text = text.replace(SEAM_CONFIRM_ANCHOR, SEAM_CONFIRM_NEW, 1)

    require("seedOceanProximityFallback(" not in text,
            "unsafe R22 proximity fallback already present in input")
    require("proximityConnectedFloodable(" not in text,
            "unsafe R22 proximity neighbour mask already present in input")
    require("neighborProximityWater" not in text,
            "unsafe R22 proximity neighbour gate already present in input")
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
        "localOceanConnectedMasks",
        "pairNeighborOceanMask",
        "bridgeMasks",
        "expandMaskFromSeed",
        "cachedFeaturesChunk",
        "final boolean[][] localOceanMasks = localOceanConnectedMasks(cache, owner, minY, maxY);",
        "final boolean[] neighborOceanWater = pairNeighborOceanMask(",
        "if (!neighborOceanWater[ne]) continue;",
        "boolean hasOceanSeed=false,hasExternalSeed=false,touchesHorizontalSeam=false",
        "hasExternalSeed=true;",
        "if(allowSeams&&touchesHorizontalSeam&&!hasExternalSeed)return 0;",
    ):
        require(marker in text, "R22 strict-ocean marker missing: " + marker)

    for forbidden in (
        "seedOceanProximityFallback",
        "nearOceanColumns",
        "proximityFallbackAllowed",
        "proximityConnectedFloodable",
        "neighborProximityWater",
        "hasProximitySeed",
        "R22ProximityFlood",
    ):
        require(forbidden not in text, "unsafe proximity flood logic survived: " + forbidden)

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
    require("cache.contains(chunkX, chunkZ)" in text
            and "holder.getChunkIfPresent(ChunkStatus.FEATURES)" in text,
            "R22 cache traversal must use only already-present FEATURES chunks")
    print("[FIELD-R22] symmetric pair-domain Y128 ocean-connectivity invariants OK")

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
        "nearOceanColumns",
        "neighborProximityWater",
        "proximityFallbackAllowed",
    ):
        require(forbidden not in out, "SELF-TEST proximity flood survived: " + forbidden)
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
    print("[FIELD-R22] STRICT-OCEAN SELF-TEST OK")

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
    print("[FIELD-R22] installed: symmetric pair-domain Y128 ocean connectivity + obsolete R8/proximity fallbacks retired")

if __name__ == "__main__":
    main()
