#!/usr/bin/env python3
"""FIELD-R18: water-contact mushrooms, surface-seeded flood, deep-lava cleanup and piece-local village admission.

Run after the accepted FIELD-R17 fixpack.
"""
from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JAVA = Path("folia-server/src/minecraft/java")

FLOOD = JAVA / "net/minecraft/world/level/chunk/NeverOverworldFlood.java"
LAVA_SRC = ROOT / "native/neveroverworld/field-r18/java/net/minecraft/world/level/chunk/NeverOverworldLavaCleanupR18.java"
LAVA_DST = JAVA / "net/minecraft/world/level/chunk/NeverOverworldLavaCleanupR18.java"
SAFETY = JAVA / "net/minecraft/world/level/chunk/NeverOverworldGeneratedVillageSafety.java"
FOUNDATION = JAVA / "net/minecraft/world/level/levelgen/structure/NeverOverworldVillageFoundationR16.java"

FLOOD_ANCHOR = "        NeverOverworldFloodConnectivityR15.apply(level, chunk);"
FLOOD_CALL = "        NeverOverworldLavaCleanupR18.cleanup(level, chunk);\n" + FLOOD_ANCHOR

VILLAGE_SIG = "    static boolean allowsGenerated("
VILLAGE_OLD = "        return start.isValid();"
VILLAGE_NEW = """        if (!start.isValid()) {
            return false;
        }
        return piecesDry(generator, randomState, heightAccessor, start);"""

PIECE_METHOD = r'''
    private static boolean piecesDry(
        final ChunkGenerator generator,
        final RandomState randomState,
        final LevelHeightAccessor heightAccessor,
        final StructureStart start
    ) {
        for (final StructurePiece piece : start.getPieces()) {
            final BoundingBox box = piece.getBoundingBox();
            final int minX = box.minX(), maxX = box.maxX();
            final int minZ = box.minZ(), maxZ = box.maxZ();
            final long width = (long)maxX - minX + 1L;
            final long depth = (long)maxZ - minZ + 1L;
            if (width <= 0L || depth <= 0L || width > 64L || depth > 64L) {
                return false;
            }

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
                }
            }
        }
        return true;
    }

'''

def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError("[FIELD-R18] " + message)

