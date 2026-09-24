#!/usr/bin/env python3
"""NeverOverworld FIELD-R21 unified fixpack.

Extends FIELD-R20 with cache-aware horizontal seam reconciliation while keeping
R19 external Overworld structures/island admission and R20 village hardening.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILE = "NO-FIELD-R21-FIXPACK-1"
JAVA = Path("folia-server/src/minecraft/java")
FLOOD15 = JAVA / "net/minecraft/world/level/chunk/NeverOverworldFloodConnectivityR15.java"
TASKS = JAVA / "net/minecraft/world/level/chunk/status/ChunkStatusTasks.java"
SAFETY = JAVA / "net/minecraft/world/level/chunk/NeverOverworldGeneratedVillageSafety.java"
R19 = JAVA / "net/minecraft/world/level/chunk/NeverOverworldExternalStructurePolicyR19.java"

def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError("[NeverOverworld R21] " + message)

def verify(folia: Path) -> None:
    flood = (folia / FLOOD15).read_text(encoding="utf-8")
    tasks = (folia / TASKS).read_text(encoding="utf-8")
    safety = (folia / SAFETY).read_text(encoding="utf-8")
    r19 = (folia / R19).read_text(encoding="utf-8")

    require("reconcileSeams" in flood and "oceanConnectedFloodable" in flood,
            "R21 cache-aware flood helper missing")
    require("getChunkIfPresent(ChunkStatus.FEATURES)" in flood,
            "R21 must read only already-present FEATURES neighbours")
    require("scan(chunk,visited,queue,x,y,z,minY,maxY,externalSeeds,allowSeams)" in flood,
            "R21 component scan must receive external seam seeds")
    require("boolean[] externalSeeds,boolean allowSeams" in flood,
            "R21 component scan seam parameters missing")
    require("if (!traversable(chunk, pos)) return tailIn;" in flood,
            "R21 neighbour ocean connectivity must traverse floodable volume")
    require("getChunk(" not in flood and "level.getBlockState(" not in flood,
            "R21 flood helper must not synchronously load/read neighbours through level")
    require(tasks.count("NeverOverworldFloodConnectivityR15.reconcileSeams(") == 1,
            "R21 LIGHT seam reconcile hook missing/duplicated")
    require(tasks.find("NeverOverworldFlood.apply(")
            < tasks.find("NeverOverworldFloodConnectivityR15.reconcileSeams("),
            "R21 seam reconcile must follow owner flood reset")

    require("MAX_PIECE_SURFACE_SPAN = 8" in safety,
            "R20 village slope hardening missing")
    require(r19.count('case "') == 131,
            "R19 external surface structure table changed")
    require("MIN_DRY_SURFACE_Y = 129" in r19,
            "R19 island admission changed")

    print(f"[NeverOverworld R21] {PROFILE} final invariants OK")

def apply(folia: Path) -> None:
    subprocess.run(
        [sys.executable, str(ROOT / "scripts/apply-never-overworld-fixpack-r20.py"), str(folia)],
        cwd=ROOT, check=True
    )
    subprocess.run(
        [sys.executable, str(ROOT / "scripts/apply-never-overworld-field-r21.py"), str(folia)],
        cwd=ROOT, check=True
    )
    verify(folia)
    print(f"[NeverOverworld R21] {PROFILE} installed")

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
