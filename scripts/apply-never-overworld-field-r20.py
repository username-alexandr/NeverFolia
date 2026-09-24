#!/usr/bin/env python3
"""FIELD-R20: chunk-seam flood safety and steep-village rejection.

Run after FIELD-R19. R20 keeps imported Overworld structures unchanged and only
hardens NeverOverworld ocean/village behavior.
"""
from __future__ import annotations

import argparse
from pathlib import Path

JAVA = Path("folia-server/src/minecraft/java")
FLOOD15 = JAVA / "net/minecraft/world/level/chunk/NeverOverworldFloodConnectivityR15.java"
SAFETY = JAVA / "net/minecraft/world/level/chunk/NeverOverworldGeneratedVillageSafety.java"

MAX_SPAN = 8

def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError("[FIELD-R20] " + message)

def patch_village(text: str) -> str:
    if "MAX_PIECE_SURFACE_SPAN = 8" not in text:
        anchor = "    private static final int MIN_DRY_BASE_HEIGHT = 129;\n"
        require(anchor in text, "village dry-height constant anchor missing")
        text = text.replace(
            anchor,
            anchor + "    private static final int MAX_PIECE_SURFACE_SPAN = 8;\n",
            1,
        )

    old = """            for (int z = minZ; z <= maxZ; ++z) {
                for (int x = minX; x <= maxX; ++x) {
                    final int base = generator.getBaseHeight(
                        x,
                        z,
                        Heightmap.Types.WORLD_SURFACE_WG,
                        heightAccessor,
                        randomState
                    );
                    if (base <= MIN_DRY_BASE_HEIGHT) {
                        return false;
                    }
                }
            }"""
    new = """            int minBase = Integer.MAX_VALUE;
            int maxBase = Integer.MIN_VALUE;
            for (int z = minZ; z <= maxZ; ++z) {
                for (int x = minX; x <= maxX; ++x) {
                    final int base = generator.getBaseHeight(
                        x,
                        z,
                        Heightmap.Types.WORLD_SURFACE_WG,
                        heightAccessor,
                        randomState
                    );
                    if (base <= MIN_DRY_BASE_HEIGHT) {
                        return false;
                    }
                    minBase = Math.min(minBase, base);
                    maxBase = Math.max(maxBase, base);
                }
            }
            if (!pieceSurfaceSpanAllowed(minBase, maxBase)) {
                return false;
            }"""
    if "pieceSurfaceSpanAllowed(minBase, maxBase)" not in text:
        require(old in text, "R18 piece dry-loop anchor missing")
        text = text.replace(old, new, 1)

    if "static boolean pieceSurfaceSpanAllowed(" not in text:
        anchor = "    private static boolean piecesDry(\n"
        require(anchor in text, "piecesDry anchor missing")
        helper = f"""    static boolean pieceSurfaceSpanAllowed(final int minBase, final int maxBase) {{
        return minBase != Integer.MAX_VALUE
            && maxBase != Integer.MIN_VALUE
            && maxBase >= minBase
            && maxBase - minBase <= MAX_PIECE_SURFACE_SPAN;
    }}

"""
        text = text.replace(anchor, helper + anchor, 1)
    return text

def verify(folia: Path) -> None:
    flood = (folia / FLOOD15).read_text(encoding="utf-8")
    safety = (folia / SAFETY).read_text(encoding="utf-8")

    require("touchesHorizontalSeam" in flood, "R20 seam-component marker missing")
    require("horizontalSeamBelowOcean" in flood, "R20 seam helper missing")
    require(
        "if(!hasOceanSeed||touchesHorizontalSeam)return 0;" in flood
        or "if(!hasOceanSeed||(!allowSeams&&touchesHorizontalSeam))return 0;" in flood,
        "R20/R21 seam-safe flood guard missing"
    )
    require("MAX_PIECE_SURFACE_SPAN = 8" in safety,
            "R20 village surface-span constant missing")
    require("pieceSurfaceSpanAllowed(minBase, maxBase)" in safety,
            "R20 village span gate missing")
    require("maxBase - minBase <= MAX_PIECE_SURFACE_SPAN" in safety,
            "R20 village span policy missing")
    require("getChunk(" not in safety,
            "R20 village gate must not load generated neighbour chunks")
    print("[FIELD-R20] final invariants OK")

def apply(folia: Path) -> None:
    flood = folia / FLOOD15
    safety = folia / SAFETY
    require(flood.is_file(), "R15 flood helper missing")
    require(safety.is_file(), "generated village safety helper missing")

    safety.write_text(patch_village(safety.read_text(encoding="utf-8")), encoding="utf-8")
    verify(folia)
    print("[FIELD-R20] installed")

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
