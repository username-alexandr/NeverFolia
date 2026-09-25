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
IMPORT_BITSET = "import java.util.BitSet;\n"
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

CACHE_METHODS_ANCHOR = "    private static int seedFromNeighbor(\n"
FEATURE_HANDOFF_METHODS = """    private static final java.util.concurrent.ConcurrentHashMap<
        net.minecraft.server.level.ServerLevel,
        java.util.concurrent.ConcurrentHashMap<Long, BitSet>
    > FEATURE_BOUNDARY_SEEDS = new java.util.concurrent.ConcurrentHashMap<>();

    public static void publishFeatureBoundarySeeds(
        final net.minecraft.server.level.ServerLevel level,
        final ChunkAccess source
    ) {
        if (level == null || source == null
            || !level.dimension().equals(Level.OVERWORLD)
            || level.getMinY() != -512 || level.getHeight() != 1024) return;

        final int minY = Math.max(SCAN_MIN_Y, source.getMinY() + 1);
        final int maxY = Math.min(SCAN_MAX_Y, source.getMaxY() - 1);
        if (minY > maxY) return;

        final boolean[] verified = oceanConnectedFloodable(source, minY, maxY);
        final ChunkPos cp = source.getPos();
        publishFeatureBoundary(level, cp.x() - 1, cp.z(), verified, 0, 15, true, minY, maxY);
        publishFeatureBoundary(level, cp.x() + 1, cp.z(), verified, 15, 0, true, minY, maxY);
        publishFeatureBoundary(level, cp.x(), cp.z() - 1, verified, 0, 15, false, minY, maxY);
        publishFeatureBoundary(level, cp.x(), cp.z() + 1, verified, 15, 0, false, minY, maxY);
    }

    private static void publishFeatureBoundary(
        final net.minecraft.server.level.ServerLevel level,
        final int targetChunkX,
        final int targetChunkZ,
        final boolean[] verified,
        final int sourceFixed,
        final int targetFixed,
        final boolean xAxis,
        final int minY,
        final int maxY
    ) {
        final BitSet seeds = new BitSet((maxY - minY + 1) * 256);
        for (int y = minY; y <= maxY; ++y) {
            for (int transverse = 0; transverse < 16; ++transverse) {
                final int sx = xAxis ? sourceFixed : transverse;
                final int sz = xAxis ? transverse : sourceFixed;
                if (!verified[encode(sx, y, sz, minY)]) continue;
                final int tx = xAxis ? targetFixed : transverse;
                final int tz = xAxis ? transverse : targetFixed;
                seeds.set(encode(tx, y, tz, minY));
            }
        }
        if (seeds.isEmpty()) return;

        final long key = chunkKey(targetChunkX, targetChunkZ);
        final java.util.concurrent.ConcurrentHashMap<Long, BitSet> worldSeeds =
            FEATURE_BOUNDARY_SEEDS.computeIfAbsent(level, ignored -> new java.util.concurrent.ConcurrentHashMap<>());
        worldSeeds.compute(key, (ignored, existing) -> {
            if (existing == null) return (BitSet)seeds.clone();
            existing.or(seeds);
            return existing;
        });
    }

    private static long chunkKey(final int chunkX, final int chunkZ) {
        return ((long)chunkX & 0xffffffffL) | (((long)chunkZ & 0xffffffffL) << 32);
    }

    private static BitSet takeFeatureBoundarySeeds(
        final net.minecraft.server.level.ServerLevel level,
        final ChunkAccess owner
    ) {
        final java.util.concurrent.ConcurrentHashMap<Long, BitSet> worldSeeds = FEATURE_BOUNDARY_SEEDS.get(level);
        if (worldSeeds == null) return null;
        final ChunkPos ownerPos = owner.getPos();
        final BitSet ret = worldSeeds.remove(chunkKey(ownerPos.x(), ownerPos.z()));
        if (worldSeeds.isEmpty()) FEATURE_BOUNDARY_SEEDS.remove(level, worldSeeds);
        return ret;
    }

"""

