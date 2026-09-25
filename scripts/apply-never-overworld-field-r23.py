#!/usr/bin/env python3
"""FIELD-R23: retire proximity-only cave flooding.

R22 fixed seam scheduling with prospective OCEAN_FLOOR_WG seeds, but also
introduced a proximity fallback that could flood large dry cave components
without an authoritative ocean-water seed. R23 keeps prospective/real ocean
connectivity and removes only that heuristic fallback.
"""
from __future__ import annotations

import argparse
from pathlib import Path

JAVA=Path("folia-server/src/minecraft/java")
FLOOD15=JAVA/"net/minecraft/world/level/chunk/NeverOverworldFloodConnectivityR15.java"

PROXIMITY_CALL="        final int proximity = seedOceanProximityFallback(cache, owner, minY, maxY, externalSeeds);\n"
STATE_OLD="        int head=0,tail=0;boolean hasOceanSeed=false,hasProximitySeed=false,touchesHorizontalSeam=false;\n"
STATE_NEW="        int head=0,tail=0;boolean hasOceanSeed=false,touchesHorizontalSeam=false;\n"
EXTERNAL_OLD=(
    "            if(externalSeeds!=null&&externalSeeds[e]){\n"
    "                if(chunk.getBlockState(pos).is(Blocks.WATER))hasOceanSeed=true;\n"
    "                else hasProximitySeed=true;\n"
    "            }\n"
)
EXTERNAL_NEW=(
    "            if(externalSeeds!=null&&externalSeeds[e])hasOceanSeed=true;\n"
)
GUARD_OLD=(
    "        if(!hasOceanSeed){\n"
    "            final int verticalSpan=componentMaxY-componentMinY+1;\n"
    "            final boolean proximityFallback=allowSeams&&touchesHorizontalSeam\n"
    "                &&proximityFallbackAllowed(tail,boundaryCells,verticalSpan,hasProximitySeed);\n"
    "            if(!proximityFallback){\n"
    "                if(allowSeams&&touchesHorizontalSeam&&tail>=64&&boundaryCells>=8\n"
    "                    &&Boolean.getBoolean(\"neverfolia.debugFloodSeams\")){\n"
    "                    System.out.println(\n"
    "                        \"[NeverFolia][R22DrySeam] chunk=\"+chunk.getPos().x()+\",\"+chunk.getPos().z()\n"
    "                        +\" size=\"+tail+\" boundary=\"+boundaryCells\n"
    "                        +\" y=\"+componentMinY+\":\"+componentMaxY\n"
    "                        +\" sample=\"+sampleSeamX+\",\"+sampleSeamY+\",\"+sampleSeamZ\n"
    "                    );\n"
    "                }\n"
    "                return 0;\n"
    "            }\n"
    "            if(Boolean.getBoolean(\"neverfolia.debugFloodSeams\")){\n"
    "                System.out.println(\n"
    "                    \"[NeverFolia][R22ProximityFlood] chunk=\"+chunk.getPos().x()+\",\"+chunk.getPos().z()\n"
    "                    +\" size=\"+tail+\" boundary=\"+boundaryCells\n"
    "                    +\" span=\"+verticalSpan+\" nearOcean=true\"\n"
    "                );\n"
    "            }\n"
    "        }\n"
)
GUARD_NEW=(
    "        if(!hasOceanSeed){\n"
    "            if(allowSeams&&touchesHorizontalSeam&&tail>=64&&boundaryCells>=8\n"
    "                &&Boolean.getBoolean(\"neverfolia.debugFloodSeams\")){\n"
    "                System.out.println(\n"
    "                    \"[NeverFolia][R23DrySeam] chunk=\"+chunk.getPos().x()+\",\"+chunk.getPos().z()\n"
    "                    +\" size=\"+tail+\" boundary=\"+boundaryCells\n"
    "                    +\" y=\"+componentMinY+\":\"+componentMaxY\n"
    "                    +\" sample=\"+sampleSeamX+\",\"+sampleSeamY+\",\"+sampleSeamZ\n"
    "                );\n"
    "            }\n"
    "            return 0;\n"
    "        }\n"
)
MASK="        final boolean[] neighborProximityWater = proximityConnectedFloodable(cache, neighbor, minY, maxY);\n"
GATE_OLD="                if (!neighborOceanWater[ne] && !neighborProximityWater[ne]) continue;\n"
GATE_NEW="                if (!neighborOceanWater[ne]) continue;\n"

