#!/usr/bin/env python3
"""R39.28: native Y=128 sea + water-connected additive normalization.

Historical R33/R35/R37 were built around a synthetic LIGHT ocean layered on
vanilla sea level 63. R39.28 moves the authoritative sea to NOISE/AQUIFER Y=128.
This late transformer therefore replaces R37's per-column OCEAN_FLOOR_WG fill
with a connectivity pass seeded only by already-generated WATER near the raised
surface. Existing water is traversed, AIR/replaceable cells are filled, solids
remain barriers, and Y>128 is never inspected.

The transform runs after FIELD-R22/R32/R33/R34/R35/R37/R38 have materialized.
"""
from __future__ import annotations
import argparse
import runpy
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
REL=Path("folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldFlood.java")
MARK="R3928_NATIVE_WATER_CONNECTED"
HELPER_MARK="enqueueNativeWaterConnectedR3928"

NEW_METHOD=r'''    private static void floodSurfaceConnectedVolume(
        final ChunkAccess chunk,
        final int minY,
        final int maxY,
        final BlockState water
    ) {
        // R3928_NATIVE_WATER_CONNECTED:
        // native NOISE/AQUIFER water at sea level 128 is authoritative.
        // Seed only from actual WATER in the upper hydraulic band, then follow
        // that real water mass through WATER + floodable cells. Unlike R37,
        // no OCEAN_FLOOR_WG column height can be raised by an overhang and
        // suppress the ocean below it.
        final int layerCount = maxY - minY + 1;
        if (layerCount <= 0) return;
        final int[] queue = new int[layerCount * 256];
        final boolean[] visited = new boolean[layerCount * 256];
        int head = 0;
        int tail = 0;
        final int baseX = chunk.getPos().getMinBlockX();
        final int baseZ = chunk.getPos().getMinBlockZ();
        final int seedMinY = Math.max(minY, maxY - 31);
        final BlockPos.MutableBlockPos pos = new BlockPos.MutableBlockPos();

        // Frozen ocean surface may occupy Y=128; the WATER immediately below it
        // is still a valid ocean seed. A 32-block band also survives icebergs
        // without making arbitrary deep aquifer pockets authoritative.
        for (int y = seedMinY; y <= maxY; ++y) {
            for (int z = 0; z < 16; ++z) {
                for (int x = 0; x < 16; ++x) {
                    pos.set(baseX + x, y, baseZ + z);
                    if (!chunk.getBlockState(pos).getFluidState().is(net.minecraft.tags.FluidTags.WATER)) continue;
                    final int encoded = ((y - minY) << 8) | (z << 4) | x;
                    if (!visited[encoded]) {
                        visited[encoded] = true;
                        queue[tail++] = encoded;
                    }
                }
            }
        }

        while (head < tail) {
            final int encoded = queue[head++];
            final int x = encoded & 15;
            final int z = (encoded >>> 4) & 15;
            final int y = minY + (encoded >>> 8);
            pos.set(baseX + x, y, baseZ + z);
            final BlockState state = chunk.getBlockState(pos);
            final boolean nativeWater = state.getFluidState().is(net.minecraft.tags.FluidTags.WATER);
            if (!nativeWater) {
                if (!isFloodableAt(chunk, pos) || NeverOverworldDryMinesR12.protectedCell(chunk, pos)) continue;
                chunk.setBlockState(pos, water, 0);
            }

            tail = enqueueNativeWaterConnectedR3928(chunk, queue, visited, tail, x - 1, y, z, baseX, baseZ, minY, maxY);
            tail = enqueueNativeWaterConnectedR3928(chunk, queue, visited, tail, x + 1, y, z, baseX, baseZ, minY, maxY);
            tail = enqueueNativeWaterConnectedR3928(chunk, queue, visited, tail, x, y, z - 1, baseX, baseZ, minY, maxY);
            tail = enqueueNativeWaterConnectedR3928(chunk, queue, visited, tail, x, y, z + 1, baseX, baseZ, minY, maxY);
            tail = enqueueNativeWaterConnectedR3928(chunk, queue, visited, tail, x, y - 1, z, baseX, baseZ, minY, maxY);
            tail = enqueueNativeWaterConnectedR3928(chunk, queue, visited, tail, x, y + 1, z, baseX, baseZ, minY, maxY);
        }
    }'''