OLD_RECONCILE = """    public static int reconcileSeams(final WorldGenLevel level, final StaticCache2D<GenerationChunkHolder> cache, final ChunkAccess owner) {
        if (level == null || cache == null || owner == null) return 0;
        if (!level.getLevel().dimension().equals(Level.OVERWORLD)
            || level.getMinY() != -512 || level.getHeight() != 1024) return 0;
        final int minY = Math.max(SCAN_MIN_Y, owner.getMinY() + 1);
        final int maxY = Math.min(SCAN_MAX_Y, owner.getMaxY() - 1);
        if (minY > maxY) return 0;

        final boolean[] externalSeeds = new boolean[(maxY - minY + 1) * 256];
        final ChunkPos cp = owner.getPos();
        final int west = seedFromNeighbor(cache, owner, cp.x() - 1, cp.z(), 0, 15, true, minY, maxY, externalSeeds);
        final int east = seedFromNeighbor(cache, owner, cp.x() + 1, cp.z(), 15, 0, true, minY, maxY, externalSeeds);
        final int north = seedFromNeighbor(cache, owner, cp.x(), cp.z() - 1, 0, 15, false, minY, maxY, externalSeeds);
        final int south = seedFromNeighbor(cache, owner, cp.x(), cp.z() + 1, 15, 0, false, minY, maxY, externalSeeds);
        final int seeded = west + east + north + south;

        // Always run the seam-capable owner pass. A component can be
        // ocean-connected through the owner's own Y=128 seed even when no
        // immediate neighbour contributes an external seed. Returning early
        // here produced one-sided WATER/AIR chunk walls.
        final int changed = floodVerifiedComponents(owner, externalSeeds, true);
        if (Boolean.getBoolean("neverfolia.debugFloodSeams")) {
            System.out.println(
                "[NeverFolia][R22Seam] chunk=" + cp.x() + "," + cp.z()
                + " seeds=" + west + "," + east + "," + north + "," + south
                + " total=" + seeded + " changed=" + changed
            );
        }
        return changed;
    }
"""

NEW_RECONCILE = """    public static int reconcileSeams(final WorldGenLevel level, final StaticCache2D<GenerationChunkHolder> cache, final ChunkAccess owner) {
        if (level == null || cache == null || owner == null) return 0;
        if (!level.getLevel().dimension().equals(Level.OVERWORLD)
            || level.getMinY() != -512 || level.getHeight() != 1024) return 0;
        final int minY = Math.max(SCAN_MIN_Y, owner.getMinY() + 1);
        final int maxY = Math.min(SCAN_MAX_Y, owner.getMaxY() - 1);
        if (minY > maxY) return 0;

        // R23: solve the hydraulic connectivity over the complete scheduler cache
        // FEATURES cache in one deterministic pass. This is scheduling
        // independent and does not infer flooding from mere ocean proximity.
        final int changed = floodCacheConnectedOwner(level.getLevel(), cache, owner, minY, maxY);
        if (Boolean.getBoolean("neverfolia.debugFloodSeams")) {
            final ChunkPos cp = owner.getPos();
            System.out.println(
                "[NeverFolia][R22Seam] chunk=" + cp.x() + "," + cp.z()
                + " seeds=0,0,0,0 total=0 changed=" + changed
                + " cacheExact=true"
            );
        }
        return changed;
    }
"""

