#!/usr/bin/env python3
"""FIELD-R35: permit NeverFolia synthetic WATER at/above natural OCEAN_FLOOR_WG.

R33 preserved vanilla aquifers and stopped custom flood below Y=96, but a
surface-ocean seed could still traverse a cave component and write a rectangular
chunk-local water volume. R35 makes the final write contract column-local:
NeverFolia may create WATER only when the target block is at/above that column's
natural OCEAN_FLOOR_WG and at/below the raised ocean plane Y=128.

Vanilla/native aquifer WATER is never removed or rewritten by this gate.
"""
from __future__ import annotations
import argparse
from pathlib import Path

JAVA=Path("folia-server/src/minecraft/java")
OWNER=JAVA/"net/minecraft/world/level/chunk/NeverOverworldFlood.java"
R15=JAVA/"net/minecraft/world/level/chunk/NeverOverworldFloodConnectivityR15.java"

OWNER_HELPER="""    private static boolean customOceanColumnOpen(
        final ChunkAccess chunk,
        final BlockPos pos,
        final int y
    ) {
        final int localX = pos.getX() & 15;
        final int localZ = pos.getZ() & 15;
        final int oceanFloorY = chunk.getHeight(
            net.minecraft.world.level.levelgen.Heightmap.Types.OCEAN_FLOOR_WG,
            localX,
            localZ
        );
        return y == FLOOD_LEVEL || (oceanFloorY < FLOOD_LEVEL && y >= oceanFloorY && y < FLOOD_LEVEL);
    }

"""

R15_HELPER="""    static boolean customOceanColumnOpen(
        final ChunkAccess chunk,
        final BlockPos pos,
        final int y
    ) {
        final int localX = pos.getX() & 15;
        final int localZ = pos.getZ() & 15;
        final int oceanFloorY = chunk.getHeight(
            net.minecraft.world.level.levelgen.Heightmap.Types.OCEAN_FLOOR_WG,
            localX,
            localZ
        );
        return y == SCAN_MAX_Y || (oceanFloorY < SCAN_MAX_Y && y >= oceanFloorY && y < SCAN_MAX_Y);
    }

"""

def fail(msg:str)->None:
    raise ValueError("[FIELD-R35] "+msg)

def inject_before_encode(text:str, helper:str)->str:
    if "customOceanColumnOpen(" in text:
        return text
    anchors=(
        "    private static int encode(",
        "    static int encode(",
    )
    for anchor in anchors:
        pos=text.find(anchor)
        if pos>=0:
            return text[:pos]+helper+text[pos:]
    # Owner flood implementations do not all carry an encode helper. In that
    # case insert before the class closing brace instead of coupling R35 to an
    # unrelated implementation detail.
    pos=text.rfind("}")
    if pos<0:
        fail("class closing brace missing")
    return text[:pos]+helper+text[pos:]

def patch_owner(text:str)->str:
    text=inject_before_encode(text,OWNER_HELPER)

    write="            chunk.setBlockState(pos, water, 0);\n"
    guarded=(
        "            if (!customOceanColumnOpen(chunk, pos, y)) {\n"
        "                continue;\n"
        "            }\n"
        + write
    )

    # R33 may already have one or more Y>=96 guards. Add the stricter
    # ocean-floor barrier immediately before every remaining synthetic write.
    cursor=0
    out=[]
    count=0
    while True:
        idx=text.find(write,cursor)
        if idx<0:
            out.append(text[cursor:])
            break
        out.append(text[cursor:idx])
        prefix=text[max(0,idx-180):idx]
        if "customOceanColumnOpen(chunk, pos, y)" in prefix:
            out.append(write)
        else:
            out.append(guarded)
            count+=1
        cursor=idx+len(write)
    text="".join(out)
    if count==0 and "customOceanColumnOpen(chunk, pos, y)" not in text:
        fail("owner synthetic WATER write anchor missing")
    return text

def patch_r15(text:str)->str:
    text=inject_before_encode(text,R15_HELPER)

    # Canonical component discovery must not walk through enclosed cave cells.
    old_seed="if(!traversable(chunk,pos)){visited[seed]=true;continue;}"
    new_seed="if(!traversable(chunk,pos)||(!chunk.getBlockState(pos).is(Blocks.WATER)&&!customOceanColumnOpen(chunk,pos,y))){visited[seed]=true;continue;}"
    if old_seed in text:
        text=text.replace(old_seed,new_seed)

    # Both BFS enqueue helpers are custom-ocean traversal. Keep them out of
    # cells below the natural ocean floor even if they are replaceable AIR.
    old_enqueue="if(!traversable(chunk,pos))return tail;"
    new_enqueue="if(!traversable(chunk,pos)||(!chunk.getBlockState(pos).is(Blocks.WATER)&&!customOceanColumnOpen(chunk,pos,y)))return tail;"
    text=text.replace(old_enqueue,new_enqueue)

    old_enqueue2="if (!traversable(chunk, pos)) return tailIn;"
    new_enqueue2="if (!traversable(chunk, pos) || (!chunk.getBlockState(pos).is(Blocks.WATER) && !customOceanColumnOpen(chunk, pos, y))) return tailIn;"
    text=text.replace(old_enqueue2,new_enqueue2)

    # Canonical component fill.
    old="if(!state.is(Blocks.WATER)&&traversable(chunk,pos)){chunk.setBlockState(pos,water,0);++changed;}"
    new="if(!state.is(Blocks.WATER)&&traversable(chunk,pos)&&customOceanColumnOpen(chunk,pos,y)){chunk.setBlockState(pos,water,0);++changed;}"
    if old in text:
        text=text.replace(old,new)

    # R22/R31 fillVerifiedMask common pre-write barrier. This protects both
    # ProtoChunk#setBlockState and raw FULL section writes.
    old2="if (chunk.getBlockState(pos).is(Blocks.WATER) || !traversable(chunk, pos)) continue;"
    new2="if (chunk.getBlockState(pos).is(Blocks.WATER) || !traversable(chunk, pos) || !customOceanColumnOpen(chunk, pos, y)) continue;"
    text=text.replace(old2,new2)

    # Historical neighbour edge write.
    old3="""                if (!owner.getBlockState(ownerPos).is(Blocks.WATER)) {
                    owner.setBlockState(ownerPos, Blocks.WATER.defaultBlockState(), 0);
                }
"""
    new3="""                if (!owner.getBlockState(ownerPos).is(Blocks.WATER)
                    && customOceanColumnOpen(owner, ownerPos, y)) {
                    owner.setBlockState(ownerPos, Blocks.WATER.defaultBlockState(), 0);
                }
"""
    if old3 in text:
        text=text.replace(old3,new3)

    # R24 FEATURES handoff owner write injected by FIELD-R22.
    old4="""            if (!owner.getBlockState(pos).is(Blocks.WATER)) {
                owner.setBlockState(pos, water, 0);
                ++changed;
            }
"""
    new4="""            if (!owner.getBlockState(pos).is(Blocks.WATER)
                && customOceanColumnOpen(owner, pos, y)) {
                owner.setBlockState(pos, water, 0);
                ++changed;
            }
"""
    if old4 in text:
        text=text.replace(old4,new4)

    return text

