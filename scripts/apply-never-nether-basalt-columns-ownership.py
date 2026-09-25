#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from pathlib import Path

REL = Path(
    "folia-server/src/minecraft/java/net/minecraft/world/level/levelgen/feature/BasaltColumnsFeature.java"
)


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][NeverNether basalt columns] {message}")


def patch_source(source: str) -> str:
    marker = "NeverNether: keep Basalt Columns writes inside the generating chunk"
    if marker in source:
        fail("BasaltColumnsFeature is already patched")

    # The hook is deliberately scoped to the NeverNether technical height. Vanilla
    # Nether and every other dimension keep the upstream BasaltColumnsFeature path.
    import_anchor = "import net.minecraft.world.level.WorldGenLevel;\n"
    if import_anchor not in source:
        fail("WorldGenLevel import anchor not found")
    source = source.replace(
        import_anchor,
        import_anchor + "import net.minecraft.world.level.ChunkPos;\n",
        1,
    )

    origin_match = re.search(
        r"(?P<indent>^[ \t]*)BlockPos\s+(?P<origin>[A-Za-z_$][A-Za-z0-9_$]*)\s*=\s*context\.origin\(\);",
        source,
        re.MULTILINE,
    )
    if origin_match is None:
        fail("context.origin() assignment not found")
    indent = origin_match.group("indent")
    origin = origin_match.group("origin")
    owner_decl = (
        origin_match.group(0)
        + "\n"
        + indent
        + "// NeverNether: keep Basalt Columns writes inside the generating chunk.\n"
        + indent
        + f"ChunkPos neverNetherOwner = isNeverNether(context.level()) ? new ChunkPos({origin}.getX() >> 4, {origin}.getZ() >> 4) : null;"
    )
    source = source[: origin_match.start()] + owner_decl + source[origin_match.end() :]

    call_pattern = re.compile(
        r"this\.placeColumn\("
        r"(?P<args>[^;\n]*?config\.reach\(\)\.sample\(random\))"
        r"\)"
    )
    call_matches = list(call_pattern.finditer(source))
    if len(call_matches) != 1:
        fail(f"expected exactly one placeColumn call, got {len(call_matches)}")
    m = call_matches[0]
    source = source[: m.start()] + f"this.placeColumn({m.group('args')}, neverNetherOwner)" + source[m.end() :]

    # Paper/Folia may change the concrete first-parameter type or formatting of
    # this private helper. Match the method structurally instead of pinning the
    # upstream decompile signature to LevelAccessor and single-line formatting.
    signature_pattern = re.compile(
        r"(?P<prefix>private\s+boolean\s+placeColumn\s*\()"
        r"(?P<params>[^)]*?)"
        r"(?P<suffix>\)\s*\{)",
        re.DOTALL,
    )
    sig_matches = list(signature_pattern.finditer(source))
    if len(sig_matches) != 1:
        fail(f"expected exactly one placeColumn signature, got {len(sig_matches)}")
    m = sig_matches[0]
    params = m.group("params")
    trimmed = params.rstrip()
    trailing = params[len(trimmed) :]
    replacement = (
        m.group("prefix")
        + trimmed
        + ", ChunkPos neverNetherOwner"
        + trailing
        + m.group("suffix")
    )
    source = source[: m.start()] + replacement + source[m.end() :]

    # Guard every candidate before findSurface/findAir reads it. Paper may wrap
    # the enhanced-for header across lines, so do not parse the complete loop with
    # a format-sensitive regex. Locate the unique betweenClosed call, find the
    # containing enhanced-for, balance its parentheses and inject after its `{`.
    between_matches = list(re.finditer(r"\bBlockPos\.betweenClosed\s*\(", source))
    if len(between_matches) != 1:
        fail(f"expected exactly one BlockPos.betweenClosed call, got {len(between_matches)}")
    between_start = between_matches[0].start()

    for_matches = list(re.finditer(r"\bfor\s*\(", source[:between_start]))
    if not for_matches:
        fail("enhanced-for before BlockPos.betweenClosed not found")
    for_match = for_matches[-1]
    open_paren = source.find("(", for_match.start(), between_start)
    if open_paren < 0:
        fail("enhanced-for opening parenthesis not found")

    colon = source.rfind(":", open_paren, between_start)
    if colon < 0:
        fail("enhanced-for colon before BlockPos.betweenClosed not found")
    declaration = source[open_paren + 1 : colon]
    pos_match = re.search(r"([A-Za-z_$][A-Za-z0-9_$]*)\s*$", declaration)
    if pos_match is None:
        fail("enhanced-for block-position variable not found")
    pos = pos_match.group(1)

    depth = 0
    close_paren = -1
    for index in range(open_paren, len(source)):
        ch = source[index]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                close_paren = index
                break
    if close_paren < 0:
        fail("enhanced-for closing parenthesis not found")

    brace = close_paren + 1
    while brace < len(source) and source[brace].isspace():
        brace += 1
    if brace >= len(source) or source[brace] != "{":
        fail("enhanced-for opening brace not found")

    line_start = source.rfind("\n", 0, for_match.start()) + 1
    line_prefix = source[line_start : for_match.start()]
    indent_match = re.match(r"[ \t]*", line_prefix)
    loop_indent = indent_match.group(0) if indent_match else ""
    guard = (
        "\n"
        + loop_indent
        + "    if (neverNetherOwner != null && !isOwnedBy(neverNetherOwner, "
        + pos
        + ")) {\n"
        + loop_indent
        + "        continue;\n"
        + loop_indent
        + "    }"
    )
    source = source[: brace + 1] + guard + source[brace + 1 :]

    helper_anchor = "    private static boolean isAirOrLavaOcean("
    idx = source.find(helper_anchor)
    if idx < 0:
        fail("isAirOrLavaOcean helper anchor not found")
    helpers = '''    private static boolean isNeverNether(WorldGenLevel level) {
        return level.getMinY() == -128 && level.getHeight() == 1024;
    }

    private static boolean isOwnedBy(ChunkPos owner, BlockPos pos) {
        return (pos.getX() >> 4) == owner.x() && (pos.getZ() >> 4) == owner.z();
    }

'''
    source = source[:idx] + helpers + source[idx:]
    return source


