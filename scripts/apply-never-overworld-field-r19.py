#!/usr/bin/env python3
"""FIELD-R19: imported dungeon surface structures use NeverOverworld island admission.

This stage contains no third-party structure assets. It only teaches the native
NeverOverworld placement/locate/safety helpers which imported structure IDs are
surface-only. Underground and OCEAN_FLOOR structures are intentionally absent
from the manifest and therefore keep their original datapack placement.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "config/neveroverworld-r19-dungeons.json"
JAVA = Path("folia-server/src/minecraft/java")
POLICY = JAVA / "net/minecraft/world/level/chunk/NeverOverworldVanillaStructurePolicy.java"
FAST = JAVA / "net/minecraft/world/level/chunk/NeverOverworldVanillaFastLocate.java"
SAFETY = JAVA / "net/minecraft/world/level/chunk/NeverOverworldGeneratedVillageSafety.java"

MARKER = "NeverFolia FIELD-R19 imported surface dungeon island policy"

def require(ok: bool, msg: str) -> None:
    if not ok:
        raise ValueError("[FIELD-R19] " + msg)

def load_manifest() -> dict:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    ids = data.get("surface_island_ids")
    require(data.get("profile") == "NO-FIELD-R19-DUNGEONS-1", "profile mismatch")
    require(isinstance(ids, list) and len(ids) == 131 and len(set(ids)) == 131,
            "expected exactly 131 unique surface IDs")
    for forbidden in ("explorify:ruins", "structory_towers:ocean_pillar",
                      "nova_structures:conduit_ruin", "explorify:end_shipwreck"):
        require(forbidden not in ids, "non-land structure leaked into surface manifest: " + forbidden)
    return data

def java_set(ids: list[str], indent: str = "    ") -> str:
    rows = []
    for i, value in enumerate(ids):
        comma = "," if i + 1 < len(ids) else ""
        rows.append(indent + '    "' + value + '"' + comma)
    return (
        indent + "// " + MARKER + "\n"
        + indent + "private static final Set<String> IMPORTED_SURFACE_R19 = Set.of(\n"
        + "\n".join(rows) + "\n"
        + indent + ");\n"
    )

def add_set(text: str, ids: list[str]) -> str:
    if "IMPORTED_SURFACE_R19" in text:
        return text
    ctor = re.search(r"\n    private NeverOverworld(?:VanillaStructurePolicy|VanillaFastLocate)\(\) \{\}", text)
    require(ctor is not None, "helper constructor anchor missing")
    block = "\n" + java_set(ids) 
    return text[:ctor.start()] + block + text[ctor.start():]

def patch_radius(text: str) -> str:
    if "NeverFolia FIELD-R19 imported radius policy" in text:
        return text
    sig = "    private static int sampleRadius(final String id) {"
    start = text.find(sig)
    require(start >= 0, "sampleRadius missing")
    end = text.find("\n    }", start)
    require(end >= 0, "sampleRadius end missing")
    method = text[start:end]
    anchor = "        return 32;"
    require(anchor in method, "sampleRadius default return 32 missing")
    extra = '''        // NeverFolia FIELD-R19 imported radius policy
        if (id.startsWith("nova_structures:")) return 64;
        if (id.startsWith("structory_towers:")) return 48;
        if (id.startsWith("explorify:")) return 48;
        if (id.startsWith("repurposed_structures:monument_")) return 96;
        if (id.startsWith("repurposed_structures:witch_hut_")) return 32;
'''
    method = method.replace(anchor, extra + anchor, 1)
    return text[:start] + method + text[end:]

def patch_policy(text: str, ids: list[str]) -> str:
    text = add_set(text, ids)
    old = '''        if (!DRY_LAND_ONLY.contains(id)) {
            return true;
        }'''
    new = '''        if (!DRY_LAND_ONLY.contains(id) && !IMPORTED_SURFACE_R19.contains(id)) {
            return true;
        }'''
    if new not in text:
        require(old in text, "generation dry-land gate anchor missing")
        text = text.replace(old, new, 1)
    text = patch_radius(text)
    return text

def patch_fast(text: str, ids: list[str]) -> str:
    text = add_set(text, ids)
    replacements = (
        (
            "if (id == null || !CONTROLLED.contains(id)) {",
            "if (id == null || (!CONTROLLED.contains(id) && !IMPORTED_SURFACE_R19.contains(id))) {",
        ),
        (
            "&& CONTROLLED.contains(id)",
            "&& (CONTROLLED.contains(id) || IMPORTED_SURFACE_R19.contains(id))",
        ),
        (
            "        if (!DRY_LAND_ONLY.contains(id)) {\n            return false;\n        }",
            "        if (!DRY_LAND_ONLY.contains(id) && !IMPORTED_SURFACE_R19.contains(id)) {\n            return false;\n        }",
        ),
    )
    for old, new in replacements:
        if new in text:
            continue
        require(old in text, "fast-locate anchor missing: " + old[:45])
        text = text.replace(old, new, 1)
    text = patch_radius(text)
    return text

def method_span(text: str, signature: str) -> tuple[int, int]:
    start = text.find(signature)
    require(start >= 0, "method missing: " + signature.strip())
    opening = text.find("{", start)
    require(opening >= 0, "method brace missing")
    depth = 0
    in_string = in_char = in_line = in_block = escaped = False
    i = opening
    while i < len(text):
        ch = text[i]
        nxt = text[i+1] if i+1 < len(text) else ""
        if in_line:
            if ch == "\n": in_line = False
            i += 1; continue
        if in_block:
            if ch == "*" and nxt == "/": in_block = False; i += 2
            else: i += 1
            continue
        if in_string:
            if escaped: escaped = False
            elif ch == "\\": escaped = True
            elif ch == '"': in_string = False
            i += 1; continue
        if in_char:
            if escaped: escaped = False
            elif ch == "\\": escaped = True
            elif ch == "'": in_char = False
            i += 1; continue
        if ch == "/" and nxt == "/": in_line = True; i += 2; continue
        if ch == "/" and nxt == "*": in_block = True; i += 2; continue
        if ch == '"': in_string = True; i += 1; continue
        if ch == "'": in_char = True; i += 1; continue
        if ch == "{": depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return start, i + 1
        i += 1
    raise ValueError("[FIELD-R19] unterminated method")

def safety_set(ids: list[str]) -> str:
    return java_set(ids)

def patch_safety(text: str, ids: list[str]) -> str:
    if "import java.util.Set;" not in text:
        anchor = "package net.minecraft.world.level.chunk;\n\n"
        require(anchor in text, "safety package anchor missing")
        text = text.replace(anchor, anchor + "import java.util.Set;\n", 1)

    if "IMPORTED_SURFACE_R19" not in text:
        ctor = text.find("    private NeverOverworldGeneratedVillageSafety() {}")
        require(ctor >= 0, "safety constructor anchor missing")
        text = text[:ctor] + safety_set(ids) + "\n" + text[ctor:]

    sig = "    static boolean allowsGenerated("
    start, end = method_span(text, sig)
    replacement = '''    static boolean allowsGenerated(
        final ChunkGenerator generator,
        final Holder<Structure> structureHolder,
        final RandomState randomState,
        final LevelHeightAccessor heightAccessor,
        final StructureStart start,
        final ResourceKey<Level> dimension
    ) {
        if (!isNeverOverworld(dimension, heightAccessor)) {
            return true;
        }

        final String id = structureHolder.unwrapKey()
            .map(key -> key.identifier().toString())
            .orElse("");
        final boolean village = isVillage(structureHolder);
        final boolean importedSurface = IMPORTED_SURFACE_R19.contains(id);
        if (!village && !importedSurface) {
            return true;
        }
        if (!start.isValid()) {
            return false;
        }
        return piecesDry(generator, randomState, heightAccessor, start);
    }'''
    text = text[:start] + replacement + text[end:]

    if "static boolean isImportedSurfaceId(" not in text:
        anchor = "    private static boolean isVillage("
        pos = text.find(anchor)
        require(pos >= 0, "isVillage anchor missing")
        helper = '''    static boolean isImportedSurfaceId(final String id) {
        return IMPORTED_SURFACE_R19.contains(id);
    }

    static int importedSurfaceCount() {
        return IMPORTED_SURFACE_R19.size();
    }

'''
        text = text[:pos] + helper + text[pos:]
    return text

def verify(root: Path, manifest: dict) -> None:
    ids = manifest["surface_island_ids"]
    policy = (root / POLICY).read_text(encoding="utf-8")
    fast = (root / FAST).read_text(encoding="utf-8")
    safety = (root / SAFETY).read_text(encoding="utf-8")
    for label, text in (("policy", policy), ("fast", fast), ("safety", safety)):
        require("IMPORTED_SURFACE_R19" in text, label + " imported set missing")
        for representative in (
            "nova_structures:trial_dungeon",  # underground: MUST NOT be in set
            "explorify:ruins",               # ocean-floor: MUST NOT be in set
            "structory_towers:ocean_pillar", # ocean-floor: MUST NOT be in set
        ):
            require(('"' + representative + '"') not in text.split("IMPORTED_SURFACE_R19",1)[1].split(");",1)[0],
                    label + " non-land representative leaked into imported set: " + representative)

    for representative in (
        "nova_structures:illager_manor",
        "structory_towers:ancient_temple",
        "explorify:farmstead",
        "repurposed_structures:witch_hut_oak",
        "repurposed_structures:monument_jungle",
    ):
        require(('"' + representative + '"') in safety, "missing representative: " + representative)

    require("!DRY_LAND_ONLY.contains(id) && !IMPORTED_SURFACE_R19.contains(id)" in policy,
            "generation prefilter not extended")
    require("IMPORTED_SURFACE_R19.contains(id)" in fast,
            "fast locate not extended")
    require("final boolean importedSurface = IMPORTED_SURFACE_R19.contains(id);" in safety,
            "exact generated-piece safety not extended")
    require("return piecesDry(generator, randomState, heightAccessor, start);" in safety,
            "exact imported surface piece dry gate missing")
    require("importedSurfaceCount()" in safety, "R19 smoke API missing")
    require("level.getBlockState(" not in safety, "unsafe world read leaked into R19 safety")
    require(len(ids) == 131, "manifest count drifted")
    print("[FIELD-R19] 131 imported surface structures use dry-island admission; underground/ocean unchanged")

def apply(root: Path) -> None:
    manifest = load_manifest()
    paths = {rel: root / rel for rel in (POLICY, FAST, SAFETY)}
    for rel, path in paths.items():
        require(path.is_file(), "materialized helper missing: " + str(rel))

    paths[POLICY].write_text(
        patch_policy(paths[POLICY].read_text(encoding="utf-8"), manifest["surface_island_ids"]),
        encoding="utf-8",
    )
    paths[FAST].write_text(
        patch_fast(paths[FAST].read_text(encoding="utf-8"), manifest["surface_island_ids"]),
        encoding="utf-8",
    )
    paths[SAFETY].write_text(
        patch_safety(paths[SAFETY].read_text(encoding="utf-8"), manifest["surface_island_ids"]),
        encoding="utf-8",
    )
    verify(root, manifest)

def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("folia", type=Path)
    p.add_argument("--check-only", action="store_true")
    a = p.parse_args()
    root = a.folia.resolve()
    if a.check_only:
        verify(root, load_manifest())
    else:
        apply(root)

if __name__ == "__main__":
    main()
