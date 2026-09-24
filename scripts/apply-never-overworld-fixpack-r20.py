#!/usr/bin/env python3
"""NeverOverworld FIELD-R20 unified fixpack.

Extends accepted FIELD-R19 with:
- seam-safe ocean-connected flood behavior;
- steep village-piece rejection to avoid cliff/double-wall artifacts;
- keeps FIELD-R19 external Overworld structures and island admission unchanged.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILE = "NO-FIELD-R20-FIXPACK-1"
JAVA = Path("folia-server/src/minecraft/java")
FLOOD15 = JAVA / "net/minecraft/world/level/chunk/NeverOverworldFloodConnectivityR15.java"
SAFETY = JAVA / "net/minecraft/world/level/chunk/NeverOverworldGeneratedVillageSafety.java"
R19 = JAVA / "net/minecraft/world/level/chunk/NeverOverworldExternalStructurePolicyR19.java"

def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError("[NeverOverworld R20] " + message)

def verify(folia: Path) -> None:
    flood = (folia / FLOOD15).read_text(encoding="utf-8")
    safety = (folia / SAFETY).read_text(encoding="utf-8")
    r19 = (folia / R19).read_text(encoding="utf-8")

    require("horizontalSeamBelowOcean" in flood,
            "R20 flood seam helper missing")
    require("touchesHorizontalSeam" in flood,
            "R20 flood seam state missing")
    require("if(!hasOceanSeed||touchesHorizontalSeam)return 0;" in flood,
            "R20 must reject partial cross-chunk source-water flood")
    require("MAX_PIECE_SURFACE_SPAN = 8" in safety,
            "R20 village piece slope cap missing")
    require("pieceSurfaceSpanAllowed(minBase, maxBase)" in safety,
            "R20 village piece slope gate missing")
    require("maxBase - minBase <= MAX_PIECE_SURFACE_SPAN" in safety,
            "R20 village slope policy missing")
    require("getChunk(" not in safety,
            "R20 village admission must not synchronously load neighbours")

    require(r19.count('case "') == 131,
            "R19 external surface structure table changed")
    require("MIN_DRY_SURFACE_Y = 129" in r19,
            "R19 island admission changed")
    require("getChunk(" not in r19 and "getBlockState(" not in r19,
            "R19 external structure admission must remain generation-state-only")

    print(f"[NeverOverworld R20] {PROFILE} final invariants OK")

def apply(folia: Path) -> None:
    subprocess.run(
        [sys.executable, str(ROOT / "scripts/apply-never-overworld-fixpack-r19.py"), str(folia)],
        cwd=ROOT, check=True
    )
    subprocess.run(
        [sys.executable, str(ROOT / "scripts/apply-never-overworld-field-r20.py"), str(folia)],
        cwd=ROOT, check=True
    )
    verify(folia)
    print(f"[NeverOverworld R20] {PROFILE} installed")

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
