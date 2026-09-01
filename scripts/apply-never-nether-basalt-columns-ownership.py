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
        + f"ChunkPos neverNetherOwner = isNeverNether(context.level()) ? new ChunkPos({origin}) : null;"
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

    signature_pattern = re.compile(
        r"private\s+boolean\s+placeColumn\("
        r"LevelAccessor\s+(?P<level>[A-Za-z_$][A-Za-z0-9_$]*)\s*,\s*"
        r"int\s+(?P<sea>[A-Za-z_$][A-Za-z0-9_$]*)\s*,\s*"
        r"BlockPos\s+(?P<origin>[A-Za-z_$][A-Za-z0-9_$]*)\s*,\s*"
        r"int\s+(?P<height>[A-Za-z_$][A-Za-z0-9_$]*)\s*,\s*"
        r"int\s+(?P<reach>[A-Za-z_$][A-Za-z0-9_$]*)\s*\)"
    )
    sig_matches = list(signature_pattern.finditer(source))
    if len(sig_matches) != 1:
        fail(f"expected exactly one placeColumn signature, got {len(sig_matches)}")
    m = sig_matches[0]
    replacement = (
        "private boolean placeColumn("
        f"LevelAccessor {m.group('level')}, int {m.group('sea')}, BlockPos {m.group('origin')}, "
        f"int {m.group('height')}, int {m.group('reach')}, ChunkPos neverNetherOwner)"
    )
    source = source[: m.start()] + replacement + source[m.end() :]

    # Guard every candidate before findSurface/findAir reads it. This is critical:
    # clipping only setBlock would still allow cross-chunk mutable reads to affect
    # the decision tree and therefore would not establish order independence.
    loop_pattern = re.compile(
        r"(?P<indent>^[ \t]*)(?:[A-Za-z_$][A-Za-z0-9_$]*:\s*)?for\s*\(BlockPos\s+(?P<pos>[A-Za-z_$][A-Za-z0-9_$]*)\s*:\s*BlockPos\.betweenClosed\([^\n]+\)\)\s*\{",
        re.MULTILINE,
    )
    loop_matches = list(loop_pattern.finditer(source))
    if len(loop_matches) != 1:
        fail(f"expected exactly one placeColumn betweenClosed loop, got {len(loop_matches)}")
    m = loop_matches[0]
    loop_indent = m.group("indent")
    pos = m.group("pos")
    guarded_loop = (
        m.group(0)
        + "\n"
        + loop_indent
        + "    if (neverNetherOwner != null && !isOwnedBy(neverNetherOwner, "
        + pos
        + ")) {\n"
        + loop_indent
        + "        continue;\n"
        + loop_indent
        + "    }"
    )
    source = source[: m.start()] + guarded_loop + source[m.end() :]

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
    private boolean placeColumn(LevelAccessor level, int lavaSeaLevel, BlockPos origin, int columnHeight, int reach) {
        block0: for (BlockPos pos : BlockPos.betweenClosed(origin.getX() - reach, origin.getY(), origin.getZ() - reach, origin.getX() + reach, origin.getY(), origin.getZ() + reach)) {
            BlockPos columnPos = null;
        }
        return false;
    }
    private static boolean isAirOrLavaOcean(LevelAccessor level, int lavaSeaLevel, BlockPos blockPos) { return false; }
}
'''
    patched = patch_source(fixture)
    assert "ChunkPos neverNetherOwner" in patched
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
