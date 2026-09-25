#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path

REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/levelgen/structure/ScatteredFeaturePiece.java")
MARKER = "// NeverFolia: raise swamp huts to the VANILLA_FLOODED waterline."


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][swamp hut waterline] {message}")


def find_method(source: str) -> tuple[int, int, str]:
    start = source.find("protected boolean updateAverageGroundHeight(")
    if start < 0:
        fail("updateAverageGroundHeight method not found")
    params_open = source.find("(", start)
    params_close = source.find(")", params_open)
    if params_open < 0 or params_close < 0:
        fail("method parameter list not found")
    params = source[params_open + 1:params_close]
    level_match = re.search(
        r"(?:WorldGenLevel|WorldGenLevelAccessor|LevelAccessor|ServerLevelAccessor|LevelHeightAccessor)\s+([A-Za-z_$][A-Za-z0-9_$]*)",
        params,
    )
    if level_match is None:
        # Mojmap/Paper can change the concrete accessor name; accepting any
        # *Level*Accessor suffix keeps the patch structural instead of binding
        # to a local variable name.
        level_match = re.search(r"[A-Za-z0-9_$.]*Level[A-Za-z0-9_$.]*Accessor\s+([A-Za-z_$][A-Za-z0-9_$]*)", params)
    if level_match is None:
        fail(f"could not infer level accessor parameter from: {params!r}")
    level_name = level_match.group(1)

    opening = source.find("{", params_close)
    if opening < 0:
        fail("method opening brace not found")
    depth = 0
    for idx in range(opening, len(source)):
        if source[idx] == "{":
            depth += 1
        elif source[idx] == "}":
            depth -= 1
            if depth == 0:
                return opening, idx, level_name
    fail("unterminated updateAverageGroundHeight method")


def patch_source(source: str) -> str:
    if MARKER in source:
        fail("swamp-hut waterline patch already applied")
    opening, closing, level_name = find_method(source)
    body = source[opening + 1:closing]
    assignments = list(re.finditer(r"(?m)^(?P<indent>[ \t]*)this\.heightPosition\s*=\s*[^;]+;", body))
    if len(assignments) != 1:
        fail(f"expected one heightPosition assignment in method, got {len(assignments)}")
    match = assignments[0]
    indent = match.group("indent")
    absolute_end = opening + 1 + match.end()
    injection = (
        "\n"
        f"{indent}{MARKER}\n"
        f"{indent}if (this instanceof net.minecraft.world.level.levelgen.structure.structures.SwampHutPiece\n"
        f"{indent}    && {level_name}.getMinY() == -512 && {level_name}.getHeight() == 1024) {{\n"
        f"{indent}    this.heightPosition = Math.max(this.heightPosition, 129);\n"
        f"{indent}}}"
    )
    patched = source[:absolute_end] + injection + source[absolute_end:]
    if patched.count(MARKER) != 1:
        fail("waterline guard was not injected exactly once")
    if f"{level_name}.getMinY()" not in patched:
        fail("inferred level accessor was not used")
    return patched


def self_test() -> None:
    fixtures = (
        '''class ScatteredFeaturePiece {
    private int heightPosition = -1;
    protected boolean updateAverageGroundHeight(LevelAccessor levelAccessor, BoundingBox box, int offset) {
        if (this.heightPosition >= 0) return true;
        int total = 100;
        int count = 2;
        this.heightPosition = total / count;
        this.boundingBox.move(0, this.heightPosition - this.boundingBox.minY() + offset, 0);
        return true;
    }
}
''',
        '''class ScatteredFeaturePiece {
    private int heightPosition = -1;
    protected boolean updateAverageGroundHeight(WorldGenLevel world, BoundingBox box, int offset) {
        this.heightPosition = 70;
        this.boundingBox.move(0, this.heightPosition - this.boundingBox.minY() + offset, 0);
        return true;
    }
}
''',
    )
    for fixture, level_name in zip(fixtures, ("levelAccessor", "world")):
        patched = patch_source(fixture)
        for marker in (MARKER, "SwampHutPiece", "Math.max(this.heightPosition, 129)", f"{level_name}.getMinY()"):
            if marker not in patched:
                fail(f"SELF-TEST missing {marker}")
    print("[NeverFolia][swamp hut waterline] SELF-TEST OK")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("folia", nargs="?", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if args.folia is None:
        parser.error("folia worktree is required unless --self-test is used")
    self_test()
    path = args.folia.resolve() / REL
    if not path.is_file():
        fail(f"source not found: {path}")
    path.write_text(patch_source(path.read_text(encoding="utf-8")), encoding="utf-8")
    print("[NeverFolia][swamp hut waterline] swamp hut waterline adaptation applied")
    print("  minimum hut ground anchor: Y=129")
    print(f"  source: {path}")


if __name__ == "__main__":
    main()
