#!/usr/bin/env python3
"""Install the bounded R3913 submerged-ice cleanup into a materialized Folia tree.

Runs after R399 integration so LIGHT order is:
R399 ocean closure -> R3913 bounded ice cleanup -> R38 water audit.
"""
from __future__ import annotations
import argparse
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
JAVA=Path("folia-server/src/minecraft/java")
CHUNK=JAVA/"net/minecraft/world/level/chunk"
LIGHT=JAVA/"ca/spottedleaf/moonrise/patches/chunk_system/scheduling/task/ChunkLightTask.java"
SOURCE="NeverOverworldIceFragmentsR3913.java"
R399_HOOK="                net.minecraft.world.level.chunk.NeverOverworldOceanClosureR399.apply(task.world, task.neverOverworldNeighbours, task.fromChunk); // R399_OCEAN_CLOSURE"
ICE_HOOK="                net.minecraft.world.level.chunk.NeverOverworldIceFragmentsR3913.apply(task.world, task.neverOverworldNeighbours, task.fromChunk); // R3913_ICE_FRAGMENTS"

def fail(msg:str)->None:
    raise ValueError("[R3913-INTEGRATION] "+msg)

def prepare(folia:Path)->dict[Path,str]:
    source=(ROOT/"native/overworld-r3913"/SOURCE)
    if not source.is_file(): fail("missing native ice source")
    staged={folia/CHUNK/SOURCE:source.read_text(encoding="utf-8")}
    light_path=folia/LIGHT
    if not light_path.is_file(): fail("ChunkLightTask source missing")
    text=light_path.read_text(encoding="utf-8")
    if ICE_HOOK not in text:
        if text.count(R399_HOOK)!=1: fail("R399 LIGHT hook missing/ambiguous")
        text=text.replace(R399_HOOK,R399_HOOK+"\n"+ICE_HOOK,1)
    if text.count(ICE_HOOK)!=1: fail("ice LIGHT hook missing/duplicated")
    if text.index(R399_HOOK)>text.index(ICE_HOOK): fail("ice hook must run after R399")
    staged[light_path]=text
    return staged

def verify(folia:Path,staged:dict[Path,str])->None:
    source=(ROOT/"native/overworld-r3913"/SOURCE).read_text(encoding="utf-8")
    target=folia/CHUNK/SOURCE
    actual=staged.get(target,target.read_text(encoding="utf-8") if target.is_file() else "")
    if actual!=source: fail("materialized ice source differs")
    light_path=folia/LIGHT
    text=staged.get(light_path,light_path.read_text(encoding="utf-8"))
    if text.count(R399_HOOK)!=1 or text.count(ICE_HOOK)!=1: fail("LIGHT hook invariant failed")
    if text.index(R399_HOOK)>text.index(ICE_HOOK): fail("wrong R399/R3913 order")

def main()->None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("folia",type=Path)
    p.add_argument("--check-only",action="store_true")
    a=p.parse_args();folia=a.folia.resolve()
    staged=prepare(folia);verify(folia,staged)
    if not a.check_only:
        for path,text in staged.items():
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(text,encoding="utf-8")
    print("[R3913-INTEGRATION] bounded submerged-ice cleanup integrated after R399")

if __name__=="__main__":
    main()
