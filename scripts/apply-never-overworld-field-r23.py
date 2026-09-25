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
    "            if(externalSeeds!=null&&externalSeeds[e]"
    "&&chunk.getBlockState(pos).is(Blocks.WATER))hasOceanSeed=true;\n"
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
    require("getChunk(" not in text and "level.getBlockState(" not in text,
            "R23 must not synchronously load/read neighbours through level")
    print("[FIELD-R23] strict ocean-connected cave flooding invariants OK")

def self_test()->None:
    fixture=(
        "class X {\n"
        +PROXIMITY_CALL+STATE_OLD+EXTERNAL_OLD+GUARD_OLD+MASK+GATE_OLD+
        "boolean prospectiveOceanSurfaceSeed; boolean surfaceOceanSeed;\n"
        "boolean oceanConnectedFloodable; boolean reconcileSeams;\n"
        "void x(){ getChunkIfPresent(ChunkStatus.FEATURES); }\n"
        "}\n"
    )
    out=patch(fixture)
    require(PROXIMITY_CALL.strip() not in out,"SELF-TEST proximity call survived")
    require("hasProximitySeed" not in out,"SELF-TEST proximity seed survived")
    require(GATE_NEW.strip() in out,"SELF-TEST strict neighbour gate missing")
    require("R23DrySeam" in out,"SELF-TEST strict dry-seam marker missing")
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
