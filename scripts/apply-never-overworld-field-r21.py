#!/usr/bin/env python3
"""FIELD-R21: radius-1 cache-aware flood seam reconciliation.

Runs after FIELD-R20. Rewrites the canonical ChunkStatusTasks LIGHT hook so
adjacent FEATURES-complete chunks already present in the generation cache can
seed the owner chunk consistently across horizontal seams. No synchronous chunk
loads and no WorldGenLevel neighbour block reads are used.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JAVA = Path("folia-server/src/minecraft/java")
TASKS = JAVA / "net/minecraft/world/level/chunk/status/ChunkStatusTasks.java"
FLOOD15 = JAVA / "net/minecraft/world/level/chunk/NeverOverworldFloodConnectivityR15.java"

def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError("[FIELD-R21] " + message)

def verify(folia: Path) -> None:
    tasks = (folia / TASKS).read_text(encoding="utf-8")
    flood = (folia / FLOOD15).read_text(encoding="utf-8")

    reconcile = "NeverOverworldFloodConnectivityR15.reconcileSeams("
    owner = "NeverOverworldFlood.apply("
    require(tasks.count(reconcile) == 1, "LIGHT must contain exactly one cache-aware seam reconcile call")
    require(tasks.count(owner) == 1, "LIGHT must contain exactly one owner flood call")
    require(tasks.find(owner) < tasks.find(reconcile), "seam reconcile must run after owner flood reset")

    for marker in (
        "StaticCache2D<GenerationChunkHolder>",
        "getChunkIfPresent(ChunkStatus.FEATURES)",
        "oceanConnectedFloodable",
        "externalSeeds",
        "allowSeams",
    ):
        require(marker in flood, "R21 flood helper marker missing: " + marker)

    require("scan(chunk,visited,queue,x,y,z,minY,maxY,externalSeeds,allowSeams)" in flood,
            "R21 component scan must receive external seam seeds")
    require("boolean[] externalSeeds,boolean allowSeams" in flood,
            "R21 component scan seam parameters missing")
    require("if (!traversable(chunk, pos)) return tailIn;" in flood,
            "R21 neighbour ocean connectivity must traverse floodable volume, not existing water only")

    require("level.getBlockState(" not in flood,
            "R21 must not use WorldGenLevel neighbour block reads")
    require("getChunk(" not in flood,
            "R21 must not synchronously load neighbour chunks")
    print("[FIELD-R21] cache-aware seam reconciliation invariants OK")

def apply(folia: Path) -> None:
    subprocess.run(
        [sys.executable, str(ROOT / "scripts/normalize-never-overworld-light-flood-call.py"), str(folia)],
        cwd=ROOT, check=True
    )
    verify(folia)
    print("[FIELD-R21] installed")

def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("folia", type=Path)
    p.add_argument("--check-only", action="store_true")
    a = p.parse_args()
    folia = a.folia.resolve()
    if a.check_only:
        verify(folia)
    else:
        apply(folia)

if __name__ == "__main__":
    main()