R23_MARKER = "    // NeverFolia FIELD-R23: exact cached 3x3 ocean connectivity; no proximity heuristic.\n"
RECONCILE_START = (
    "    public static int reconcileSeams(final WorldGenLevel level, "
    "final StaticCache2D<GenerationChunkHolder> cache, final ChunkAccess owner) {\n"
)
SEED_NEIGHBOR_START = "    private static int seedFromNeighbor(\n"

EXACT_RECONCILE = R23_MARKER + """    public static int reconcileSeams(final WorldGenLevel level, final StaticCache2D<GenerationChunkHolder> cache, final ChunkAccess owner) {
        if (level == null || cache == null || owner == null) return 0;
        if (!level.getLevel().dimension().equals(Level.OVERWORLD)
            || level.getMinY() != -512 || level.getHeight() != 1024) return 0;
        final int minY = Math.max(SCAN_MIN_Y, owner.getMinY() + 1);
        final int maxY = Math.min(SCAN_MAX_Y, owner.getMaxY() - 1);
        if (minY > maxY) return 0;
        return floodFromCachedOceanConnectivity(cache, owner, minY, maxY);
    }

"""

EXACT_HELPERS = """    private static int floodFromCachedOceanConnectivity(
        final StaticCache2D<GenerationChunkHolder> cache,
        final ChunkAccess owner,
        final int minY,
        final int maxY
    ) {
        final int gridWidth = 48;
        final int plane = gridWidth * gridWidth;
        final int layers = maxY - minY + 1;
        final int capacity = layers * plane;
        final boolean[] connected = new boolean[capacity];
        final int[] queue = new int[capacity];
        final ChunkAccess[] chunks = new ChunkAccess[9];
        final ChunkPos ownerPos = owner.getPos();

        for (int dz = -1; dz <= 1; ++dz) {
            for (int dx = -1; dx <= 1; ++dx) {
                chunks[(dz + 1) * 3 + (dx + 1)] =
                    cachedFeaturesChunk(cache, owner, ownerPos.x() + dx, ownerPos.z() + dz);
            }
        }

        int head = 0;
        int tail = 0;
        final BlockPos.MutableBlockPos pos = new BlockPos.MutableBlockPos();

        // Seed only from actual/predictable ocean surface columns at Y128.
        // No geometric proximity or component-size heuristic participates.
        for (int chunkGridZ = 0; chunkGridZ < 3; ++chunkGridZ) {
            for (int chunkGridX = 0; chunkGridX < 3; ++chunkGridX) {
                final ChunkAccess chunk = chunks[chunkGridZ * 3 + chunkGridX];
                if (chunk == null) continue;
                final int baseX = chunk.getPos().getMinBlockX();
                final int baseZ = chunk.getPos().getMinBlockZ();
                for (int z = 0; z < 16; ++z) {
                    for (int x = 0; x < 16; ++x) {
                        final int surfaceY = chunk.getHeight(Heightmap.Types.OCEAN_FLOOR_WG, x, z);
                        pos.set(baseX + x, SCAN_MAX_Y, baseZ + z);
                        final BlockState state = chunk.getBlockState(pos);
                        if (!surfaceOceanSeed(surfaceY, state) || !traversable(chunk, pos)) continue;
                        final int gx = chunkGridX * 16 + x;
                        final int gz = chunkGridZ * 16 + z;
                        final int e = cachedEncode(gx, SCAN_MAX_Y, gz, minY, plane, gridWidth);
                        if (connected[e]) continue;
                        connected[e] = true;
                        queue[tail++] = e;
                    }
                }
            }
        }

        while (head < tail) {
            final int e = queue[head++];
            final int layer = e / plane;
            final int rem = e - layer * plane;
            final int gz = rem / gridWidth;
            final int gx = rem - gz * gridWidth;
            final int y = minY + layer;
            tail = enqueueCached(chunks, connected, queue, tail, gx - 1, y, gz, minY, maxY, plane, gridWidth);
            tail = enqueueCached(chunks, connected, queue, tail, gx + 1, y, gz, minY, maxY, plane, gridWidth);
            tail = enqueueCached(chunks, connected, queue, tail, gx, y, gz - 1, minY, maxY, plane, gridWidth);
            tail = enqueueCached(chunks, connected, queue, tail, gx, y, gz + 1, minY, maxY, plane, gridWidth);
            tail = enqueueCached(chunks, connected, queue, tail, gx, y - 1, gz, minY, maxY, plane, gridWidth);
            tail = enqueueCached(chunks, connected, queue, tail, gx, y + 1, gz, minY, maxY, plane, gridWidth);
        }

        int west = 0, east = 0, north = 0, south = 0;
        int changed = 0;
        final int ownerBaseX = owner.getPos().getMinBlockX();
        final int ownerBaseZ = owner.getPos().getMinBlockZ();
        final BlockState water = Blocks.WATER.defaultBlockState();
        for (int y = minY; y <= maxY; ++y) {
            for (int z = 0; z < 16; ++z) {
                for (int x = 0; x < 16; ++x) {
                    final int gx = 16 + x;
                    final int gz = 16 + z;
                    final int e = cachedEncode(gx, y, gz, minY, plane, gridWidth);
                    if (!connected[e]) continue;
                    if (y < SCAN_MAX_Y) {
                        if (x == 0) ++west;
                        if (x == 15) ++east;
                        if (z == 0) ++north;
                        if (z == 15) ++south;
                    }
                    pos.set(ownerBaseX + x, y, ownerBaseZ + z);
                    final BlockState state = owner.getBlockState(pos);
                    if (!state.is(Blocks.WATER) && traversable(owner, pos)) {
                        owner.setBlockState(pos, water, 0);
                        ++changed;
                    }
                }
            }
        }

        if (Boolean.getBoolean("neverfolia.debugFloodSeams")) {
            System.out.println(
                "[NeverFolia][R22Seam] chunk=" + ownerPos.x() + "," + ownerPos.z()
                + " seeds=" + west + "," + east + "," + north + "," + south
                + " total=" + (west + east + north + south) + " changed=" + changed
            );
        }
        return changed;
    }

    private static int enqueueCached(
        final ChunkAccess[] chunks,
        final boolean[] connected,
        final int[] queue,
        final int tailIn,
        final int gx,
        final int y,
        final int gz,
        final int minY,
        final int maxY,
        final int plane,
        final int gridWidth
    ) {
        if (gx < 0 || gx >= gridWidth || gz < 0 || gz >= gridWidth || y < minY || y > maxY) {
            return tailIn;
        }
        final int e = cachedEncode(gx, y, gz, minY, plane, gridWidth);
        if (connected[e]) return tailIn;
        final int chunkGridX = gx >> 4;
        final int chunkGridZ = gz >> 4;
        final ChunkAccess chunk = chunks[chunkGridZ * 3 + chunkGridX];
        if (chunk == null) return tailIn;
        final int localX = gx & 15;
        final int localZ = gz & 15;
        final BlockPos pos = new BlockPos(
            chunk.getPos().getMinBlockX() + localX,
            y,
            chunk.getPos().getMinBlockZ() + localZ
        );
        if (!traversable(chunk, pos)) return tailIn;
        connected[e] = true;
        queue[tailIn] = e;
        return tailIn + 1;
    }

    private static int cachedEncode(
        final int gx,
        final int y,
        final int gz,
        final int minY,
        final int plane,
        final int gridWidth
    ) {
        return (y - minY) * plane + gz * gridWidth + gx;
    }

"""

