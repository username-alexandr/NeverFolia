#!/usr/bin/env python3
"""FIELD-R23: strict ocean-connectivity flood admission.

R22 fixed WATER/AIR seams with prospective surface seeds, but its proximity
fallback could promote a large dry seam-touching cave merely because an ocean
column existed within 16 blocks. That violates the NeverOverworld contract:
only components proven connected to the surface ocean may be flooded.

R23 keeps R22's scheduling-independent OCEAN_FLOOR_WG surface seeds and real
FEATURES-neighbour connectivity, while removing proximity-only admission.
"""
from __future__ import annotations

import argparse
from pathlib import Path

JAVA=Path("folia-server/src/minecraft/java")
FLOOD15=JAVA/"net/minecraft/world/level/chunk/NeverOverworldFloodConnectivityR15.java"

SCAN_STATE_R22="        int head=0,tail=0;boolean hasOceanSeed=false,hasProximitySeed=false,touchesHorizontalSeam=false;\n"
SCAN_STATE_R23="        int head=0,tail=0;boolean hasOceanSeed=false,touchesHorizontalSeam=false;\n"

EXTERNAL_R22=(
    "            if(externalSeeds!=null&&externalSeeds[e]){\n"
    "                if(chunk.getBlockState(pos).is(Blocks.WATER))hasOceanSeed=true;\n"
    "                else hasProximitySeed=true;\n"
    "            }\n"
)
EXTERNAL_R23=(
    "            if(externalSeeds!=null&&externalSeeds[e]"
    "&&chunk.getBlockState(pos).is(Blocks.WATER))hasOceanSeed=true;\n"
)

GUARD_R22=(
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
GUARD_R23=(
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

PROXIMITY_SEED_CALL=(
    "        final int proximity = seedOceanProximityFallback(cache, owner, minY, maxY, externalSeeds);\n"
)
NEIGHBOR_MASK=(
    "        final boolean[] neighborProximityWater = "
    "proximityConnectedFloodable(cache, neighbor, minY, maxY);\n"
)
NEIGHBOR_GATE_R22="                if (!neighborOceanWater[ne] && !neighborProximityWater[ne]) continue;\n"
NEIGHBOR_GATE_R23="                if (!neighborOceanWater[ne]) continue;\n"

def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError("[FIELD-R23] "+message)

def patch(text: str) -> str:
    # Idempotent R23 state.
    if "R23DrySeam" in text and PROXIMITY_SEED_CALL not in text and NEIGHBOR_MASK not in text:
        return text

    require(PROXIMITY_SEED_CALL in text, "R22 proximity seed call missing")
    require(NEIGHBOR_MASK in text, "R22 neighbour proximity mask missing")
    require(NEIGHBOR_GATE_R22 in text, "R22 neighbour proximity gate missing")
    require(SCAN_STATE_R22 in text, "R22 scan state missing")
    require(EXTERNAL_R22 in text, "R22 external seed classification missing")
    require(GUARD_R22 in text, "R22 proximity flood guard missing")

    text=text.replace(PROXIMITY_SEED_CALL,"",1)
    text=text.replace(NEIGHBOR_MASK,"",1)
    text=text.replace(NEIGHBOR_GATE_R22,NEIGHBOR_GATE_R23,1)
    text=text.replace(SCAN_STATE_R22,SCAN_STATE_R23,1)
    text=text.replace(EXTERNAL_R22,EXTERNAL_R23,1)
    text=text.replace(GUARD_R22,GUARD_R23,1)
    return text

def verify(folia: Path) -> None:
    path=folia/FLOOD15
    require(path.is_file(),"R15/R22 flood helper missing")
    text=path.read_text(encoding="utf-8")

    # R22's useful scheduling-independent surface contract stays active.
    for marker in (
        "prospectiveOceanSurfaceSeed",
        "surfaceOceanSeed",
        "chunk.getHeight(Heightmap.Types.OCEAN_FLOOR_WG, x, z)",
        "reconcileSeams(final WorldGenLevel level",
        "getChunkIfPresent(ChunkStatus.FEATURES)",
        "oceanConnectedFloodable(neighbor, minY, maxY)",
        NEIGHBOR_GATE_R23.strip(),
        EXTERNAL_R23.strip(),
        "R23DrySeam",
    ):
        require(marker in text,"required strict-ocean marker missing: "+marker)

    # Proximity helpers may remain for diagnostics/audit history, but they are
    # forbidden from contributing seeds or neighbour admission in production.
    require(PROXIMITY_SEED_CALL not in text,
            "proximity fallback still seeds owner flood components")
    require(NEIGHBOR_MASK not in text,
            "proximity-connected neighbour mask still participates in flooding")
    require(NEIGHBOR_GATE_R22 not in text,
            "proximity neighbour gate survived")
    require("hasProximitySeed" not in text,
            "dry external seeds can still qualify a component")
    require("proximityFallback=allowSeams" not in text,
            "proximity fallback can still authorize flooding")
    require("[NeverFolia][R22ProximityFlood]" not in text,
            "R22 proximity flood production branch survived")

    print("[FIELD-R23] strict verified-ocean flood admission invariants OK")

def main() -> None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("folia",type=Path)
    p.add_argument("--check-only",action="store_true")
    a=p.parse_args()
    folia=a.folia.resolve()
    if a.check_only:
        verify(folia)
        return
    path=folia/FLOOD15
    require(path.is_file(),"R15/R22 flood helper missing")
    path.write_text(patch(path.read_text(encoding="utf-8")),encoding="utf-8")
    verify(folia)
    print("[FIELD-R23] installed: proximity is diagnostic-only; dry caves require real ocean connectivity")

if __name__=="__main__":
    main()
