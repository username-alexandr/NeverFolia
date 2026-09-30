#!/usr/bin/env python3
"""R39.25: make native sea-level worldgen authoritative and retire synthetic LIGHT flooding."""
from __future__ import annotations
import argparse
from pathlib import Path

JAVA=Path("folia-server/src/minecraft/java")
CHUNK=JAVA/"net/minecraft/world/level/chunk"
LIGHT=JAVA/"ca/spottedleaf/moonrise/patches/chunk_system/scheduling/task/ChunkLightTask.java"
FLOOD=CHUNK/"NeverOverworldFlood.java"
R15=CHUNK/"NeverOverworldFloodConnectivityR15.java"
R399=CHUNK/"NeverOverworldOceanClosureR399.java"
R3913=CHUNK/"NeverOverworldIceFragmentsR3913.java"
HELPER=CHUNK/"NeverOverworldNativeSeaR3925.java"

MARK="// R3925_NATIVE_SEA"

CALLS=(
    "net.minecraft.world.level.chunk.NeverOverworldFlood.apply(task.world, task.fromChunk);",
    "net.minecraft.world.level.chunk.NeverOverworldFloodConnectivityR15.reconcileSeams(task.world, task.neverOverworldNeighbours, task.fromChunk);",
    "net.minecraft.world.level.chunk.NeverOverworldFlood.reweatherSubmergedSurface(task.world, task.fromChunk);",
    "net.minecraft.world.level.chunk.NeverOverworldEcologyR13.cleanup(task.world, task.fromChunk);",
    "net.minecraft.world.level.chunk.NeverOverworldEcologyR15.cleanup(task.world, task.fromChunk);",
    "net.minecraft.world.level.chunk.NeverOverworldOceanClosureR399.apply(task.world, task.neverOverworldNeighbours, task.fromChunk);",
    "net.minecraft.world.level.chunk.NeverOverworldIceFragmentsR3913.apply(task.world, task.neverOverworldNeighbours, task.fromChunk);",
)

HELPER_SOURCE=r'''package net.minecraft.world.level.chunk;

import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.WorldGenLevel;

/** R39.25 profile gate. The matching datapack owns sea_level=128 natively.
 * Historical post-FEATURES/LIGHT flood writers must therefore remain read-only.
 */
public final class NeverOverworldNativeSeaR3925 {
    public static final String REVISION="R3925-native-sea-level-128-v1";
    public static final int SEA_LEVEL=128;
    public static final int TOP_SOURCE_WATER_Y=127;
    private NeverOverworldNativeSeaR3925(){}

    public static boolean active(final WorldGenLevel level){
        return level!=null
            && level.getLevel().dimension().equals(Level.OVERWORLD)
            && level.getMinY()==-512 && level.getHeight()==1024;
    }
    public static boolean active(final ServerLevel level){
        return level!=null
            && level.dimension().equals(Level.OVERWORLD)
            && level.getMinY()==-512 && level.getHeight()==1024;
    }
}
'''

def fail(msg:str)->None:
    raise ValueError("[R3925-NATIVE-SEA] "+msg)

def replace_light_calls(text:str)->str:
    if MARK in text:
        # Idempotence still verifies every historical writer is absent.
        for call in CALLS:
            if call in text: fail("historical LIGHT writer survived after marker: "+call)
        return text
    replaced=0
    lines=text.splitlines()
    out=[]
    for line in lines:
        stripped=line.strip()
        matched=None
        for call in CALLS:
            if stripped==call or stripped.startswith(call+" //"):
                matched=call;break
        if matched is None:
            out.append(line);continue
        indent=line[:len(line)-len(line.lstrip())]
        out.append(indent+MARK+": disabled "+matched)
        replaced+=1
    text="\n".join(out)+("\n" if text.endswith("\n") else "")
    if replaced!=len(CALLS):
        missing=[call for call in CALLS if call in text]
        fail(f"expected {len(CALLS)} LIGHT writers, replaced {replaced}; remaining={missing}")
    return text

def inject_gate(text:str,signature:str,statement:str)->str:
    marker=MARK+" "+signature.split("(",1)[0].split()[-1]
    start=text.find(signature)
    if start<0: fail("method signature missing: "+signature)
    brace=text.find("{",start)
    if brace<0: fail("opening brace missing: "+signature)
    window=text[brace+1:brace+300]
    if marker in window:return text
    insertion="\n        "+marker+"\n        "+statement
    return text[:brace+1]+insertion+text[brace+1:]

