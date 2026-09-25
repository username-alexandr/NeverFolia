#!/usr/bin/env python3
"""FIELD-R23: release gate for strict physical ocean connectivity.

FIELD-R22 now owns the actual scheduling-independent implementation: each
owner<->neighbour seam is evaluated in the symmetric 2x3/3x2 intersection of
the two LIGHT radius-1 FEATURES caches. Ocean connectivity propagates only
through physically adjacent floodable cells from real/prospective Y128 ocean
seeds. R23 freezes that contract and rejects any return of proximity/size/span
heuristics.
"""
from __future__ import annotations

import argparse
import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JAVA = Path("folia-server/src/minecraft/java")
FLOOD15 = JAVA / "net/minecraft/world/level/chunk/NeverOverworldFloodConnectivityR15.java"

REQUIRED = (
    "prospectiveOceanSurfaceSeed",
    "surfaceOceanSeed",
    "Heightmap.Types.OCEAN_FLOOR_WG",
    "localOceanConnectedMasks",
    "pairNeighborOceanMask",
    "bridgeMasks",
    "expandMaskFromSeed",
    "cachedFeaturesChunk",
    "getChunkIfPresent(ChunkStatus.FEATURES)",
    "final boolean[][] localOceanMasks = localOceanConnectedMasks(cache, owner, minY, maxY);",
    "final boolean[] neighborOceanWater = pairNeighborOceanMask(",
    "if (!neighborOceanWater[ne]) continue;",
    "boolean hasOceanSeed=false,hasExternalSeed=false,touchesHorizontalSeam=false",
    "hasExternalSeed=true;",
    "if(allowSeams&&touchesHorizontalSeam&&!hasExternalSeed)return 0;",
)

FORBIDDEN = (
    "seedOceanProximityFallback",
    "nearOceanColumns",
    "proximityFallbackAllowed",
    "proximityConnectedFloodable",
    "neighborProximityWater",
    "hasProximitySeed",
    "R22ProximityFlood",
)

def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError("[FIELD-R23] " + message)

def verify(folia: Path) -> None:
    path = folia / FLOOD15
    require(path.is_file(), "strict flood helper missing")
    text = path.read_text(encoding="utf-8")

    for marker in REQUIRED:
        require(marker in text, "strict pair-domain marker missing: " + marker)
    for marker in FORBIDDEN:
        require(marker not in text, "unsafe proximity flood logic survived: " + marker)

    require("getChunk(" not in text and "level.getBlockState(" not in text,
            "R23 must not synchronously load/read neighbour chunks through level")
    require("cache.contains(chunkX, chunkZ)" in text,
            "R23 must stay inside the existing LIGHT FEATURES cache")
    print("[FIELD-R23] strict symmetric cached-ocean connectivity invariants OK")

def self_test() -> None:
    # Reuse FIELD-R22's transformer self-test so the exact installation layer
    # and this release gate cannot drift independently.
    stage = runpy.run_path(str(ROOT / "scripts/apply-never-overworld-field-r22.py"))
    stage["self_test"]()
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
    verify(folia)
    if not a.check_only:
        print("[FIELD-R23] installed: strict pair-domain cave flood gate")

if __name__ == "__main__":
    main()