HELPER=r'''    private static int enqueueNativeWaterConnectedR3928(
        final ChunkAccess chunk,
        final int[] queue,
        final boolean[] visited,
        int tail,
        final int localX,
        final int y,
        final int localZ,
        final int baseX,
        final int baseZ,
        final int minY,
        final int maxY
    ) {
        if (localX < 0 || localX > 15 || localZ < 0 || localZ > 15 || y < minY || y > maxY) return tail;
        final int encoded = ((y - minY) << 8) | (localZ << 4) | localX;
        if (visited[encoded]) return tail;
        final BlockPos.MutableBlockPos pos = new BlockPos.MutableBlockPos(baseX + localX, y, baseZ + localZ);
        final BlockState state = chunk.getBlockState(pos);
        final boolean nativeWater = state.getFluidState().is(net.minecraft.tags.FluidTags.WATER);
        if (!nativeWater && (!isFloodableAt(chunk, pos) || NeverOverworldDryMinesR12.protectedCell(chunk, pos))) {
            visited[encoded] = true;
            return tail;
        }
        visited[encoded] = true;
        queue[tail++] = encoded;
        return tail;
    }

'''

def fail(msg:str)->None:
    raise ValueError("[R39.28] "+msg)

def method_bounds(text:str,signature:str)->tuple[int,int]:
    if text.count(signature)!=1: fail("missing/ambiguous method "+signature)
    start=text.index(signature);opening=text.index("{",start);depth=1;i=opening+1
    while i<len(text):
        ch=text[i]
        if ch=="{": depth+=1
        elif ch=="}":
            depth-=1
            if depth==0:return start,i+1
        i+=1
    fail("unterminated method "+signature)

def patch(text:str)->str:
    if MARK in text and HELPER_MARK in text:
        return text
    if MARK in text or HELPER_MARK in text:
        fail("partial R39.28 installation")
    r37=runpy.run_path(str(ROOT/"scripts/apply-never-overworld-r37.py"))
    old=r37["COLUMN_METHOD"]
    if text.count(old)!=1:
        fail("exact R37 column-ocean method not found")
    text=text.replace(old,NEW_METHOD,1)
    anchor="    public static void traceNativeWaterR37("
    if text.count(anchor)!=1:
        fail("R37 trace insertion anchor missing/duplicated")
    text=text.replace(anchor,HELPER+anchor,1)
    return text

def verify(text:str)->None:
    a,b=method_bounds(text,"    private static void floodSurfaceConnectedVolume(")
    method=text[a:b]
    for marker in (
        MARK,
        "seedMinY = Math.max(minY, maxY - 31)",
        "FluidTags.WATER",
        "enqueueNativeWaterConnectedR3928",
        "NeverOverworldDryMinesR12.protectedCell",
    ):
        if marker not in method and marker not in text:
            fail("missing marker "+marker)
    if "OCEAN_FLOOR_WG" in method:
        fail("primary R39.28 flood still depends on overhang-sensitive heightmap")
    if "chunk.setBlockState(pos, water, 0)" not in method:
        fail("no additive water write")
    if "state.getFluidState().is(net.minecraft.tags.FluidTags.WATER)" not in text:
        fail("native water traversal missing")

def self_test()->None:
    r37=runpy.run_path(str(ROOT/"scripts/apply-never-overworld-r37.py"))
    fixture="class NeverOverworldFlood {\n"+r37["COLUMN_METHOD"]+"\n    public static void traceNativeWaterR37(String phase, Object chunk) {}\n}\n"
    out=patch(fixture);verify(out)
    if patch(out)!=out: fail("transform not idempotent")
    print("[R39.28] native-water connected normalizer SELF-TEST OK")

def main()->None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("folia",nargs="?",type=Path)
    p.add_argument("--self-test",action="store_true")
    p.add_argument("--check-only",action="store_true")
    a=p.parse_args()
    if a.self_test:
        self_test();return
    if a.folia is None:p.error("folia worktree required")
    path=a.folia.resolve()/REL
    if not path.is_file():fail("NeverOverworldFlood source missing")
    text=path.read_text(encoding="utf-8")
    if a.check_only:
        verify(text);print("[R39.28] native-water connected normalizer invariants OK");return
    self_test();out=patch(text);verify(out);path.write_text(out,encoding="utf-8")
    print("[R39.28] installed: native sea128 water is authoritative; overhang heightmap gate removed from primary flood")

if __name__=="__main__":main()
