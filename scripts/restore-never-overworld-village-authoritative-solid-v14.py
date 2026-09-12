#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

SAFETY_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldGeneratedVillageSafety.java")
SAFETY_SIG = "    static boolean allowsGenerated("
INSPECT_SIG = "    private static Preview inspectBoundingBox("
R9V4_BODY = '''    static boolean allowsGenerated(
        final ChunkGenerator generator,
        final Holder<Structure> structureHolder,
        final RandomState randomState,
        final LevelHeightAccessor heightAccessor,
        final StructureStart start,
        final ResourceKey<Level> dimension
    ) {
        if (!isNeverOverworld(dimension, heightAccessor) || !isVillage(structureHolder)) {
            return true;
        }
        // NeverFolia R9-v4: the shared candidate envelope is authoritative for
        // prediction/generation agreement. Do not re-run an expensive all-column
        // bbox height scan after Structure.generate(), because /locate cannot
        // reproduce that decision without triggering the Folia watchdog.
        return start.isValid();
    }
'''
RESTORED_BODY = '''    static boolean allowsGenerated(
        final ChunkGenerator generator,
        final Holder<Structure> structureHolder,
        final RandomState randomState,
        final LevelHeightAccessor heightAccessor,
        final StructureStart start,
        final ResourceKey<Level> dimension
    ) {
        if (!isNeverOverworld(dimension, heightAccessor) || !isVillage(structureHolder)) {
            return true;
        }
        // NeverFolia R9-v14: the predictor remains cheap and zero-generation,
        // but real generation is authoritative. Validate the actual generated
        // Jigsaw bbox against SOLID terrain: OCEAN_FLOOR_WG deliberately ignores
        // water columns, unlike WORLD_SURFACE_WG which can treat fluid as surface.
        if (!start.isValid()) {
            return false;
        }
        return inspectBoundingBox(generator, randomState, heightAccessor, start.getBoundingBox()).dry();
    }
'''
MARKER = "NeverFolia R9-v14: the predictor remains cheap and zero-generation"


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][R9 village authoritative solid v14] {message}")


def method_bounds(text: str, signature: str) -> tuple[int, int]:
    start = text.find(signature)
    if start < 0:
        fail(f"method not found: {signature.strip()}")
    opening = text.find("{", start)
    if opening < 0:
        fail("opening brace missing")
    depth = 0
    in_s = in_c = in_line = in_block = escaped = False
    i = opening
    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""
        if in_line:
            if ch == "\n": in_line = False
            i += 1; continue
        if in_block:
            if ch == "*" and nxt == "/": in_block = False; i += 2
            else: i += 1
            continue
        if in_s:
            if escaped: escaped = False
            elif ch == "\\": escaped = True
            elif ch == '"': in_s = False
            i += 1; continue
        if in_c:
            if escaped: escaped = False
            elif ch == "\\": escaped = True
            elif ch == "'": in_c = False
            i += 1; continue
        if ch == "/" and nxt == "/": in_line = True; i += 2; continue
        if ch == "/" and nxt == "*": in_block = True; i += 2; continue
        if ch == '"': in_s = True; i += 1; continue
        if ch == "'": in_c = True; i += 1; continue
        if ch == "{": depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                if end < len(text) and text[end] == "\n": end += 1
                return start, end
        i += 1
    fail("unterminated method")


def patch(text: str) -> str:
    if MARKER in text:
        validate(text)
        return text
    start, end = method_bounds(text, SAFETY_SIG)
    method = text[start:end]
    if R9V4_BODY not in text and "return start.isValid();" not in method:
        fail("R9-v4 disabled safety anchor missing")
    text = text[:start] + RESTORED_BODY + text[end:]
    i_start, i_end = method_bounds(text, INSPECT_SIG)
    inspect = text[i_start:i_end]
    if "Heightmap.Types.OCEAN_FLOOR_WG" not in inspect:
        count = inspect.count("Heightmap.Types.WORLD_SURFACE_WG")
        if count != 1:
            fail(f"expected one WORLD_SURFACE_WG in inspectBoundingBox, got {count}")
        inspect = inspect.replace("Heightmap.Types.WORLD_SURFACE_WG", "Heightmap.Types.OCEAN_FLOOR_WG", 1)
        text = text[:i_start] + inspect + text[i_end:]
    validate(text)
    return text


def validate(text: str) -> None:
    start, end = method_bounds(text, SAFETY_SIG)
    allows = text[start:end]
    i_start, i_end = method_bounds(text, INSPECT_SIG)
    inspect = text[i_start:i_end]
    required = (
        MARKER,
        "start.getBoundingBox()",
        "inspectBoundingBox(generator, randomState, heightAccessor, start.getBoundingBox()).dry()",
    )
    missing = [x for x in required if x not in allows]
    if missing:
        fail(f"allowsGenerated markers missing: {missing}")
    if "return start.isValid();" in allows:
        fail("R9-v4 validity-only bypass survived")
    if "Heightmap.Types.OCEAN_FLOOR_WG" not in inspect:
        fail("solid terrain heightmap missing")
    if "Heightmap.Types.WORLD_SURFACE_WG" in inspect:
        fail("fluid-aware WORLD_SURFACE_WG survived in bbox inspector")
    if "generator.getBaseHeight(" not in inspect:
        fail("bbox inspector no longer checks terrain columns")


def self_test() -> None:
    fixture = '''class NeverOverworldGeneratedVillageSafety {
    static boolean allowsGenerated(
        final ChunkGenerator generator,
        final Holder<Structure> structureHolder,
        final RandomState randomState,
        final LevelHeightAccessor heightAccessor,
        final StructureStart start,
        final ResourceKey<Level> dimension
    ) {
        if (!isNeverOverworld(dimension, heightAccessor) || !isVillage(structureHolder)) {
            return true;
        }
        // NeverFolia R9-v4: the shared candidate envelope is authoritative for
        // prediction/generation agreement. Do not re-run an expensive all-column
        // bbox height scan after Structure.generate(), because /locate cannot
        // reproduce that decision without triggering the Folia watchdog.
        return start.isValid();
    }
    private static Preview inspectBoundingBox(
        final ChunkGenerator generator,
        final RandomState randomState,
        final LevelHeightAccessor heightAccessor,
        final BoundingBox box
    ) {
        final int base = generator.getBaseHeight(0, 0, Heightmap.Types.WORLD_SURFACE_WG, heightAccessor, randomState);
        return base >= 129 ? Preview.dry(0,0,0,0) : Preview.wet(0,0,0,0,0,0,base);
    }
}
'''
    out = patch(fixture)
    validate(out)
    if patch(out) != out:
        fail("SELF-TEST: transformer is not idempotent")
    print("[NeverFolia][R9 village authoritative solid v14] SELF-TEST OK")
    print("  real generated bbox is authoritative")
    print("  terrain gate uses OCEAN_FLOOR_WG, not WORLD_SURFACE_WG")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("folia", nargs="?", type=Path)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        self_test(); return
    if args.folia is None:
        ap.error("folia worktree is required")
    self_test()
    helper = args.folia.resolve() / SAFETY_REL
    if not helper.is_file():
        fail(f"safety helper missing: {helper}")
    helper.write_text(patch(helper.read_text(encoding="utf-8")), encoding="utf-8")
    print(f"[NeverFolia][R9 village authoritative solid v14] restored: {helper}")


if __name__ == "__main__":
    main()
