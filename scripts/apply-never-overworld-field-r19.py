#!/usr/bin/env python3
"""FIELD-R19: seam-safe ocean normalization, village cliff safety, and external Overworld structures."""
from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JAVA = Path("folia-server/src/minecraft/java")

FLOOD = JAVA / "net/minecraft/world/level/chunk/NeverOverworldFlood.java"
STRUCTURE_START = JAVA / "net/minecraft/world/level/levelgen/structure/StructureStart.java"
VILLAGE_SAFETY = JAVA / "net/minecraft/world/level/chunk/NeverOverworldGeneratedVillageSafety.java"
CHUNK_GENERATOR = JAVA / "net/minecraft/world/level/chunk/ChunkGenerator.java"

FLOOD_SRC = ROOT / "native/neveroverworld/field-r19/java/net/minecraft/world/level/chunk/NeverOverworldFloodNormalizationR19.java"
FLOOD_DST = JAVA / "net/minecraft/world/level/chunk/NeverOverworldFloodNormalizationR19.java"
FOUNDATION_SRC = ROOT / "native/neveroverworld/field-r19/java/net/minecraft/world/level/levelgen/structure/NeverOverworldVillageFoundationR19.java"
FOUNDATION_DST = JAVA / "net/minecraft/world/level/levelgen/structure/NeverOverworldVillageFoundationR19.java"
EXTERNAL_SRC = ROOT / "native/neveroverworld/field-r19/java/net/minecraft/world/level/chunk/NeverOverworldExternalStructurePolicyR19.java"
EXTERNAL_DST = JAVA / "net/minecraft/world/level/chunk/NeverOverworldExternalStructurePolicyR19.java"

R15_CALL = "        NeverOverworldFloodConnectivityR15.apply(level, chunk);\n"
R19_CALL = "        NeverOverworldFloodNormalizationR19.apply(level, chunk);\n"
R16_VILLAGE_CALL = "            NeverOverworldVillageFoundationR16.apply(level, this, chunkPos);"
R19_VILLAGE_CALL = "            NeverOverworldVillageFoundationR19.apply(level, this, chunkPos);"
EXTERNAL_MARKER = "// FIELD-R19: land-surface structures from supplied datapacks must resolve onto dry islands."
RELIEF_CONST = "    private static final int MAX_PIECE_RELIEF_R19 = 18;\n"

def fail(message: str) -> None:
    raise ValueError("[NeverOverworld R19] " + message)

def copy_helper(src: Path, dst: Path, staged: dict[Path, str]) -> None:
    if not src.is_file():
        fail(f"missing R19 helper source: {src}")
    payload = src.read_text(encoding="utf-8")
    if dst.exists() and dst.read_text(encoding="utf-8") != payload:
        fail(f"conflicting materialized R19 helper: {dst}")
    staged[dst] = payload

def patch_flood(text: str) -> str:
    if R19_CALL in text:
        return text
    if text.count(R15_CALL) != 1:
        fail(f"expected one R15 final flood call, got {text.count(R15_CALL)}")
    return text.replace(R15_CALL, R15_CALL + R19_CALL, 1)

def patch_structure_start(text: str) -> str:
    if R19_VILLAGE_CALL in text:
        return text
    if text.count(R16_VILLAGE_CALL) != 1:
        fail("R16 village foundation hook missing before R19 replacement")
    return text.replace(R16_VILLAGE_CALL, R19_VILLAGE_CALL, 1)

def replace_java_method(text: str, signature: str, replacement: str) -> str:
    if text.count(signature) != 1:
        fail(f"expected one method signature {signature!r}, got {text.count(signature)}")
    start = text.index(signature)
    opening = text.index("{", start + len(signature))
    depth = 0
    in_string = in_char = in_line = in_block = escaped = False
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
                return text[:start] + replacement + text[i + 1:]
        i += 1
    fail(f"unterminated method {signature!r}")

def patch_village_safety(text: str) -> str:
    if "MAX_PIECE_RELIEF_R19" not in text:
        anchor = "    private static final int MIN_DRY_BASE_HEIGHT = 129;\n"
        if text.count(anchor) != 1:
            fail("village safety dry-height constant anchor missing")
        text = text.replace(anchor, anchor + RELIEF_CONST, 1)

    signature = "    private static boolean piecesDry("
    if signature not in text:
        fail("R18 piece-local village admission method missing")
    replacement = r'''    private static boolean piecesDry(
        final ChunkGenerator generator,
        final RandomState randomState,
        final LevelHeightAccessor heightAccessor,
        final StructureStart start
    ) {
        for (final StructurePiece piece : start.getPieces()) {
            final BoundingBox box = piece.getBoundingBox();
            final int minX = box.minX();
            final int minZ = box.minZ();
            final int maxX = box.maxX();
            final int maxZ = box.maxZ();
            final long width = (long)maxX - minX + 1L;
            final long depth = (long)maxZ - minZ + 1L;
            if (width <= 0L || depth <= 0L || width > 64L || depth > 64L) {
                return false;
            }
            int minBase = Integer.MAX_VALUE;
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
                    if (maxBase - minBase > MAX_PIECE_RELIEF_R19) {
                        return false;
                    }
                }
            }
        }
        return true;
    }
'''
    return replace_java_method(text, signature, replacement)

def matching_brace(source: str, opening: int) -> int:
    depth = 0
    for i in range(opening, len(source)):
        if source[i] == "{": depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0: return i
    fail("unterminated tryGenerateStructure")

def param_name(params: str, pattern: str) -> str:
    m = re.search(pattern + r"\s+([A-Za-z_$][A-Za-z0-9_$]*)", params)
    if m is None: fail(f"could not infer tryGenerateStructure parameter {pattern}")
    return m.group(1)

