#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path

ORE_FEATURE_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/levelgen/feature/OreFeature.java")
MARKER = "NeverFolia: preserve original vanilla 26.2 resource-ore write bounds"
RESOURCE_HELPER = "neverfolia$isVanillaResourceOre"
WORLD_HELPER = "neverfolia$isExtendedNeverOverworld"


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][NeverOverworld vanilla ore write bounds] {message}")


def matching(source: str, start: int, opening: str, closing: str) -> int:
    if start < 0 or start >= len(source) or source[start] != opening:
        fail(f"expected {opening!r} at index {start}")
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
            in_string = True
            i += 1
            continue
        if ch == "'":
            in_char = True
            i += 1
            continue
        if ch == "/" and nxt == "/":
            newline = source.find("\n", i + 2)
            i = len(source) if newline < 0 else newline + 1
            continue
        if ch == "/" and nxt == "*":
            end = source.find("*/", i + 2)
            if end < 0:
                fail("unterminated Java block comment")
            i = end + 2
            continue
        if ch == opening:
            depth += 1
        elif ch == closing:
            depth -= 1
            if depth == 0:
                return i
        i += 1
    fail(f"unterminated delimiter {opening}{closing}")


def patch_source(source: str) -> str:
    if MARKER in source or RESOURCE_HELPER in source or WORLD_HELPER in source:
        fail("OreFeature is already patched for NeverOverworld vanilla ore write bounds")

    method = re.search(r"\b(?:protected|public|private)\s+boolean\s+doPlace\s*\(", source)
    if method is None:
        fail("OreFeature.doPlace(...) not found")
    params_open = source.find("(", method.start(), method.end())
    params_close = matching(source, params_open, "(", ")")
    params = source[params_open + 1 : params_close]
    level_match = re.search(r"\bWorldGenLevel\s+(\w+)\b", params)
    config_match = re.search(r"\bOreConfiguration\s+(\w+)\b", params)
    if level_match is None or config_match is None:
        fail("could not resolve WorldGenLevel/OreConfiguration parameter names in doPlace")
    level = level_match.group(1)
    config = config_match.group(1)

    cursor = params_close + 1
    while cursor < len(source) and source[cursor].isspace():
        cursor += 1
    if cursor >= len(source) or source[cursor] != "{":
        fail("OreFeature.doPlace body opening brace not found")
    body_open = cursor
    body_close = matching(source, body_open, "{", "}")
    body = source[body_open + 1 : body_close]

    calls = list(re.finditer(rf"!\s*{re.escape(level)}\.isOutsideBuildHeight\s*\(\s*(\w+)\s*\)", body))
    if len(calls) != 1:
        fail(f"expected exactly one !{level}.isOutsideBuildHeight(y) guard in doPlace, got {len(calls)}")
    call = calls[0]
    y = call.group(1)
    original = call.group(0)
    replacement = (
        f"{original}\n"
        f"                        // {MARKER}.\n"
        f"                        && (!{WORLD_HELPER}({level})\n"
        f"                            || !{RESOURCE_HELPER}({config})\n"
        f"                            || ({y} >= -64 && {y} <= 319))"
    )
    patched_body = body[: call.start()] + replacement + body[call.end() :]
    patched = source[: body_open + 1] + patched_body + source[body_close:]

    class_close = patched.rfind("}")
    if class_close < 0:
        fail("OreFeature class closing brace not found")
    helper = f'''\n    private static boolean {WORLD_HELPER}(final WorldGenLevel level) {{
        return level.getLevel().dimension().equals(net.minecraft.world.level.Level.OVERWORLD)
            && level.getMinY() == -512
            && level.getHeight() == 1024;
    }}

    private static boolean {RESOURCE_HELPER}(final OreConfiguration config) {{
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

    for required in (
        MARKER,
        f"{WORLD_HELPER}({level})",
        f"{RESOURCE_HELPER}({config})",
        f"{y} >= -64 && {y} <= 319",
        "Blocks.DEEPSLATE_DIAMOND_ORE",
        "Blocks.DEEPSLATE_EMERALD_ORE",
    ):
        if required not in patched:
            fail(f"patched source missing {required!r}")
    if patched.count(MARKER) != 1:
        fail("write-bounds marker was not injected exactly once")
    return patched


def self_test() -> None:
    fixture = '''package test;
class OreFeature {
    protected boolean doPlace(WorldGenLevel level, RandomSource random, OreConfiguration config, double x0, int yStart) {
        for (int y = yStart; y < yStart + 10; ++y) {
            if (1.0D < 2.0D && !level.isOutsideBuildHeight(y)) {
                return true;
            }
        }
        return false;
    }
}
'''
    patched = patch_source(fixture)
    for required in (
        MARKER,
        "!level.isOutsideBuildHeight(y)",
        f"!{WORLD_HELPER}(level)",
        f"!{RESOURCE_HELPER}(config)",
        "y >= -64 && y <= 319",
        "level.getMinY() == -512",
        "level.getHeight() == 1024",
        "Blocks.DEEPSLATE_DIAMOND_ORE",
        "Blocks.DEEPSLATE_EMERALD_ORE",
    ):
        if required not in patched:
            fail(f"SELF-TEST: missing {required!r}")
    if "deep_tuff" in patched:
        fail("SELF-TEST: resource filter must not special-case material geology")
    print("[NeverFolia][NeverOverworld vanilla ore write bounds] STRUCTURAL SELF-TEST OK")
    print("  vanilla resource ore writes restricted to original Y=-64..319 only in extended NR overworld")
    print("  non-resource OreFeature placements remain allowed across the extended dimension")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Preserve vanilla 26.2 resource-ore build-bound rejection after NeverOverworld height extension"
    )
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
    print("[NeverFolia][NeverOverworld vanilla ore write bounds] ORIGINAL 26.2 WRITE BOUNDS RESTORED")
    print("  resource ore write Y: -64..319")
    print("  extended NeverOverworld Y: -512..511")
    print(f"  source: {path}")


if __name__ == "__main__":
    main()
