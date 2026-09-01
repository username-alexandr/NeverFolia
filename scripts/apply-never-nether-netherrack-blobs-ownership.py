#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from pathlib import Path

REL = Path(
    "folia-server/src/minecraft/java/net/minecraft/world/level/levelgen/feature/ReplaceBlobsFeature.java"
)


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][NeverNether replace blobs] {message}")


def matching_brace(source: str, open_brace: int) -> int:
    depth = 0
    in_string = False
    escaped = False
    for index in range(open_brace, len(source)):
        ch = source[index]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return index
    fail("unterminated Java block")


def matching_paren(source: str, open_paren: int) -> int:
    depth = 0
    for index in range(open_paren, len(source)):
        ch = source[index]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return index
    fail("unterminated Java call")


def split_top_level_args(text: str) -> list[str]:
    args: list[str] = []
    start = 0
    paren = bracket = brace = angle = 0
    for index, ch in enumerate(text):
        if ch == "(":
            paren += 1
        elif ch == ")":
            paren -= 1
        elif ch == "[":
            bracket += 1
        elif ch == "]":
            bracket -= 1
        elif ch == "{":
            brace += 1
        elif ch == "}":
            brace -= 1
        elif ch == "<":
            angle += 1
        elif ch == ">" and angle:
            angle -= 1
        elif ch == "," and paren == bracket == brace == angle == 0:
            args.append(text[start:index].strip())
            start = index + 1
    args.append(text[start:].strip())
    return args


def patch_source(source: str) -> str:
    marker = "NeverNether: keep ReplaceBlobsFeature writes inside the generating chunk"
    if marker in source:
        fail("ReplaceBlobsFeature is already patched")

    if "class ReplaceBlobsFeature" not in source:
        fail("ReplaceBlobsFeature class declaration not found")

    place_match = re.search(
        r"\bboolean\s+place\s*\([^)]*\)\s*\{",
        source,
        re.DOTALL,
    )
    if place_match is None:
        fail("place(...) method not found")
    method_open = source.find("{", place_match.start(), place_match.end())
    method_close = matching_brace(source, method_open)
    method = source[method_open + 1 : method_close]

    level_match = re.search(
        r"(?P<indent>^[ \t]*)WorldGenLevel\s+(?P<level>[A-Za-z_$][A-Za-z0-9_$]*)\s*=\s*context\.level\(\);",
        method,
        re.MULTILINE,
    )
    if level_match is None:
        fail("context.level() assignment not found in place method")
    indent = level_match.group("indent")
    level = level_match.group("level")
    owner_decl = (
        level_match.group(0)
        + "\n"
        + indent
        + "// NeverNether: keep ReplaceBlobsFeature writes inside the generating chunk.\n"
        + indent
        + "net.minecraft.world.level.ChunkPos neverNetherOwner = "
        + f"isNeverNether({level}) ? new net.minecraft.world.level.ChunkPos("
        + "context.origin().getX() >> 4, context.origin().getZ() >> 4) : null;"
    )
    method = method[: level_match.start()] + owner_decl + method[level_match.end() :]

    call_token = "this.setBlock("
    positions: list[tuple[int, int, str]] = []
    search_from = 0
    while True:
        start = method.find(call_token, search_from)
        if start < 0:
            break
        open_paren = start + len("this.setBlock")
        close_paren = matching_paren(method, open_paren)
        semicolon = close_paren + 1
        while semicolon < len(method) and method[semicolon].isspace():
            semicolon += 1
        if semicolon >= len(method) or method[semicolon] != ";":
            fail("setBlock call is not followed by semicolon")
        args = split_top_level_args(method[open_paren + 1 : close_paren])
        if len(args) < 2:
            fail(f"setBlock call has too few arguments: {args!r}")
        positions.append((start, semicolon + 1, args[1]))
        search_from = semicolon + 1

    if len(positions) != 1:
        fail(f"expected exactly one this.setBlock call in place method, got {len(positions)}")

    start, end, pos_expr = positions[0]
    line_start = method.rfind("\n", 0, start) + 1
    prefix = method[line_start:start]
    indent_match = re.match(r"[ \t]*", prefix)
    call_indent = indent_match.group(0) if indent_match else ""
    original = method[start:end]
    wrapped = (
        f"if (neverNetherOwner == null || isOwnedBy(neverNetherOwner, {pos_expr})) {{\n"
        + call_indent
        + "    "
        + original
        + "\n"
        + call_indent
        + "}"
    )
    method = method[:start] + wrapped + method[end:]
    source = source[: method_open + 1] + method + source[method_close:]

    class_close = source.rfind("}")
    if class_close < 0:
        fail("class closing brace not found")
    helpers = '''
   private static boolean isNeverNether(WorldGenLevel level) {
      return level.getMinY() == -128 && level.getHeight() == 1024;
   }

   private static boolean isOwnedBy(net.minecraft.world.level.ChunkPos owner, BlockPos pos) {
      return (pos.getX() >> 4) == owner.x() && (pos.getZ() >> 4) == owner.z();
   }

'''
    source = source[:class_close] + helpers + source[class_close:]
    return source


def self_test() -> None:
    # Mirrors Minecraft 26.2 Mojmap structure closely enough that source-shape
    # drift in the real class is detected before the expensive Folia build.
    fixture = '''package net.minecraft.world.level.levelgen.feature;
import net.minecraft.core.BlockPos;
import net.minecraft.world.level.WorldGenLevel;
public class ReplaceBlobsFeature extends Feature<ReplaceSphereConfiguration> {
   @Override
   public boolean place(final FeaturePlaceContext<ReplaceSphereConfiguration> context) {
      ReplaceSphereConfiguration config = context.config();
      WorldGenLevel level = context.level();
      RandomSource random = context.random();
      Block targetBlock = config.targetState.getBlock();
      BlockPos centerPos = findTarget(level, context.origin().mutable(), targetBlock);
      if (centerPos == null) {
         return false;
      } else {
         for (BlockPos pos : BlockPos.withinManhattan(centerPos, 3, 3, 3)) {
            BlockState blockState = level.getBlockState(pos);
            if (blockState.is(targetBlock)) {
               this.setBlock(level, pos, config.replaceState);
            }
         }
         return true;
      }
   }
}
'''
    patched = patch_source(fixture)
    assert "ChunkPos neverNetherOwner" in patched
    assert "new net.minecraft.world.level.ChunkPos(context.origin().getX() >> 4, context.origin().getZ() >> 4)" in patched
    assert "if (neverNetherOwner == null || isOwnedBy(neverNetherOwner, pos))" in patched
    assert "level.getMinY() == -128 && level.getHeight() == 1024" in patched
    assert patched.count("this.setBlock(") == 1
    print("[NeverFolia][NeverNether replace blobs] SELF-TEST OK")


def main() -> None:
    if len(sys.argv) == 2 and sys.argv[1] == "--self-test":
        self_test()
        return
    if len(sys.argv) != 2:
        fail("usage: apply-never-nether-netherrack-blobs-ownership.py /path/to/.work/Folia | --self-test")
    folia = Path(sys.argv[1]).resolve()
    target = folia / REL
    if not target.is_file():
        fail(f"ReplaceBlobsFeature source not found: {target}")
    source = target.read_text(encoding="utf-8")
    patched = patch_source(source)
    target.write_text(patched, encoding="utf-8")
    print("[NeverFolia][NeverNether replace blobs] chunk-ownership hook applied")
    print(f"  target: {target}")


if __name__ == "__main__":
    main()
