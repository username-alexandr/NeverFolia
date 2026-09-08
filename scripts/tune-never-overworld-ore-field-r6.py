#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

HELPER_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldOreGeology.java")

V3 = {
    "COAL": "        COAL(0x07A8B9C0D1E2F314L, 48, 0.70D, 0.12D, -256, DEEP_MAX_Y, 26.0D, 60.0D, 1.7D, 3.2D, 0.68D, 0.65D, Blocks.COAL_ORE, Blocks.DEEPSLATE_COAL_ORE),",
    "IRON": "        IRON(0x11A2B3C4D5E6F701L, 64, 0.41D, 0.20D, -480, DEEP_MAX_Y, 28.0D, 72.0D, 1.5D, 3.0D, 0.70D, 0.84D, Blocks.IRON_ORE, Blocks.DEEPSLATE_IRON_ORE),",
    "COPPER": "        COPPER(0x22B3C4D5E6F70112L, 56, 0.63D, 0.20D, -300, DEEP_MAX_Y, 22.0D, 56.0D, 1.8D, 3.4D, 0.62D, 0.80D, Blocks.COPPER_ORE, Blocks.DEEPSLATE_COPPER_ORE),",
    "GOLD": "        GOLD(0x33C4D5E6F7011223L, 48, 0.66D, 0.32D, -420, -128, 16.0D, 44.0D, 1.2D, 2.2D, 0.58D, 0.72D, Blocks.GOLD_ORE, Blocks.DEEPSLATE_GOLD_ORE),",
    "REDSTONE": "        REDSTONE(0x44D5E6F701122334L, 48, 0.47D, 0.26D, -480, -160, 20.0D, 54.0D, 1.0D, 1.9D, 0.52D, 0.70D, Blocks.REDSTONE_ORE, Blocks.DEEPSLATE_REDSTONE_ORE),",
    "LAPIS": "        LAPIS(0x55E6F70112233445L, 48, 0.52D, 0.28D, -360, -128, 12.0D, 30.0D, 1.0D, 2.0D, 0.46D, 0.74D, Blocks.LAPIS_ORE, Blocks.DEEPSLATE_LAPIS_ORE),",
    "DIAMOND": "        DIAMOND(0x66F7011223344556L, 48, 0.48D, 0.25D, -496, -160, 18.0D, 44.0D, 0.90D, 1.50D, 0.42D, 0.64D, Blocks.DIAMOND_ORE, Blocks.DEEPSLATE_DIAMOND_ORE),",
}

R6 = {
    "COAL": V3["COAL"].replace(", 0.70D, 0.12D,", ", 0.55D, 0.12D,"),
    "IRON": V3["IRON"].replace(", 0.41D, 0.20D,", ", 0.32D, 0.20D,"),
    "COPPER": V3["COPPER"].replace(", 0.63D, 0.20D,", ", 0.50D, 0.20D,"),
    "GOLD": V3["GOLD"].replace(", 0.66D, 0.32D,", ", 0.52D, 0.32D,"),
    "REDSTONE": V3["REDSTONE"].replace(", 0.47D, 0.26D,", ", 0.37D, 0.26D,"),
    "LAPIS": V3["LAPIS"].replace(", 0.52D, 0.28D,", ", 0.41D, 0.28D,"),
    "DIAMOND": V3["DIAMOND"].replace(", 0.48D, 0.25D,", ", 0.38D, 0.25D,"),
}


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][NeverOverworld ore field-r6] {message}")


def patch(source: str) -> str:
    out = source
    for kind in V3:
        old, new = V3[kind], R6[kind]
        if out.count(new) == 1 and out.count(old) == 0:
            continue
        if out.count(old) != 1:
            fail(f"expected exactly one v3 {kind} entry, got {out.count(old)}")
        out = out.replace(old, new, 1)
    for kind, line in R6.items():
        if out.count(line) != 1:
            fail(f"R6 {kind} entry missing after patch")
    return out


def self_test() -> None:
    fixture = "class X { enum OreKind {\n" + "\n".join(V3.values()) + "\n}}"
    out = patch(fixture)
    for kind in R6:
        if R6[kind] not in out:
            fail(f"SELF-TEST: {kind} missing")
    ratios = {"COAL":0.55/0.70,"IRON":0.32/0.41,"COPPER":0.50/0.63,"GOLD":0.52/0.66,"REDSTONE":0.37/0.47,"LAPIS":0.41/0.52,"DIAMOND":0.38/0.48}
    if not all(0.77 <= r <= 0.80 for r in ratios.values()):
        fail(f"SELF-TEST: frequency reduction drifted: {ratios}")
    print("[NeverFolia][NeverOverworld ore field-r6] SELF-TEST OK", ratios)


def main() -> None:
    parser=argparse.ArgumentParser()
    parser.add_argument("folia",nargs="?",type=Path)
    parser.add_argument("--self-test",action="store_true")
    args=parser.parse_args()
    if args.self_test:
        self_test(); return
    if args.folia is None:
        parser.error("folia worktree path is required")
    self_test()
    helper=args.folia.resolve()/HELPER_REL
    if not helper.is_file():
        fail(f"helper missing: {helper}")
    helper.write_text(patch(helper.read_text(encoding="utf-8")),encoding="utf-8")
    print("[NeverFolia][NeverOverworld ore field-r6] buried deep ore frequency reduced")


if __name__ == "__main__":
    main()