def verify(owner:str,r15:str)->None:
    if "customOceanColumnOpen(" not in owner:
        fail("owner ocean-column barrier missing")
    if "OCEAN_FLOOR_WG" not in owner:
        fail("owner OCEAN_FLOOR_WG lookup missing")
    if "customOceanColumnOpen(" not in r15 or "OCEAN_FLOOR_WG" not in r15:
        fail("R15 ocean-column barrier missing")

    # No plain canonical writes may survive in the verified component path.
    forbidden="if(!state.is(Blocks.WATER)&&traversable(chunk,pos)){chunk.setBlockState(pos,water,0);++changed;}"
    if forbidden in r15:
        fail("R15 canonical write survived without column barrier")

    if "|| !customOceanColumnOpen(chunk, pos, y)) continue;" not in r15:
        fail("R22 fillVerifiedMask lacks column barrier")
    if "is(Blocks.WATER)&&!customOceanColumnOpen(chunk,pos,y)" not in r15:
        fail("R15 component discovery does not preserve authoritative WATER seeds")
    if "is(Blocks.WATER)&&!customOceanColumnOpen(chunk,pos,y)" not in r15 and "is(Blocks.WATER) && !customOceanColumnOpen(chunk, pos, y)" not in r15:
        fail("R15 BFS traversal lacks water-aware ocean-floor barrier")

def self_test()->None:
    owner="""class NeverOverworldFlood {
    private static final int FLOOD_LEVEL = 128;
    void x(ChunkAccess chunk,BlockPos.MutableBlockPos pos,BlockState water,int y){
            chunk.setBlockState(pos, water, 0);
    }
    private static int encode(int x,int y,int z,int minY){return 0;}
}
"""
    r15="""class NeverOverworldFloodConnectivityR15 {
    static final int SCAN_MAX_Y = 128;
    void a(ChunkAccess chunk,BlockPos.MutableBlockPos pos,BlockState water,int y){
        BlockState state=chunk.getBlockState(pos);
        if(!traversable(chunk,pos)){visited[seed]=true;continue;}
        if(!state.is(Blocks.WATER)&&traversable(chunk,pos)){chunk.setBlockState(pos,water,0);++changed;}
        if (chunk.getBlockState(pos).is(Blocks.WATER) || !traversable(chunk, pos)) continue;
    }
    int enqueue(ChunkAccess chunk,BlockPos.MutableBlockPos pos,int y,int tail){
        if(!traversable(chunk,pos))return tail;
        return tail+1;
    }
    int enqueueFloodable(ChunkAccess chunk,BlockPos.MutableBlockPos pos,int y,int tailIn){
        if (!traversable(chunk, pos)) return tailIn;
        return tailIn+1;
    }
    private static int encode(int x,int y,int z,int minY){return 0;}
}
"""
    po=patch_owner(owner)
    pr=patch_r15(r15)
    verify(po,pr)
    if patch_owner(po)!=po or patch_r15(pr)!=pr:
        fail("transform is not idempotent")
    print("[FIELD-R35] SELF-TEST OK")

def main()->None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("folia",nargs="?",type=Path)
    p.add_argument("--self-test",action="store_true")
    p.add_argument("--check-only",action="store_true")
    a=p.parse_args()
    if a.self_test:
        self_test();return
    if a.folia is None:
        p.error("folia worktree is required")
    owner_path=a.folia.resolve()/OWNER
    r15_path=a.folia.resolve()/R15
    if not owner_path.is_file() or not r15_path.is_file():
        fail("materialized flood sources missing")
    owner=owner_path.read_text(encoding="utf-8")
    r15=r15_path.read_text(encoding="utf-8")
    if a.check_only:
        verify(owner,r15)
        print("[FIELD-R35] column-bounded ocean write invariants OK")
        return
    self_test()
    owner=patch_owner(owner)
    r15=patch_r15(r15)
    verify(owner,r15)
    owner_path.write_text(owner,encoding="utf-8")
    r15_path.write_text(r15,encoding="utf-8")
    print("[FIELD-R35] installed: synthetic WATER only above natural OCEAN_FLOOR_WG")

if __name__=="__main__":
    main()