def require(ok:bool,message:str)->None:
    if not ok:
        raise ValueError("[FIELD-R23] "+message)

def patch(text:str)->str:
    text=text.replace(PROXIMITY_CALL,"")
    if STATE_OLD in text:text=text.replace(STATE_OLD,STATE_NEW,1)
    if EXTERNAL_OLD in text:text=text.replace(EXTERNAL_OLD,EXTERNAL_NEW,1)
    if GUARD_OLD in text:text=text.replace(GUARD_OLD,GUARD_NEW,1)
    text=text.replace(MASK,"")
    if GATE_OLD in text:text=text.replace(GATE_OLD,GATE_NEW,1)

    if R23_MARKER not in text:
        start=text.find(RECONCILE_START)
        require(start>=0,"R22/R21 reconcile method start missing")
        end=text.find(SEED_NEIGHBOR_START,start)
        require(end>start,"seedFromNeighbor anchor missing after reconcile")
        text=text[:start]+EXACT_RECONCILE+EXACT_HELPERS+text[end:]
    return text

def verify(folia:Path)->None:
    path=folia/FLOOD15
    require(path.is_file(),"R15/R22 flood helper missing")
    text=path.read_text(encoding="utf-8")
    for marker in (
        "prospectiveOceanSurfaceSeed",
        "surfaceOceanSeed",
        "oceanConnectedFloodable",
        "reconcileSeams",
        "getChunkIfPresent(ChunkStatus.FEATURES)",
        GATE_NEW.strip(),
        STATE_NEW.strip(),
        EXTERNAL_NEW.strip(),
        "if (!neighborOceanWater[ne]) continue;",
        R23_MARKER.strip(),
        "floodFromCachedOceanConnectivity(cache, owner, minY, maxY)",
        "cachedEncode(",
        "R23DrySeam",
    ):
        require(marker in text,"strict ocean-connectivity marker missing: "+marker)
    for forbidden in (
        PROXIMITY_CALL.strip(),
        "hasProximitySeed",
        MASK.strip(),
        GATE_OLD.strip(),
        "R22ProximityFlood",
        "final boolean proximityFallback=allowSeams&&touchesHorizontalSeam",
    ):
        require(forbidden not in text,"proximity-only flood path survived: "+forbidden)
    reconcile_start=text.index(R23_MARKER)
    reconcile_end=text.index(SEED_NEIGHBOR_START,reconcile_start)
    reconcile=text[reconcile_start:reconcile_end]
    require("seedOceanProximityFallback(" not in reconcile
            and "neighborProximityWater" not in reconcile
            and "proximityFallbackAllowed(" not in reconcile,
            "R23 production reconcile must not use proximity heuristics")
    require("gridWidth = 48" in reconcile and "OCEAN_FLOOR_WG" in reconcile,
            "R23 exact 3x3 cached connectivity volume missing")
    require("getChunk(" not in text and "level.getBlockState(" not in text,
            "R23 must not synchronously load/read neighbours through level")
    print("[FIELD-R23] strict ocean-connected cave flooding invariants OK")