def patch_external_policy_hook(source: str) -> str:
    if EXTERNAL_MARKER in source:
        return source
    method = source.find("private boolean tryGenerateStructure(")
    if method < 0: fail("tryGenerateStructure method missing")
    po = source.find("(", method); pc = source.find(")", po)
    params = source[po + 1:pc]
    entry = param_name(params, r"(?:StructureSet\.)?StructureSelectionEntry")
    random_state = param_name(params, r"RandomState")
    chunk = param_name(params, r"ChunkAccess")
    chunk_pos = param_name(params, r"ChunkPos")
    dimension = param_name(params, r"ResourceKey\s*<\s*Level\s*>")
    bo = source.find("{", pc); bc = matching_brace(source, bo)
    body = source[bo + 1:bc]
    marker = "// NeverFolia: reject submerged dry-land structure starts before generation."
    marker_at = body.find(marker)
    if marker_at < 0: fail("accepted vanilla dry-land policy hook missing")
    call = f"NeverOverworldVanillaStructurePolicy.allows(this, {entry}.structure(), {random_state}, {chunk}, {chunk_pos}, {dimension})"
    call_at = body.find(call)
    if call_at < 0: fail("vanilla dry-land policy call missing")
    guard_close = body.find("        }", call_at)
    if guard_close < 0: fail("vanilla dry-land policy guard close missing")
    insert_at = bo + 1 + guard_close + len("        }")
    injected = (
        "\n        " + EXTERNAL_MARKER + "\n"
        f"        if (!NeverOverworldExternalStructurePolicyR19.allows(this, {entry}.structure(), {random_state}, {chunk}, {chunk_pos}, {dimension})) {{\n"
        "            return false;\n"
        "        }"
    )
    return source[:insert_at] + injected + source[insert_at:]

def prepare(folia: Path) -> dict[Path, str]:
    paths = [FLOOD, STRUCTURE_START, VILLAGE_SAFETY, CHUNK_GENERATOR]
    for rel in paths:
        if not (folia / rel).is_file(): fail(f"missing materialized source: {rel}")

    staged: dict[Path, str] = {}
    staged[folia / FLOOD] = patch_flood((folia / FLOOD).read_text(encoding="utf-8"))
    staged[folia / STRUCTURE_START] = patch_structure_start((folia / STRUCTURE_START).read_text(encoding="utf-8"))
    staged[folia / VILLAGE_SAFETY] = patch_village_safety((folia / VILLAGE_SAFETY).read_text(encoding="utf-8"))
    staged[folia / CHUNK_GENERATOR] = patch_external_policy_hook((folia / CHUNK_GENERATOR).read_text(encoding="utf-8"))
    copy_helper(FLOOD_SRC, folia / FLOOD_DST, staged)
    copy_helper(FOUNDATION_SRC, folia / FOUNDATION_DST, staged)
    copy_helper(EXTERNAL_SRC, folia / EXTERNAL_DST, staged)
    return staged

def verify(folia: Path) -> None:
    flood = (folia / FLOOD).read_text(encoding="utf-8")
    structure = (folia / STRUCTURE_START).read_text(encoding="utf-8")
    safety = (folia / VILLAGE_SAFETY).read_text(encoding="utf-8")
    chunk = (folia / CHUNK_GENERATOR).read_text(encoding="utf-8")
    f19 = (folia / FLOOD_DST).read_text(encoding="utf-8")
    v19 = (folia / FOUNDATION_DST).read_text(encoding="utf-8")
    ext = (folia / EXTERNAL_DST).read_text(encoding="utf-8")

    checks = {
        "R19 flood normalization call": R19_CALL.strip() in flood,
        "R15 kept before R19": flood.index(R15_CALL.strip()) < flood.index(R19_CALL.strip()),
        "R19 foundation hook": R19_VILLAGE_CALL in structure and R16_VILLAGE_CALL not in structure,
        "village relief admission": "MAX_PIECE_RELIEF_R19 = 18" in safety and "maxBase - minBase" in safety,
        "external generation hook": EXTERNAL_MARKER in chunk and "NeverOverworldExternalStructurePolicyR19.allows" in chunk,
        "ocean column rebuild": "OCEAN_FLOOR_WG" in f19 and "drainBoundaryDryLandWater" in f19,
        "owner-only R19": "level.getBlockState(" not in f19 and "getChunk(" not in f19,
        "village support cap": "MAX_SUPPORT_DEPTH = 12" in v19 and "foundationMaterial" in v19,
        "external surface list": "structory_towers:ancient_temple" in ext and "nova_structures:tavern_oak" in ext and "explorify:tavern" in ext,
        "ocean/underground left alone": "structory_towers:ocean_pillar" not in ext and "nova_structures:conduit_ruin" not in ext and "nova_structures:trial_dungeon" not in ext,
    }
    missing = [name for name, ok in checks.items() if not ok]
    if missing: fail("invariant failure: " + ", ".join(missing))
    print("[NeverOverworld R19] seam water + village + external structure invariants OK")

def self_test() -> None:
    flood = "x\n" + R15_CALL + "y\n"
    assert patch_flood(flood).count(R19_CALL) == 1
    st = "x\n" + R16_VILLAGE_CALL + "\ny"
    assert R19_VILLAGE_CALL in patch_structure_start(st)
    print("[NeverOverworld R19] installer SELF-TEST OK")

def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("folia", nargs="?", type=Path)
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--check-only", action="store_true")
    a = p.parse_args()
    if a.self_test:
        self_test(); return
    if a.folia is None: p.error("materialized Folia directory required")
    folia = a.folia.resolve()
    if a.check_only:
        verify(folia); return
    staged = prepare(folia)
    for path, text in staged.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    verify(folia)
    print("[NeverOverworld R19] installed")

if __name__ == "__main__":
    main()
