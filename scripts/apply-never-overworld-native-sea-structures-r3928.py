#!/usr/bin/env python3
"""R39.28: make dry-land structure admission fluid-ignoring under native sea Y=128.

With sea_level=128 authoritative during NOISE, WORLD_SURFACE_WG sees the water
surface and can no longer prove dry land. Dry-land admission must use
OCEAN_FLOOR_WG / solid terrain instead. Ocean/underground structures are left
untouched.
"""
from __future__ import annotations
import argparse
from pathlib import Path

JAVA=Path("folia-server/src/minecraft/java/net/minecraft/world/level/chunk")
VANILLA=JAVA/"NeverOverworldVanillaStructurePolicy.java"
EXTERNAL=JAVA/"NeverOverworldExternalStructurePolicyR19.java"
MARK="R3928_NATIVE_SEA_DRY_GROUND"

def fail(msg:str)->None:
    raise ValueError("[R39.28 structures] "+msg)

def bounds(text:str,signature:str)->tuple[int,int]:
    if text.count(signature)!=1: fail("missing/ambiguous method: "+signature)
    start=text.index(signature);op=text.index("{",start);depth=1
    for i in range(op+1,len(text)):
        if text[i]=="{": depth+=1
        elif text[i]=="}":
            depth-=1
            if depth==0:return start,i+1
    fail("unterminated method: "+signature)

def patch_vanilla(text:str)->str:
    if MARK in text:
        return text
    old="Heightmap.Types.WORLD_SURFACE_WG"
    if text.count(old)!=1: fail("vanilla dry policy WORLD_SURFACE_WG count drift")
    text=text.replace(old,"Heightmap.Types.OCEAN_FLOOR_WG",1)
    anchor="final int base = generator.getBaseHeight("
    if text.count(anchor)!=1: fail("vanilla base-height anchor drift")
    pos=text.index(anchor)
    line_start=text.rfind("\n",0,pos)+1
    text=text[:line_start]+"        // "+MARK+": native sea water is not dry ground.\n"+text[line_start:]
    return text

def patch_external(text:str)->str:
    if MARK in text:
        return text
    # Only dry-land classification is changed. Synthetic island materialization
    # already uses OCEAN_FLOOR_WG and must remain untouched.
    a,b=bounds(text,"    private static boolean dryAt(")
    method=text[a:b]
    if method.count("Heightmap.Types.WORLD_SURFACE_WG")!=1:
        fail("external dryAt heightmap drift")
    method=method.replace("Heightmap.Types.WORLD_SURFACE_WG","Heightmap.Types.OCEAN_FLOOR_WG",1)
    text=text[:a]+method+text[b:]

    a,b=bounds(text,"    static boolean allowsGenerated(")
    method=text[a:b]
    if method.count("Heightmap.Types.WORLD_SURFACE_WG")!=1:
        fail("external allowsGenerated center heightmap drift")
    method=method.replace("Heightmap.Types.WORLD_SURFACE_WG","Heightmap.Types.OCEAN_FLOOR_WG",1)
    marker="        final int centerX = chunkPos.getMiddleBlockX();\n"
    if method.count(marker)!=1: fail("external generated marker drift")
    method=method.replace(marker,"        // "+MARK+": classify the real solid floor, not native sea water.\n"+marker,1)
    text=text[:a]+method+text[b:]
    return text

def verify(vanilla:str,external:str)->None:
    if MARK not in vanilla or MARK not in external: fail("marker missing")
    if "Heightmap.Types.WORLD_SURFACE_WG" in vanilla: fail("vanilla dry admission still water-sensitive")
    a,b=bounds(external,"    private static boolean dryAt(")
    if "WORLD_SURFACE_WG" in external[a:b] or "OCEAN_FLOOR_WG" not in external[a:b]:
        fail("external dryAt not solid-floor based")
    a,b=bounds(external,"    static boolean allowsGenerated(")
    if "WORLD_SURFACE_WG" in external[a:b] or "OCEAN_FLOOR_WG" not in external[a:b]:
        fail("external generated admission not solid-floor based")
    # Do not remove the synthetic-island owner's existing floor scan; it is
    # already correct and remains a separate policy choice.
    if "chunk.getHeight(Heightmap.Types.OCEAN_FLOOR_WG, lx, lz)" not in external:
        fail("synthetic-island floor scan lost")

def self_test()->None:
    vanilla="""class V {
    static boolean allows() {
        final int base = generator.getBaseHeight(
            x, z, Heightmap.Types.WORLD_SURFACE_WG, heightAccessor, randomState
        );
        return base >= 129;
    }
}
"""
    external="""class E {
    private static boolean dryAt(Object generator) {
        return generator.getBaseHeight(x,z,Heightmap.Types.WORLD_SURFACE_WG,h,r)>=129;
    }
    static boolean allowsGenerated(Object generator) {
        final int centerX = chunkPos.getMiddleBlockX();
        final int centerZ = chunkPos.getMiddleBlockZ();
        final int base = generator.getBaseHeight(
            centerX, centerZ, Heightmap.Types.WORLD_SURFACE_WG, heightAccessor, randomState
        );
        return true;
    }
    void island(){ int floorY = chunk.getHeight(Heightmap.Types.OCEAN_FLOOR_WG, lx, lz); }
}
"""
    pv=patch_vanilla(vanilla);pe=patch_external(external);verify(pv,pe)
    if patch_vanilla(pv)!=pv or patch_external(pe)!=pe: fail("not idempotent")
    print("[R39.28 structures] NATIVE-SEA DRY-GROUND SELF-TEST OK")

def main()->None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("folia",nargs="?",type=Path)
    p.add_argument("--self-test",action="store_true")
    p.add_argument("--check-only",action="store_true")
    a=p.parse_args()
    if a.self_test:self_test();return
    if a.folia is None:p.error("folia worktree required")
    vp=a.folia.resolve()/VANILLA;ep=a.folia.resolve()/EXTERNAL
    if not vp.is_file() or not ep.is_file():fail("materialized structure policy sources missing")
    v=vp.read_text(encoding="utf-8");e=ep.read_text(encoding="utf-8")
    if a.check_only:
        verify(v,e);print("[R39.28 structures] native-sea dry-ground invariants OK");return
    self_test();v=patch_vanilla(v);e=patch_external(e);verify(v,e)
    vp.write_text(v,encoding="utf-8");ep.write_text(e,encoding="utf-8")
    print("[R39.28 structures] dry-land admission now uses solid ocean floor under native sea Y=128")

if __name__=="__main__":main()
