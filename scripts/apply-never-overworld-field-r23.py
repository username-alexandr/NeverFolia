#!/usr/bin/env python3
"""FIELD-R23: strict physical ocean connectivity for cave flooding.

R22 fixed scheduling-dependent WATER/AIR seams with prospective Y128 ocean
seeds, but its bounded "near ocean" fallback could still flood a large cave
component without a proven path to ocean water. R23 removes that heuristic.

After R23 a component may flood only when it contains an authoritative Y128
surface-ocean seed or receives a seed through an actually ocean-connected
FEATURES neighbour. Proximity, component size and seam area are never sufficient
on their own. Lava-adjacent and protected mine cells remain hard barriers.
"""
from __future__ import annotations

import argparse
import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JAVA = Path("folia-server/src/minecraft/java")
FLOOD15 = JAVA / "net/minecraft/world/level/chunk/NeverOverworldFloodConnectivityR15.java"

R22 = runpy.run_path(str(ROOT / "scripts/apply-never-overworld-field-r22.py"))
PROXIMITY_METHODS = R22["PROXIMITY_METHODS"]

PROXIMITY_HELPER = """    static boolean proximityFallbackAllowed(
        final int componentSize,
        final int boundaryCells,
        final int verticalSpan,
        final boolean nearOcean
    ) {
        return nearOcean
            && componentSize >= 768
            && boundaryCells >= 48
            && verticalSpan >= 8;
    }

"""

PROXIMITY_CALL = (
    "        final int proximity = seedOceanProximityFallback(cache, owner, minY, maxY, externalSeeds);\n"
)
PROXIMITY_MASK = (
    "        final boolean[] neighborProximityWater = "
    "proximityConnectedFloodable(cache, neighbor, minY, maxY);\n"
)
UNSAFE_NEIGHBOR_GATE = (
    "                if (!neighborOceanWater[ne] && !neighborProximityWater[ne]) continue;\n"
)
STRICT_NEIGHBOR_GATE = "                if (!neighborOceanWater[ne]) continue;\n"

UNSAFE_SCAN_STATE = (
    "        int head=0,tail=0;boolean hasOceanSeed=false,hasProximitySeed=false,touchesHorizontalSeam=false;\n"
)
STRICT_SCAN_STATE = (
    "        int head=0,tail=0;boolean hasOceanSeed=false,touchesHorizontalSeam=false;\n"
)

UNSAFE_EXTERNAL = (
    "            if(externalSeeds!=null&&externalSeeds[e]){\n"
    "                if(chunk.getBlockState(pos).is(Blocks.WATER))hasOceanSeed=true;\n"
    "                else hasProximitySeed=true;\n"
    "            }\n"
)
STRICT_EXTERNAL = (
    "            if(externalSeeds!=null&&externalSeeds[e]"
    "&&chunk.getBlockState(pos).is(Blocks.WATER))hasOceanSeed=true;\n"
)

UNSAFE_GUARD = (
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

STRICT_GUARD = (
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

def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError("[FIELD-R23] " + message)

def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new and new in text and old not in text:
        return text
    if not new and old not in text:
        return text
    require(text.count(old) == 1, label + " missing/duplicated")
    return text.replace(old, new, 1)

def patch(text: str) -> str:
    text = replace_once(text, PROXIMITY_CALL, "", "proximity owner seed call")
    text = replace_once(text, PROXIMITY_MASK, "", "neighbour proximity mask")
    text = replace_once(text, UNSAFE_NEIGHBOR_GATE, STRICT_NEIGHBOR_GATE, "neighbour proximity gate")
    text = replace_once(text, UNSAFE_SCAN_STATE, STRICT_SCAN_STATE, "scan proximity state")
    text = replace_once(text, UNSAFE_EXTERNAL, STRICT_EXTERNAL, "external proximity seed classification")
    text = replace_once(text, UNSAFE_GUARD, STRICT_GUARD, "proximity fallback guard")
    text = replace_once(text, PROXIMITY_METHODS, "", "proximity helper methods")
    text = replace_once(text, PROXIMITY_HELPER, "", "proximity policy helper")
    return text

def verify(folia: Path) -> None:
    path = folia / FLOOD15
    require(path.is_file(), "R15/R22 flood helper missing")
    text = path.read_text(encoding="utf-8")

    for forbidden in (
        "seedOceanProximityFallback",
        "proximityConnectedFloodable",
        "nearOceanColumns",
        "proximityFallbackAllowed",
        "neighborProximityWater",
        "hasProximitySeed",
        "R22ProximityFlood",
    ):
        require(forbidden not in text, "unsafe proximity flooding survived: " + forbidden)

    for marker in (
        "prospectiveOceanSurfaceSeed",
        "surfaceOceanSeed",
        "Heightmap.Types.OCEAN_FLOOR_WG",
        "final boolean[] neighborOceanWater = oceanConnectedFloodable",
        "if (!neighborOceanWater[ne]) continue;",
        "if(!hasOceanSeed)",
        "NeverOverworldDryMinesR12.protectedCell",
        "!hasAdjacentLava(chunk,pos)",
        "getChunkIfPresent(ChunkStatus.FEATURES)",
    ):
        require(marker in text, "strict ocean-connectivity marker missing: " + marker)

    require("getChunk(" not in text and "level.getBlockState(" not in text,
            "R23 must not synchronously load/read neighbours through level")
    print("[FIELD-R23] strict physical ocean connectivity invariants OK")

def self_test() -> None:
    fixture = (
        PROXIMITY_HELPER
        + PROXIMITY_METHODS
        + PROXIMITY_CALL
        + PROXIMITY_MASK
        + UNSAFE_NEIGHBOR_GATE
        + UNSAFE_SCAN_STATE
        + UNSAFE_EXTERNAL
        + UNSAFE_GUARD
    )
    out = patch(fixture)
    for forbidden in (
        "seedOceanProximityFallback",
        "proximityConnectedFloodable",
        "nearOceanColumns",
        "proximityFallbackAllowed",
        "neighborProximityWater",
        "hasProximitySeed",
        "R22ProximityFlood",
    ):
        require(forbidden not in out, "SELF-TEST unsafe marker survived: " + forbidden)
    require(STRICT_NEIGHBOR_GATE in out, "SELF-TEST strict neighbour gate missing")
    require(STRICT_EXTERNAL in out, "SELF-TEST strict external seed missing")
    require("[NeverFolia][R23DrySeam]" in out, "SELF-TEST strict dry-seam marker missing")
    require(patch(out) == out, "SELF-TEST transformer is not idempotent")
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
    path = folia / FLOOD15
    require(path.is_file(), "R15/R22 flood helper missing")
    path.write_text(patch(path.read_text(encoding="utf-8")), encoding="utf-8")
    verify(folia)
    print("[FIELD-R23] installed: cave flood requires proven ocean connectivity")

if __name__ == "__main__":
    main()
