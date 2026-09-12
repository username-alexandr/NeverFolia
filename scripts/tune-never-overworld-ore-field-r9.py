#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path

GEOLOGY_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldOreGeology.java")
PRUNER_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldOreExposurePruner.java")

R9_CHANCE = {
    "COAL": "0.51D", "IRON": "0.27D", "COPPER": "0.39D", "GOLD": "0.44D",
    "REDSTONE": "0.32D", "LAPIS": "0.33D", "DIAMOND": "0.26D",
}
R9_PROFILES = {
    "COAL": (6, 55, 10), "IRON": (6, 60, 12), "COPPER": (5, 45, 8),
    "GOLD": (4, 45, 5), "REDSTONE": (4, 50, 5), "LAPIS": (3, 0, 0),
    "DIAMOND": (2, 0, 0), "EMERALD": (3, 40, 3),
}


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][R9 ore field] {message}")


def patch_geology(text: str) -> str:
    for kind, chance in R9_CHANCE.items():
        pattern = re.compile(rf"(?m)^(?P<prefix>\s*{kind}\([^,]+,\s*\d+,\s*)(?P<chance>[0-9.]+D)(?P<suffix>,[^\n]+)$")
        matches = list(pattern.finditer(text))
        if len(matches) != 1: fail(f"expected one {kind} geology entry, got {len(matches)}")
        m = matches[0]
        text = text[:m.start()] + m.group("prefix") + chance + m.group("suffix") + text[m.end():]
    return text


def patch_pruner(text: str) -> str:
    for kind, (deep, buried, exposed) in R9_PROFILES.items():
        pattern = re.compile(rf"(?m)^(?P<indent>\s*){kind}\((?P<salt>0x[0-9A-F]+L),\s*\d+,\s*\d+,\s*\d+\)(?P<tail>[,;])$")
        matches = list(pattern.finditer(text))
        if len(matches) != 1: fail(f"expected one {kind} pruner profile, got {len(matches)}")
        m = matches[0]
        replacement = f"{m.group('indent')}{kind}({m.group('salt')}, {deep}, {buried}, {exposed}){m.group('tail')}"
        text = text[:m.start()] + replacement + text[m.end():]
    return text


def validate(geology: str, pruner: str) -> None:
    for kind, chance in R9_CHANCE.items():
        if not re.search(rf"(?m)^\s*{kind}\([^,]+,\s*\d+,\s*{re.escape(chance)},", geology): fail(f"R9 geology chance missing for {kind}")
    if "LAPIS(0x66F7011223344556L, 3, 0, 0)" not in pruner: fail("upper lapis suppression missing")
    if "DIAMOND(0x77A8122334455667L, 2, 0, 0)" not in pruner: fail("upper diamond suppression missing")


def self_test() -> None:
    geology = '''enum OreKind {
        COAL(0x01L, 48, 0.60D, 0.12D, -256, -96, 1D, 2D, 1D, 2D, 1D, 1D, A, B),
        IRON(0x02L, 64, 0.32D, 0.20D, -480, -96, 1D, 2D, 1D, 2D, 1D, 1D, A, B),
        COPPER(0x03L, 56, 0.46D, 0.20D, -300, -96, 1D, 2D, 1D, 2D, 1D, 1D, A, B),
        GOLD(0x04L, 48, 0.52D, 0.32D, -420, -128, 1D, 2D, 1D, 2D, 1D, 1D, A, B),
        REDSTONE(0x05L, 48, 0.38D, 0.26D, -480, -160, 1D, 2D, 1D, 2D, 1D, 1D, A, B),
        LAPIS(0x06L, 48, 0.39D, 0.28D, -360, -128, 1D, 2D, 1D, 2D, 1D, 1D, A, B),
        DIAMOND(0x07L, 48, 0.31D, 0.25D, -496, -160, 1D, 2D, 1D, 2D, 1D, 1D, A, B);
}'''
    pruner = '''enum OreProfile {
        COAL(0x11A2B3C4D5E6F701L, 6, 85, 18),
        IRON(0x22B3C4D5E6F70112L, 6, 90, 20),
        COPPER(0x33C4D5E6F7011223L, 5, 75, 12),
        GOLD(0x44D5E6F701122334L, 4, 75, 8),
        REDSTONE(0x55E6F70112233445L, 4, 85, 8),
        LAPIS(0x66F7011223344556L, 3, 80, 6),
        DIAMOND(0x77A8122334455667L, 2, 70, 3),
        EMERALD(0x18B9233445566778L, 3, 80, 5);
}'''
    g = patch_geology(geology); p = patch_pruner(pruner); validate(g, p)
    if patch_geology(g) != g or patch_pruner(p) != p: fail("SELF-TEST: transformer is not idempotent")
    print("[NeverFolia][R9 ore field] SELF-TEST OK")


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("folia", nargs="?", type=Path); parser.add_argument("--self-test", action="store_true"); args = parser.parse_args()
    if args.self_test: self_test(); return
    if args.folia is None: parser.error("folia worktree path is required")
    self_test(); folia = args.folia.resolve(); geology_path = folia / GEOLOGY_REL; pruner_path = folia / PRUNER_REL
    if not geology_path.is_file(): fail(f"geology helper missing: {geology_path}")
    if not pruner_path.is_file(): fail(f"ore exposure pruner missing: {pruner_path}")
    geology = patch_geology(geology_path.read_text(encoding="utf-8")); pruner = patch_pruner(pruner_path.read_text(encoding="utf-8")); validate(geology, pruner)
    geology_path.write_text(geology, encoding="utf-8"); pruner_path.write_text(pruner, encoding="utf-8")
    print("[NeverFolia][R9 ore field] field scarcity applied")

if __name__ == "__main__": main()
