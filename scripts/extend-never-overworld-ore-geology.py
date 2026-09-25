#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path

HELPER_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldOreGeology.java")
COAL_MARKER = "COAL(0x07A8B9C0D1E2F314L"
EMERALD_MARKER = "EMERALD(0x77A8122334455667L"


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][NeverOverworld geology v2] {message}")


def patch_helper(source: str) -> str:
    if COAL_MARKER in source or EMERALD_MARKER in source:
        fail("native geology helper is already extended with coal/emerald")
    if "private enum OreKind" not in source:
        fail("OreKind enum not found in native geology helper")

    iron_anchor = "    private enum OreKind {\n        IRON("
    if source.count(iron_anchor) != 1:
        fail("expected one OreKind/IRON anchor")
    coal = (
        "    private enum OreKind {\n"
        "        COAL(0x07A8B9C0D1E2F314L, 120, 0.48D, 0.24D, -256, DEEP_MAX_Y, "
        "32.0D, 88.0D, 1.8D, 3.6D, 0.68D, 0.82D, Blocks.COAL_ORE, Blocks.DEEPSLATE_COAL_ORE),\n"
        "        IRON("
    )
    patched = source.replace(iron_anchor, coal, 1)

    diamond = re.compile(
        r"(?m)^(?P<indent>\s*)DIAMOND\((?P<body>[^\n]*Blocks\.DIAMOND_ORE,\s*Blocks\.DEEPSLATE_DIAMOND_ORE)\);$"
    )
    matches = list(diamond.finditer(patched))
    if len(matches) != 1:
        fail(f"expected exactly one DIAMOND enum entry, got {len(matches)}")
    m = matches[0]
    emerald = (
        f"{m.group('indent')}DIAMOND({m.group('body')}),\n"
        f"{m.group('indent')}EMERALD(0x77A8122334455667L, 192, 0.075D, 0.72D, -360, -128, "
        "10.0D, 26.0D, 0.70D, 1.25D, 0.42D, 0.46D, Blocks.EMERALD_ORE, Blocks.DEEPSLATE_EMERALD_ORE);"
    )
    patched = patched[: m.start()] + emerald + patched[m.end() :]

    for marker in (
        COAL_MARKER,
        EMERALD_MARKER,
        "Blocks.DEEPSLATE_COAL_ORE",
        "Blocks.DEEPSLATE_EMERALD_ORE",
    ):
        if marker not in patched:
            fail(f"patched helper missing {marker!r}")
    return patched


def self_test() -> None:
    fixture = '''class NeverOverworldOreGeology {
    private static final int DEEP_MAX_Y = -96;
    private enum OreKind {
        IRON(0x11A2B3C4D5E6F701L, 96, 0.58D, 0.28D, -480, DEEP_MAX_Y, 36.0D, 96.0D, 1.8D, 3.8D, 0.70D, 0.86D, Blocks.IRON_ORE, Blocks.DEEPSLATE_IRON_ORE),
        DIAMOND(0x66F7011223344556L, 160, 0.10D, 0.64D, -480, -180, 14.0D, 34.0D, 0.8D, 1.45D, 0.40D, 0.58D, Blocks.DIAMOND_ORE, Blocks.DEEPSLATE_DIAMOND_ORE);
    }
}
'''
    patched = patch_helper(fixture)
    if patched.count("COAL(") != 1 or patched.count("EMERALD(") != 1:
        fail("SELF-TEST: coal/emerald entries were not injected exactly once")
    if "DIAMOND(" not in patched or "DIAMOND_ORE)," not in patched:
        fail("SELF-TEST: diamond entry did not remain before emerald")
    print("[NeverFolia][NeverOverworld geology v2] COAL + EMERALD EXTENSION SELF-TEST OK")


def main() -> None:
    parser = argparse.ArgumentParser(description="Extend NR-DEV-1 native ore geology with coal and emerald provinces")
    parser.add_argument("folia", nargs="?", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if args.folia is None:
        parser.error("folia worktree path is required unless --self-test is used")

    helper = args.folia.resolve() / HELPER_REL
    if not helper.is_file():
        fail(f"native geology helper not found: {helper}")
    helper.write_text(patch_helper(helper.read_text(encoding="utf-8")), encoding="utf-8")
    print("[NeverFolia][NeverOverworld geology v2] coal + emerald province veins applied")
    print(f"  helper: {helper}")


if __name__ == "__main__":
    main()