def self_test() -> None:
    fixture = '''package net.minecraft.world.level.levelgen.feature;
import net.minecraft.world.level.WorldGenLevel;
class BasaltColumnsFeature {
    boolean place(FeaturePlaceContext context) {
        BlockPos origin = context.origin();
        WorldGenLevel level = context.level();
        this.placeColumn(level, lavaSeaLevel, pos, blocksToPlaceY, config.reach().sample(random));
        return true;
    }
    private boolean placeColumn(PatchedLevelReader level, int lavaSeaLevel, BlockPos origin,
                                int columnHeight, int reach) {
        block0: for (BlockPos pos : BlockPos.betweenClosed(
                origin.getX() - reach, origin.getY(), origin.getZ() - reach,
                origin.getX() + reach, origin.getY(), origin.getZ() + reach
        )) {
            BlockPos columnPos = null;
        }
        return false;
    }
    private static boolean isAirOrLavaOcean(LevelAccessor level, int lavaSeaLevel, BlockPos blockPos) { return false; }
}
'''
    patched = patch_source(fixture)
    assert "ChunkPos neverNetherOwner" in patched
    assert "new ChunkPos(origin.getX() >> 4, origin.getZ() >> 4)" in patched
    assert "int reach, ChunkPos neverNetherOwner" in patched
    assert "neverNetherOwner)" in patched
    assert "!isOwnedBy(neverNetherOwner, pos)" in patched
    assert "level.getMinY() == -128 && level.getHeight() == 1024" in patched
    print("[NeverFolia][NeverNether basalt columns] SELF-TEST OK")


def main() -> None:
    if len(sys.argv) == 2 and sys.argv[1] == "--self-test":
        self_test()
        return
    if len(sys.argv) != 2:
        fail("usage: apply-never-nether-basalt-columns-ownership.py /path/to/.work/Folia | --self-test")
    folia = Path(sys.argv[1]).resolve()
    target = folia / REL
    if not target.is_file():
        fail(f"BasaltColumnsFeature source not found: {target}")
    source = target.read_text(encoding="utf-8")
    patched = patch_source(source)
    target.write_text(patched, encoding="utf-8")
    print("[NeverFolia][NeverNether basalt columns] chunk-ownership hook applied")
    print(f"  target: {target}")


if __name__ == "__main__":
    main()
