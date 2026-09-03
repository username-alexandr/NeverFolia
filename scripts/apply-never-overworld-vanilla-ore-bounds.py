#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path

ORE_FEATURE_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/levelgen/feature/OreFeature.java")
MARKER = "NeverFolia: preserve vanilla 26.2 resource-ore bounds"
HELPER = "neverfolia$isVanillaResourceOre"


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][NeverOverworld vanilla ore bounds] {message}")


def matching(source: str, start: int, opening: str, closing: str) -> int:
    depth = 0
    in_string = False
    in_char = False
    escaped = False
    i = start
    while i < len(source):
        ch = source[i]
        nxt = source[i + 1] if i + 1 < len(source) else ""
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            i += 1
            continue
        if in_char:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == "'":
                in_char = False
            i += 1
            continue
        if ch == '"':
            in_string = True; i += 1; continue
        if ch == "'":
            in_char = True; i += 1; continue
        if ch == "/" and nxt == "/":
            nl = source.find("\n", i + 2)
            i = len(source) if nl < 0 else nl + 1
            continue
        if ch == "/" and nxt == "*":
            end = source.find("*/", i + 2)
            if end < 0: fail("unterminated block comment")
            i = end + 2
            continue
        if ch == opening:
            depth += 1
        elif ch == closing:
            depth -= 1
            if depth == 0:
                return i
        i += 1
    fail(f"unterminated {opening}{closing}")


def patch_source(source: str) -> str:
    if MARKER in source or HELPER in source:
        fail("OreFeature is already patched")

    method = re.search(
        r"public\s+boolean\s+place\s*\(\s*FeaturePlaceContext\s*<\s*OreConfiguration\s*>\s+(\w+)\s*\)\s*\{",
        source,
    )
    if method is None:
        fail("OreFeature.place(FeaturePlaceContext<OreConfiguration>) not found")
    context = method.group(1)
    body_open = source.find("{", method.start(), method.end())
    line_start = source.rfind("\n", 0, body_open) + 1
    indent_match = re.match(r"[ \t]*", source[line_start:method.start()])
    method_indent = indent_match.group(0) if indent_match else "   "
    indent = method_indent + "   "

    guard = (
        "\n"
        f"{indent}// {MARKER}.\n"
        f"{indent}// Anchor normalization restores the original sampled Y values; this guard\n"
        f"{indent}// reproduces the old -64..319 build-bound rejection in the extended NR world.\n"
        f"{indent}final var neverfoliaLevel = {context}.level();\n"
        f"{indent}final int neverfoliaY = {context}.origin().getY();\n"
        f"{indent}if (neverfoliaLevel.getLevel().dimension().equals(net.minecraft.world.level.Level.OVERWORLD)\n"
        f"{indent}    && neverfoliaLevel.getMinY() == -512\n"
        f"{indent}    && neverfoliaLevel.getHeight() == 1024\n"
        f"{indent}    && (neverfoliaY < -64 || neverfoliaY > 319)\n"
        f"{indent}    && {HELPER}({context}.config())) {{\n"
        f"{indent}   return false;\n"
        f"{indent}}}\n"
    )
    patched = source[: body_open + 1] + guard + source[body_open + 1 :]

    class_close = patched.rfind("}")
    if class_close < 0:
        fail("OreFeature class closing brace not found")
    helper = f'''\n   private static boolean {HELPER}(final OreConfiguration config) {{
      for (final OreConfiguration.TargetBlockState target : config.targetStates) {{
         final var state = target.state;
         if (state.is(net.minecraft.world.level.block.Blocks.COAL_ORE)
            || state.is(net.minecraft.world.level.block.Blocks.DEEPSLATE_COAL_ORE)
            || state.is(net.minecraft.world.level.block.Blocks.IRON_ORE)
            || state.is(net.minecraft.world.level.block.Blocks.DEEPSLATE_IRON_ORE)
            || state.is(net.minecraft.world.level.block.Blocks.COPPER_ORE)
            || state.is(net.minecraft.world.level.block.Blocks.DEEPSLATE_COPPER_ORE)
            || state.is(net.minecraft.world.level.block.Blocks.GOLD_ORE)
            || state.is(net.minecraft.world.level.block.Blocks.DEEPSLATE_GOLD_ORE)
            || state.is(net.minecraft.world.level.block.Blocks.REDSTONE_ORE)
            || state.is(net.minecraft.world.level.block.Blocks.DEEPSLATE_REDSTONE_ORE)
            || state.is(net.minecraft.world.level.block.Blocks.LAPIS_ORE)
            || state.is(net.minecraft.world.level.block.Blocks.DEEPSLATE_LAPIS_ORE)
            || state.is(net.minecraft.world.level.block.Blocks.DIAMOND_ORE)
            || state.is(net.minecraft.world.level.block.Blocks.DEEPSLATE_DIAMOND_ORE)
            || state.is(net.minecraft.world.level.block.Blocks.EMERALD_ORE)
            || state.is(net.minecraft.world.level.block.Blocks.DEEPSLATE_EMERALD_ORE)) {{
            return true;
         }}
      }}
      return false;
   }}
'''
    patched = patched[:class_close] + helper + patched[class_close:]
    if patched.count(MARKER) != 1 or patched.count(f"boolean {HELPER}") != 1:
        fail("patch markers were not written exactly once")
    return patched


def self_test() -> None:
    fixture = '''package test;
class OreFeature {
   public boolean place(FeaturePlaceContext<OreConfiguration> context) {
      return true;
   }
}
'''
    patched = patch_source(fixture)
    for required in (
        MARKER,
        "neverfoliaLevel.getMinY() == -512",
        "neverfoliaLevel.getHeight() == 1024",
        "neverfoliaY < -64 || neverfoliaY > 319",
        "Blocks.DEEPSLATE_DIAMOND_ORE",
        "Blocks.DEEPSLATE_EMERALD_ORE",
        f"{HELPER}(context.config())",
    ):
        if required not in patched:
            fail(f"SELF-TEST: missing {required!r}")
    if patched.index("return false;") > patched.index("return true;"):
        fail("SELF-TEST: bounds guard was not inserted before original placement body")
    print("[NeverFolia][NeverOverworld vanilla ore bounds] STRUCTURAL SELF-TEST OK")


def main() -> None:
    parser = argparse.ArgumentParser(description="Restore original vanilla OreFeature build-bound rejection inside extended NeverOverworld")
    parser.add_argument("folia", nargs="?", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if args.folia is None:
        parser.error("folia worktree path is required unless --self-test is used")
    path = args.folia.resolve() / ORE_FEATURE_REL
    if not path.is_file():
        fail(f"OreFeature source not found: {path}")
    path.write_text(patch_source(path.read_text(encoding="utf-8")), encoding="utf-8")
    print("[NeverFolia][NeverOverworld vanilla ore bounds] original vanilla resource-ore bounds guard applied")
    print(f"  source: {path}")


if __name__ == "__main__":
    main()
