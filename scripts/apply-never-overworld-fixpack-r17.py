#!/usr/bin/env python3
"""NeverOverworld FIELD-R17 unified worldgen fixpack.

Single entry point for the accepted post-FIELD-R12 fixes:
- R13 flooded ecology/fluid reset/dry-mine hardening;
- R14 verified ocean connectivity and lava barrier;
- R15 final Y<=128 connected-cavity audit + flora/height policy;
- R16 local village-piece foundations.

Historical stage installers remain for diagnosis, but production CI must invoke
this fixpack once and then verify the final R17 invariants with --check-only.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILE = "NO-FIELD-R17-FIXPACK-1"

STAGES = (
    "scripts/apply-never-overworld-field-r13.py",
    "scripts/apply-never-overworld-field-r14.py",
    "scripts/apply-never-overworld-field-r15.py",
    "scripts/apply-never-overworld-field-r16.py",
)

JAVA = Path("folia-server/src/minecraft/java")
FLOOD = JAVA / "net/minecraft/world/level/chunk/NeverOverworldFlood.java"
ECO13 = JAVA / "net/minecraft/world/level/chunk/NeverOverworldEcologyR13.java"
ECO15 = JAVA / "net/minecraft/world/level/chunk/NeverOverworldEcologyR15.java"
FLOOD15 = JAVA / "net/minecraft/world/level/chunk/NeverOverworldFloodConnectivityR15.java"
SIMPLE = JAVA / "net/minecraft/world/level/levelgen/feature/SimpleBlockFeature.java"
MUSHROOM = JAVA / "net/minecraft/world/level/levelgen/feature/AbstractHugeMushroomFeature.java"
BAMBOO = JAVA / "net/minecraft/world/level/levelgen/feature/BambooFeature.java"
STRUCTURE = JAVA / "net/minecraft/world/level/levelgen/structure/StructureStart.java"
VILLAGE16 = JAVA / "net/minecraft/world/level/levelgen/structure/NeverOverworldVillageFoundationR16.java"

DRY_FLOWERS = (
    "Blocks.DANDELION", "Blocks.POPPY", "Blocks.BLUE_ORCHID", "Blocks.ALLIUM",
    "Blocks.AZURE_BLUET", "Blocks.RED_TULIP", "Blocks.ORANGE_TULIP",
    "Blocks.WHITE_TULIP", "Blocks.PINK_TULIP", "Blocks.OXEYE_DAISY",
    "Blocks.CORNFLOWER", "Blocks.LILY_OF_THE_VALLEY", "Blocks.WITHER_ROSE",
    "Blocks.TORCHFLOWER", "Blocks.PITCHER_PLANT", "Blocks.PINK_PETALS",
    "Blocks.WILDFLOWERS", "Blocks.CACTUS_FLOWER", "Blocks.CLOSED_EYEBLOSSOM",
    "Blocks.OPEN_EYEBLOSSOM", "Blocks.SUNFLOWER", "Blocks.LILAC",
    "Blocks.ROSE_BUSH", "Blocks.PEONY",
)

def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError("[NeverOverworld R17] " + message)

def read(folia: Path, rel: Path) -> str:
    path = folia / rel
    require(path.is_file(), "missing materialized source: " + str(rel))
    return path.read_text(encoding="utf-8")

def verify(folia: Path) -> None:
    flood = read(folia, FLOOD)
    eco13 = read(folia, ECO13)
    eco15 = read(folia, ECO15)
    flood15 = read(folia, FLOOD15)
    simple = read(folia, SIMPLE)
    mushroom = read(folia, MUSHROOM)
    bamboo = read(folia, BAMBOO)
    structure = read(folia, STRUCTURE)
    village16 = read(folia, VILLAGE16)

    # Flood contract: only verified ocean-connected components, through Y=128,
    # with generated lava preserved as a barrier and dry mines protected.
    require("NeverOverworldFloodConnectivityR15.apply(level, chunk);" in flood,
            "final connected-cavity flood pass missing")
    require("NeverOverworldFloodBoundaryR11.apply(level, chunk);" not in flood,
            "obsolete R11 boundary flood call survived final R17 state")
    require("NeverOverworldFloodConnectivityR14.apply(level, chunk);" not in flood,
            "obsolete R14 boundary-only flood call survived final R17 state")
    require(flood.count("NeverOverworldEcologyR15.cleanup(level, chunk);") >= 2,
            "R17 requires ecology cleanup both before and after final flood")
    require("if (!state.is(Blocks.WATER)) {" in flood,
            "generated lava is still being stripped before flood")
    require("NeverOverworldDryMinesR12.prepare(chunk);" in flood,
            "dry-mine preparation missing")
    require("SCAN_MAX_Y = 128" in flood15, "final flood audit does not include Y=128")
    require("hasAdjacentLava" in flood15 and "NeverOverworldDryMinesR12.protectedCell" in flood15,
            "lava/dry-mine flood barriers missing")

    # Vegetation contract.
    for marker in ("Blocks.BROWN_MUSHROOM", "Blocks.RED_MUSHROOM", "Blocks.PUMPKIN",
                   "Blocks.BAMBOO", "Blocks.MOSS_CARPET", "Blocks.PALE_MOSS_CARPET"):
        require(marker in eco13, "R13 height flora marker missing: " + marker)
    for marker in ("Blocks.CAVE_VINES", "Blocks.CAVE_VINES_PLANT", "Blocks.AZALEA",
                   "Blocks.FLOWERING_AZALEA", "Blocks.SMALL_DRIPLEAF", "Blocks.BIG_DRIPLEAF",
                   "Blocks.CACTUS", "Blocks.MELON", "Blocks.BAMBOO", "Blocks.BAMBOO_SAPLING",
                   "Blocks.COCOA", "Blocks.AZURE_BLUET", "Blocks.PINK_PETALS", *DRY_FLOWERS):
        require(marker in eco15, "R17 ecology marker missing: " + marker)
    require("NeverOverworldEcologyR15.allowSimpleBlock" in simple,
            "early R17 SimpleBlock height gate missing")
    require("NeverOverworldEcologyR13.allowSimpleBlock" in simple,
            "R13 SimpleBlock gate missing")
    require("NeverOverworldEcologyR13.allowHeightGatedOrigin" in mushroom,
            "huge mushroom early height gate missing")
    require("NeverOverworldEcologyR13.allowHeightGatedOrigin" in bamboo,
            "bamboo early height gate missing")

    # Village contract: VILLAGE-NOFILL stays disabled globally; only short local
    # support directly beneath actual piece columns is allowed.
    require("NeverOverworldVillageFoundationR16.apply(level, this, chunkPos);" in structure,
            "local village foundation hook missing")
    require("NeverOverworldVillageReclamation.apply" not in structure,
            "old whole-village reclamation was re-enabled")
    require("MAX_SUPPORT_DEPTH = 10" in village16,
            "bounded village foundation depth changed")
    require("placedFloorY" in village16 and "supportBelow" in village16,
            "piece-local foundation evidence checks missing")

    print(f"[NeverOverworld R17] {PROFILE} final invariants OK")

def apply(folia: Path) -> None:
    for stage in STAGES:
        cmd = [sys.executable, str(ROOT / stage), str(folia)]
        subprocess.run(cmd, cwd=ROOT, check=True)
    verify(folia)
    print(f"[NeverOverworld R17] {PROFILE} installed as one fixpack")

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