def method_span(text: str, signature: str) -> tuple[int, int]:
    start = text.find(signature)
    require(start >= 0, "method signature missing: " + signature)
    brace = text.find("{", start)
    require(brace >= 0, "method opening brace missing: " + signature)
    depth = 0
    for i in range(brace, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return start, i + 1
    raise ValueError("[FIELD-R18] unterminated method: " + signature)

def patch_flood(text: str) -> str:
    if "NeverOverworldLavaCleanupR18.cleanup(level, chunk);" in text:
        return text
    require(text.count(FLOOD_ANCHOR) == 1, "R15 flood-call anchor mismatch")
    return text.replace(FLOOD_ANCHOR, FLOOD_CALL, 1)

def patch_safety(text: str) -> str:
    start, end = method_span(text, VILLAGE_SIG)
    method = text[start:end]
    if "piecesDry(generator, randomState, heightAccessor, start)" not in method:
        require(method.count(VILLAGE_OLD) == 1, "expected V17 start.isValid-only village gate")
        method = method.replace(VILLAGE_OLD, VILLAGE_NEW, 1)
        text = text[:start] + method + text[end:]

    if "import net.minecraft.world.level.levelgen.structure.StructurePiece;" not in text:
        anchor = "import net.minecraft.world.level.levelgen.structure.StructureStart;\n"
        require(anchor in text, "StructureStart import anchor missing")
        text = text.replace(anchor, anchor + "import net.minecraft.world.level.levelgen.structure.StructurePiece;\n", 1)

    if "private static boolean piecesDry(" not in text:
        anchor = "    static Preview preview("
        require(anchor in text, "preview anchor missing")
        text = text.replace(anchor, PIECE_METHOD + anchor, 1)
    return text

def patch_foundation(text: str) -> str:
    text = text.replace("static final int MAX_SUPPORT_DEPTH = 10;", "static final int MAX_SUPPORT_DEPTH = 24;")
    old = """        return state.isAir()
            || state.is(Blocks.WATER)
            || state.is(Blocks.SNOW)
            || state.canBeReplaced();"""
    new = """        return state.isAir()
            || state.is(Blocks.WATER)
            || state.is(Blocks.SNOW)
            || state.is(Blocks.SNOW_BLOCK)
            || state.is(Blocks.POWDER_SNOW)
            || state.is(Blocks.ICE)
            || state.is(Blocks.PACKED_ICE)
            || state.is(Blocks.BLUE_ICE)
            || state.canBeReplaced();"""
    require(old in text or "state.is(Blocks.BLUE_ICE)" in text, "R16 foundation gap anchor missing")
    if old in text:
        text = text.replace(old, new, 1)
    return text

def verify(folia: Path) -> None:
    flood = (folia / FLOOD).read_text(encoding="utf-8")
    safety = (folia / SAFETY).read_text(encoding="utf-8")
    lava = (folia / LAVA_DST).read_text(encoding="utf-8")
    foundation = (folia / FOUNDATION).read_text(encoding="utf-8")

    require("NeverOverworldFloodConnectivityR15.apply(level, chunk);" in flood, "R15 flood missing")
    require("NeverOverworldLavaCleanupR18.cleanup(level, chunk);" in flood, "R18 lava cleanup hook missing")
    require("DEEP_LAVA_CUTOFF = -54" in lava, "R18 deep lava cutoff drifted")
    require("state.is(Blocks.LAVA)" in lava, "R18 lava cleanup marker missing")

    start, end = method_span(safety, VILLAGE_SIG)
    method = safety[start:end]
    require("piecesDry(generator, randomState, heightAccessor, start)" in method,
            "piece-local village gate missing")
    require("return start.isValid();" not in method, "old village no-op gate survived")
    require("for (final StructurePiece piece : start.getPieces())" in safety,
            "piece iteration missing")
    require("Heightmap.Types.WORLD_SURFACE_WG" in safety, "piece dry heightmap check missing")
    require("base <= MIN_DRY_BASE_HEIGHT" in safety,
            "piece gate must reject ocean-surface base height 129")
    require("MAX_SUPPORT_DEPTH = 24" in foundation,
            "R18 village foundation depth must be 24")
    for marker in ("Blocks.SNOW_BLOCK", "Blocks.POWDER_SNOW", "Blocks.ICE", "Blocks.PACKED_ICE", "Blocks.BLUE_ICE"):
        require(marker in foundation, "R18 village foundation gap marker missing: " + marker)
    require("NeverOverworldVillageReclamation.apply" not in (folia / JAVA / "net/minecraft/world/level/levelgen/structure/StructureStart.java").read_text(encoding="utf-8"),
            "whole-village reclamation was re-enabled")

    print("[FIELD-R18] final invariants OK")

def apply(folia: Path) -> None:
    flood = folia / FLOOD
    safety = folia / SAFETY
    require(flood.is_file(), "NeverOverworldFlood missing")
    require(safety.is_file(), "GeneratedVillageSafety missing")

    flood.write_text(patch_flood(flood.read_text(encoding="utf-8")), encoding="utf-8")
    safety.write_text(patch_safety(safety.read_text(encoding="utf-8")), encoding="utf-8")
    foundation = folia / FOUNDATION
    require(foundation.is_file(), "R16 village foundation helper missing")
    foundation.write_text(patch_foundation(foundation.read_text(encoding="utf-8")), encoding="utf-8")

    payload = LAVA_SRC.read_text(encoding="utf-8")
    target = folia / LAVA_DST
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        require(target.read_text(encoding="utf-8") == payload, "conflicting R18 lava helper")
    else:
        target.write_text(payload, encoding="utf-8")

    verify(folia)
    print("[FIELD-R18] installed")

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
