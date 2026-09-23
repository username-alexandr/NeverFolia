#!/usr/bin/env python3
"""NeverOverworld FIELD-R18 unified fixpack.

Extends accepted FIELD-R17 with:
- Y130/132 water-contact mushroom cleanup;
- Y128-only ocean flood seeding;
- deep generated lava cleanup below Y=-54;
- piece-local village dry admission before StructureStart persistence.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILE = "NO-FIELD-R18-FIXPACK-1"

JAVA = Path("folia-server/src/minecraft/java")
ECO13 = JAVA / "net/minecraft/world/level/chunk/NeverOverworldEcologyR13.java"
FLOOD15 = JAVA / "net/minecraft/world/level/chunk/NeverOverworldFloodConnectivityR15.java"
LAVA18 = JAVA / "net/minecraft/world/level/chunk/NeverOverworldLavaCleanupR18.java"
FLOOD = JAVA / "net/minecraft/world/level/chunk/NeverOverworldFlood.java"
SAFETY = JAVA / "net/minecraft/world/level/chunk/NeverOverworldGeneratedVillageSafety.java"
START = JAVA / "net/minecraft/world/level/levelgen/structure/StructureStart.java"

def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError("[NeverOverworld R18] " + message)

def read(folia: Path, rel: Path) -> str:
    p = folia / rel
    require(p.is_file(), "missing materialized source: " + str(rel))
    return p.read_text(encoding="utf-8")

def verify(folia: Path) -> None:
    eco13 = read(folia, ECO13)
    flood15 = read(folia, FLOOD15)
    lava18 = read(folia, LAVA18)
    flood = read(folia, FLOOD)
    safety = read(folia, SAFETY)
    start = read(folia, START)

    require("WATER_SUPPORT_SCAN_MAX_Y = 132" in eco13,
            "water-contact ecology scan does not cover Y130 screenshot case")
    require("waterSide" in eco13 and "shouldRemoveForWaterContext" in eco13,
            "horizontal water-contact mushroom cleanup missing")
    require("seamSensitive" in eco13,
            "owner-only seam mushroom/shoreline cleanup missing")
    require("level.getBlockState(" not in eco13,
            "unsafe cross-chunk WorldGenLevel read survived R18 ecology helper")

    require("hasOceanSeed" in flood15, "surface-ocean flood seed marker missing")
    require("y==SCAN_MAX_Y" in flood15 and "Blocks.WATER" in flood15,
            "R18 flood must require Y128 water seed")
    require("hasWater=false" not in flood15 and "hasWater=true" not in flood15,
            "old any-water flood seed survived")

    require("NeverOverworldLavaCleanupR18.cleanup(level, chunk);" in flood,
            "R18 deep lava cleanup hook missing")
    require("DEEP_LAVA_CUTOFF = -54" in lava18,
            "deep lava cutoff drifted")
    require("shouldRemoveGeneratedLava" in lava18,
            "deep lava policy missing")

    require("piecesDry(generator, randomState, heightAccessor, start)" in safety,
            "piece-local village dry admission missing")
    require("for (final StructurePiece piece : start.getPieces())" in safety,
            "village piece loop missing")
    require("Heightmap.Types.WORLD_SURFACE_WG" in safety,
            "village piece terrain gate missing")
    require("return start.isValid();" not in safety[safety.find("static boolean allowsGenerated("):safety.find("static Preview preview(")],
            "old start.isValid-only village gate survived")
    require("NeverOverworldVillageReclamation.apply" not in start,
            "whole-village reclamation re-enabled")

    print(f"[NeverOverworld R18] {PROFILE} final invariants OK")

def apply(folia: Path) -> None:
    subprocess.run([sys.executable, str(ROOT / "scripts/apply-never-overworld-fixpack-r17.py"), str(folia)],
                   cwd=ROOT, check=True)
    subprocess.run([sys.executable, str(ROOT / "scripts/apply-never-overworld-field-r18.py"), str(folia)],
                   cwd=ROOT, check=True)
    verify(folia)
    print(f"[NeverOverworld R18] {PROFILE} installed")

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