CACHE_METHODS = """    private static final int CACHE_CHUNK_RADIUS = 1;
    private static final int CACHE_CHUNK_WIDTH = CACHE_CHUNK_RADIUS * 2 + 1;
    private static final int CACHE_BLOCK_WIDTH = CACHE_CHUNK_WIDTH * 16;
    private static final int CACHE_OWNER_OFFSET = CACHE_CHUNK_RADIUS * 16;
    private static final int CACHE_BLOCK_AREA = CACHE_BLOCK_WIDTH * CACHE_BLOCK_WIDTH;

    /**
     * Exact cache-bounded FEATURES flood solver. Use the native immediate-neighbour cache when the
     * scheduler exposes it; missing outer holders remain null and are never
     * synchronously loaded.
     *
     * Seeds come only from Y=128 columns that are actual/prospective flooded
     * exterior according to OCEAN_FLOOR_WG. BFS then traverses real floodable
     * cells across chunk boundaries. Only connected cells in the owner chunk
     * are written. A sealed cave therefore stays dry even when geographically
     * close to the ocean.
     */
    private static int floodCacheConnectedOwner(
        final net.minecraft.server.level.ServerLevel level,
        final StaticCache2D<GenerationChunkHolder> cache,
        final ChunkAccess owner,
        final int minY,
        final int maxY
    ) {
        final ChunkAccess[] chunks = new ChunkAccess[CACHE_CHUNK_WIDTH * CACHE_CHUNK_WIDTH];
        final ChunkPos ownerPos = owner.getPos();
        for (int dz = -CACHE_CHUNK_RADIUS; dz <= CACHE_CHUNK_RADIUS; ++dz) {
            for (int dx = -CACHE_CHUNK_RADIUS; dx <= CACHE_CHUNK_RADIUS; ++dx) {
                final int slot = (dz + CACHE_CHUNK_RADIUS) * CACHE_CHUNK_WIDTH + (dx + CACHE_CHUNK_RADIUS);
                if (dx == 0 && dz == 0) {
                    chunks[slot] = owner;
                    continue;
                }
                final int chunkX = ownerPos.x() + dx;
                final int chunkZ = ownerPos.z() + dz;
                if (!cache.contains(chunkX, chunkZ)) continue;
                final GenerationChunkHolder holder = cache.get(chunkX, chunkZ);
                if (holder != null) {
                    chunks[slot] = holder.getChunkIfPresent(ChunkStatus.FEATURES);
                }
            }
        }

        final int layers = maxY - minY + 1;
        final int capacity = layers * CACHE_BLOCK_AREA;
        final BitSet connected = new BitSet(capacity);
        final int[] queue = new int[capacity];
        int head = 0;
        int tail = 0;
        final BlockPos.MutableBlockPos pos = new BlockPos.MutableBlockPos();
        final BlockPos.MutableBlockPos adjacent = new BlockPos.MutableBlockPos();

        // Seed every real/prospective exterior-water column exposed by the cache.
        for (int tileZ = 0; tileZ < CACHE_CHUNK_WIDTH; ++tileZ) {
            for (int tileX = 0; tileX < CACHE_CHUNK_WIDTH; ++tileX) {
                final ChunkAccess chunk = chunks[tileZ * CACHE_CHUNK_WIDTH + tileX];
                if (chunk == null) continue;
                final int chunkBaseX = chunk.getPos().getMinBlockX();
                final int chunkBaseZ = chunk.getPos().getMinBlockZ();
                for (int localZ = 0; localZ < 16; ++localZ) {
                    for (int localX = 0; localX < 16; ++localX) {
                        final int surfaceY = chunk.getHeight(
                            Heightmap.Types.OCEAN_FLOOR_WG, localX, localZ
                        );
                        final int regionX = tileX * 16 + localX;
                        final int regionZ = tileZ * 16 + localZ;
                        pos.set(chunkBaseX + localX, SCAN_MAX_Y, chunkBaseZ + localZ);
                        final BlockState state = chunk.getBlockState(pos);
                        if (!surfaceOceanSeed(surfaceY, state)
                            || !traversableCache(chunks, regionX, SCAN_MAX_Y, regionZ, pos, adjacent)) continue;
                        final int e = encodeCache(regionX, SCAN_MAX_Y, regionZ, minY);
                        if (!connected.get(e)) {
                            connected.set(e);
                            queue[tail++] = e;
                        }
                    }
                }
            }
        }

        final BitSet featureSeeds = takeFeatureBoundarySeeds(level, owner);
        int featureSeedCount = 0;
        if (featureSeeds != null) {
            for (int y = minY; y <= maxY; ++y) {
                for (int localZ = 0; localZ < 16; ++localZ) {
                    for (int localX = 0; localX < 16; ++localX) {
                        if (!featureSeeds.get(encode(localX, y, localZ, minY))) continue;
                        final int regionX = localX + CACHE_OWNER_OFFSET;
                        final int regionZ = localZ + CACHE_OWNER_OFFSET;
                        if (!traversableCache(chunks, regionX, y, regionZ, pos, adjacent)) continue;
                        final int e = encodeCache(regionX, y, regionZ, minY);
                        if (!connected.get(e)) {
                            connected.set(e);
                            queue[tail++] = e;
                            ++featureSeedCount;
                        }
                    }
                }
            }
        }
        if (featureSeedCount > 0 && Boolean.getBoolean("neverfolia.debugFloodSeams")) {
            System.out.println(
                "[NeverFolia][R23FeatureSeeds] chunk=" + ownerPos.x() + "," + ownerPos.z()
                + " count=" + featureSeedCount
            );
        }

        while (head < tail) {
            final int e = queue[head++];
            final int layer = e / CACHE_BLOCK_AREA;
            final int plane = e - layer * CACHE_BLOCK_AREA;
            final int regionZ = plane / CACHE_BLOCK_WIDTH;
            final int regionX = plane - regionZ * CACHE_BLOCK_WIDTH;
            final int y = minY + layer;

            tail = enqueueCache(chunks, connected, queue, tail, regionX - 1, y, regionZ, minY, maxY, pos, adjacent);
            tail = enqueueCache(chunks, connected, queue, tail, regionX + 1, y, regionZ, minY, maxY, pos, adjacent);
            tail = enqueueCache(chunks, connected, queue, tail, regionX, y, regionZ - 1, minY, maxY, pos, adjacent);
            tail = enqueueCache(chunks, connected, queue, tail, regionX, y, regionZ + 1, minY, maxY, pos, adjacent);
            tail = enqueueCache(chunks, connected, queue, tail, regionX, y - 1, regionZ, minY, maxY, pos, adjacent);
            tail = enqueueCache(chunks, connected, queue, tail, regionX, y + 1, regionZ, minY, maxY, pos, adjacent);
        }

        int changed = 0;
        final BlockState water = Blocks.WATER.defaultBlockState();
        final int ownerBaseX = ownerPos.getMinBlockX();
        final int ownerBaseZ = ownerPos.getMinBlockZ();
        for (int y = minY; y <= maxY; ++y) {
            for (int localZ = 0; localZ < 16; ++localZ) {
                for (int localX = 0; localX < 16; ++localX) {
                    final int e = encodeCache(localX + CACHE_OWNER_OFFSET, y, localZ + CACHE_OWNER_OFFSET, minY);
                    if (!connected.get(e)) continue;
                    pos.set(ownerBaseX + localX, y, ownerBaseZ + localZ);
                    final BlockState state = owner.getBlockState(pos);
                    if (!state.is(Blocks.WATER)
                        && traversableCache(chunks, localX + CACHE_OWNER_OFFSET, y, localZ + CACHE_OWNER_OFFSET, pos, adjacent)) {
                        owner.setBlockState(pos, water, 0);
                        ++changed;
                    }
                }
            }
        }
        return changed;
    }

    private static int enqueueCache(
        final ChunkAccess[] chunks,
        final BitSet connected,
        final int[] queue,
        final int tailIn,
        final int regionX,
        final int y,
        final int regionZ,
        final int minY,
        final int maxY,
        final BlockPos.MutableBlockPos pos,
        final BlockPos.MutableBlockPos adjacent
    ) {
        if (regionX < 0 || regionX >= CACHE_BLOCK_WIDTH
            || regionZ < 0 || regionZ >= CACHE_BLOCK_WIDTH
            || y < minY || y > maxY) return tailIn;

        final int e = encodeCache(regionX, y, regionZ, minY);
        if (connected.get(e)) return tailIn;

        final int tileX = regionX >> 4;
        final int tileZ = regionZ >> 4;
        final ChunkAccess chunk = chunks[tileZ * CACHE_CHUNK_WIDTH + tileX];
        if (chunk == null) return tailIn;

        final int localX = regionX & 15;
        final int localZ = regionZ & 15;
        if (!traversableCache(chunks, regionX, y, regionZ, pos, adjacent)) return tailIn;

        connected.set(e);
        queue[tailIn] = e;
        return tailIn + 1;
    }

    private static boolean traversableCache(
        final ChunkAccess[] chunks,
        final int regionX,
        final int y,
        final int regionZ,
        final BlockPos.MutableBlockPos pos,
        final BlockPos.MutableBlockPos adjacent
    ) {
        if (regionX < 0 || regionX >= CACHE_BLOCK_WIDTH
            || regionZ < 0 || regionZ >= CACHE_BLOCK_WIDTH) return false;
        final int tileX = regionX >> 4;
        final int tileZ = regionZ >> 4;
        final ChunkAccess chunk = chunks[tileZ * CACHE_CHUNK_WIDTH + tileX];
        if (chunk == null) return false;
        final int localX = regionX & 15;
        final int localZ = regionZ & 15;
        pos.set(
            chunk.getPos().getMinBlockX() + localX,
            y,
            chunk.getPos().getMinBlockZ() + localZ
        );
        if (!traversable(chunk, pos)) return false;

        // traversable() already checks lava inside one chunk. These four tests
        // close the missing cross-chunk part of the lava barrier.
        if (localX == 0 && lavaAtCache(chunks, regionX - 1, y, regionZ, adjacent)) return false;
        if (localX == 15 && lavaAtCache(chunks, regionX + 1, y, regionZ, adjacent)) return false;
        if (localZ == 0 && lavaAtCache(chunks, regionX, y, regionZ - 1, adjacent)) return false;
        if (localZ == 15 && lavaAtCache(chunks, regionX, y, regionZ + 1, adjacent)) return false;
        return true;
    }

    private static boolean lavaAtCache(
        final ChunkAccess[] chunks,
        final int regionX,
        final int y,
        final int regionZ,
        final BlockPos.MutableBlockPos pos
    ) {
        if (regionX < 0 || regionX >= CACHE_BLOCK_WIDTH
            || regionZ < 0 || regionZ >= CACHE_BLOCK_WIDTH) return false;
        final int tileX = regionX >> 4;
        final int tileZ = regionZ >> 4;
        final ChunkAccess chunk = chunks[tileZ * CACHE_CHUNK_WIDTH + tileX];
        if (chunk == null || y < chunk.getMinY() || y >= chunk.getMaxY()) return false;
        pos.set(
            chunk.getPos().getMinBlockX() + (regionX & 15),
            y,
            chunk.getPos().getMinBlockZ() + (regionZ & 15)
        );
        return chunk.getBlockState(pos).is(Blocks.LAVA);
    }

    private static int encodeCache(
        final int regionX,
        final int y,
        final int regionZ,
        final int minY
    ) {
        return (y - minY) * CACHE_BLOCK_AREA + regionZ * CACHE_BLOCK_WIDTH + regionX;
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
    if IMPORT_BITSET not in text:
        package_end = text.find("\n", text.find("package "))
        require(package_end >= 0, "Java package declaration missing")
        text = text[:package_end + 1] + IMPORT_BITSET + text[package_end + 1:]

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

    if OLD_RECONCILE in text:
        text = text.replace(OLD_RECONCILE, NEW_RECONCILE, 1)
    elif (
        "floodCacheConnectedOwner(level.getLevel(), cache, owner, minY, maxY)" not in text
        and "floodCacheConnectedOwner(level.getLevel(), cache, owner, minY, maxY)" not in text
        and "reconcileSeams(" in text
    ):
        require(False, "R21 reconcileSeams body drifted before R23 exact-cache patch")

    if "public static void publishFeatureBoundarySeeds(" not in text and "reconcileSeams(" in text:
        require(CACHE_METHODS_ANCHOR in text, "R23 feature handoff insertion anchor missing")
        text = text.replace(CACHE_METHODS_ANCHOR, FEATURE_HANDOFF_METHODS + CACHE_METHODS_ANCHOR, 1)

    if "private static int floodCacheConnectedOwner(" not in text and "reconcileSeams(" in text:
        require(CACHE_METHODS_ANCHOR in text, "R23 cache helper insertion anchor missing")
        text = text.replace(CACHE_METHODS_ANCHOR, CACHE_METHODS + CACHE_METHODS_ANCHOR, 1)

    # Exact cache-wide connectivity replaces the old proximity fallback.
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
        "floodCacheConnectedOwner",
        "R23FeatureSeeds",
        "takeFeatureBoundarySeeds",
        "chunkKey(final int chunkX, final int chunkZ)",
        "FEATURE_BOUNDARY_SEEDS",
        "publishFeatureBoundarySeeds",
        "new BitSet(capacity)",
        "CACHE_CHUNK_RADIUS = 1",
        "CACHE_BLOCK_WIDTH = CACHE_CHUNK_WIDTH * 16",
        "CACHE_OWNER_OFFSET = CACHE_CHUNK_RADIUS * 16",
        "enqueueCache",
        "traversableCache",
        "lavaAtCache",
        "cacheExact=true",
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
        "final int changed = floodCacheConnectedOwner(level.getLevel(), cache, owner, minY, maxY);" in text,
        "R23 exact native-radius cache connectivity pass missing"
    )
    require("getChunk(" not in text and "level.getBlockState(" not in text,
            "R22 must not synchronously load/read neighbours through level")
    require("ChunkPos.asLong(" not in text and ".toLong()" not in text,
            "R23 handoff must not depend on removed ChunkPos long-key APIs")
    print("[FIELD-R23] exact cache-bounded ocean-connectivity seam invariants OK")

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

    # Regression: replacing reconcileSeams adds the call first, but the helper
    # declaration must still be materialized afterwards.
    reconcile_fixture = fixture.rsplit("\n}", 1)[0] + "\n" + OLD_RECONCILE + CACHE_METHODS_ANCHOR + "        return 0;\n    }\n}\n"
    reconcile_out = patch(reconcile_fixture)
    require(
        "private static int floodCacheConnectedOwner(" in reconcile_out,
        "SELF-TEST exact-cache helper declaration was not materialized",
    )
    require(
        "CACHE_BLOCK_WIDTH = CACHE_CHUNK_WIDTH * 16" in reconcile_out,
        "SELF-TEST exact-cache helper body missing",
    )
    require(
        "publishFeatureBoundarySeeds" in reconcile_out
        and "takeFeatureBoundarySeeds" in reconcile_out,
        "SELF-TEST feature-boundary handoff helper missing",
    )
    require(
        "private static long chunkKey(final int chunkX, final int chunkZ)" in reconcile_out,
        "SELF-TEST stable chunk key helper missing",
    )
    require(
        "final int changed = floodCacheConnectedOwner(level.getLevel(), cache, owner, minY, maxY);" in reconcile_out,
        "SELF-TEST reconcileSeams did not switch to exact-cache flood",
    )
    require(
        "floodCacheConnectedOwner(level.getLevel(), cache, owner, minY, maxY)" in reconcile_out,
        "SELF-TEST handoff reconcile state detection missing",
    )
    require(
        patch(reconcile_out) == reconcile_out,
        "SELF-TEST exact-cache transformer is not idempotent",
    )

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
    print("[FIELD-R23] SELF-TEST OK")

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
    print("[FIELD-R23] installed: FEATURES border handoff + native LIGHT exact connectivity; proximity flood disabled")

if __name__ == "__main__":
    main()