def prepare(folia:Path)->dict[Path,str]:
    paths=[folia/LIGHT,folia/FLOOD,folia/R15,folia/R399,folia/R3913]
    if any(not p.is_file() for p in paths):
        fail("materialized R39.24 water sources missing")
    staged={}
    staged[folia/LIGHT]=replace_light_calls((folia/LIGHT).read_text(encoding="utf-8"))

    flood=(folia/FLOOD).read_text(encoding="utf-8")
    flood=inject_gate(flood,"public static void apply(final WorldGenLevel level, final ChunkAccess chunk)","if (NeverOverworldNativeSeaR3925.active(level)) return;")
    flood=inject_gate(flood,"public static void reweatherSubmergedSurface(","if (NeverOverworldNativeSeaR3925.active(level)) return;")
    staged[folia/FLOOD]=flood

    r15=(folia/R15).read_text(encoding="utf-8")
    r15=inject_gate(r15,"public static int apply(final WorldGenLevel level, final ChunkAccess chunk)","if (NeverOverworldNativeSeaR3925.active(level)) return 0;")
    r15=inject_gate(r15,"public static int reconcileSeams(final WorldGenLevel level, final StaticCache2D<GenerationChunkHolder> cache, final ChunkAccess owner)","if (NeverOverworldNativeSeaR3925.active(level)) return 0;")
    r15=inject_gate(r15,"public static void publishFeatureBoundarySeeds(","if (NeverOverworldNativeSeaR3925.active(level)) return;")
    r15=inject_gate(r15,"public static void onFullChunk(","if (NeverOverworldNativeSeaR3925.active(level)) return;")
    staged[folia/R15]=r15

    r399=(folia/R399).read_text(encoding="utf-8")
    r399=inject_gate(r399,"public static int apply(WorldGenLevel level,StaticCache2D<GenerationChunkHolder> cache,ChunkAccess owner)","if (NeverOverworldNativeSeaR3925.active(level)) return 0;")
    staged[folia/R399]=r399

    r3913=(folia/R3913).read_text(encoding="utf-8")
    r3913=inject_gate(r3913,"public static int apply(WorldGenLevel level,StaticCache2D<GenerationChunkHolder> cache,ChunkAccess owner)","if (NeverOverworldNativeSeaR3925.active(level)) return 0;")
    staged[folia/R3913]=r3913
    staged[folia/HELPER]=HELPER_SOURCE
    return staged

def verify(folia:Path,staged:dict[Path,str]|None=None)->None:
    def get(rel):
        path=folia/rel
        return (staged[path] if staged and path in staged else path.read_text(encoding="utf-8"))
    light=get(LIGHT)
    for call in CALLS:
        if call in light:fail("synthetic LIGHT writer remains: "+call)
    if light.count(MARK)<len(CALLS):fail("native sea LIGHT retirement markers incomplete")

    helper=(staged.get(folia/HELPER) if staged and folia/HELPER in staged else (folia/HELPER).read_text(encoding="utf-8"))
    for token in ("SEA_LEVEL=128","TOP_SOURCE_WATER_Y=127","R3925-native-sea-level-128-v1"):
        if token not in helper:fail("helper contract missing "+token)

    flood=get(FLOOD);r15=get(R15);r399=get(R399);r3913=get(R3913)
    if flood.count("NeverOverworldNativeSeaR3925.active(level)")<2:fail("owner flood/reweather gates missing")
    if r15.count("NeverOverworldNativeSeaR3925.active(level)")<4:fail("R15 public write gates missing")
    if "NeverOverworldNativeSeaR3925.active(level)) return 0;" not in r399:fail("R399 native gate missing")
    if "NeverOverworldNativeSeaR3925.active(level)) return 0;" not in r3913:fail("R3913 native gate missing")
    print("[R3925-NATIVE-SEA] synthetic flood writers retired; native sea level owns Overworld water")

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("folia",type=Path)
    p.add_argument("--check-only",action="store_true")
    a=p.parse_args();folia=a.folia.resolve()
    staged=prepare(folia);verify(folia,staged)
    if not a.check_only:
        for path,text in staged.items():
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(text,encoding="utf-8")
    else:
        # Check-only must verify already-installed bytes, not merely a staged transform.
        verify(folia,None)

if __name__=="__main__":main()