def self_test()->None:
    fixture=(
        "class X {\n"
        +PROXIMITY_CALL+STATE_OLD+EXTERNAL_OLD+GUARD_OLD+MASK
        +RECONCILE_START
        +"        return 0;\n"
        +"    }\n\n"
        +SEED_NEIGHBOR_START
        +"        return 0;\n"
        +"    }\n"
        +"boolean prospectiveOceanSurfaceSeed; boolean surfaceOceanSeed;\n"
        +"boolean oceanConnectedFloodable;\n"
        +"void x(){ getChunkIfPresent(ChunkStatus.FEATURES); }\n"
        +"}\n"
    )
    out=patch(fixture)
    require(PROXIMITY_CALL.strip() not in out,"SELF-TEST proximity call survived")
    require("hasProximitySeed" not in out,"SELF-TEST proximity seed survived")
    require(R23_MARKER.strip() in out,"SELF-TEST exact reconcile marker missing")
    require("floodFromCachedOceanConnectivity" in out,"SELF-TEST exact cached flood helper missing")
    require("gridWidth = 48" in out,"SELF-TEST 3x3 cache width missing")
    reconcile=out[out.index(R23_MARKER):out.index(SEED_NEIGHBOR_START)]
    require("seedOceanProximityFallback(" not in reconcile,"SELF-TEST proximity reconcile survived")
    require(patch(out)==out,"SELF-TEST transformer is not idempotent")
    print("[FIELD-R23] SELF-TEST OK")

def main()->None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("folia",nargs="?",type=Path)
    p.add_argument("--self-test",action="store_true")
    p.add_argument("--check-only",action="store_true")
    a=p.parse_args()
    if a.self_test:
        self_test();return
    if a.folia is None:p.error("folia worktree is required")
    folia=a.folia.resolve()
    if a.check_only:
        verify(folia);return
    self_test()
    path=folia/FLOOD15
    require(path.is_file(),"R15/R22 flood helper missing")
    path.write_text(patch(path.read_text(encoding="utf-8")),encoding="utf-8")
    verify(folia)
    print("[FIELD-R23] installed: proximity-only cave flooding retired")

if __name__=="__main__":
    main()
