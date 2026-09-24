#!/usr/bin/env python3
"""NeverOverworld FIELD-R19 unified fixpack.

Extends accepted FIELD-R18 with external Overworld structures:
- imported surface-land structures use dry-island admission;
- imported ocean/underground structures keep source placement;
- vanilla structure policy remains owned by R18/earlier NeverOverworld layers.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILE = "NO-FIELD-R19-FIXPACK-1"
JAVA = Path("folia-server/src/minecraft/java")
CHUNK = JAVA / "net/minecraft/world/level/chunk/ChunkGenerator.java"
HELPER = JAVA / "net/minecraft/world/level/chunk/NeverOverworldExternalStructurePolicyR19.java"

def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError("[NeverOverworld R19] " + message)

def verify(folia: Path) -> None:
    chunk = (folia / CHUNK).read_text(encoding="utf-8")
    helper = (folia / HELPER).read_text(encoding="utf-8")
    require("NeverOverworldExternalStructurePolicyR19.allows" in chunk,
            "external structure island admission hook missing")
    require(helper.count('case "') == 131,
            "external surface structure ID count must stay 131")
    require("MIN_DRY_SURFACE_Y = 129" in helper,
            "R19 island dry height changed")
    require("WORLD_SURFACE_WG" in helper,
            "R19 must use surface height sampling")
    require("getChunk(" not in helper and "getBlockState(" not in helper,
            "R19 island policy must not load/read neighbour chunk state")
    for marker in (
        "nova_structures:tavern_oak",
        "explorify:tavern",
        "structory_towers:wizard_tower",
        "repurposed_structures:witch_hut_oak",
        "repurposed_structures:monument_jungle",
    ):
        require(marker in helper, "representative R19 surface structure missing: " + marker)
    for marker in (
        "explorify:ruins",
        "structory_towers:ocean_pillar",
        "nova_structures:catacomb",
        "nova_structures:conduit_ruin",
        "minecraft:village_plains",
    ):
        require(f'case "{marker}"' not in helper,
                "non-R19 surface structure was island-gated: " + marker)
    print(f"[NeverOverworld R19] {PROFILE} final invariants OK")

def apply(folia: Path) -> None:
    subprocess.run(
        [sys.executable, str(ROOT / "scripts/apply-never-overworld-fixpack-r18.py"), str(folia)],
        cwd=ROOT, check=True
    )
    subprocess.run(
        [sys.executable, str(ROOT / "scripts/apply-never-overworld-external-structure-policy-r19.py"), str(folia)],
        cwd=ROOT, check=True
    )
    verify(folia)
    print(f"[NeverOverworld R19] {PROFILE} installed")

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
