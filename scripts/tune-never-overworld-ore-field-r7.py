#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

HELPER_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldOreGeology.java")

R6 = {
    "COAL": "        COAL(0x07A8B9C0D1E2F314L, 48, 0.71D, 0.12D, -256, DEEP_MAX_Y, 26.0D, 60.0D, 1.7D, 3.2D, 0.68D, 0.65D, Blocks.COAL_ORE, Blocks.DEEPSLATE_COAL_ORE),",
    "IRON": "        IRON(0x11A2B3C4D5E6F701L, 64, 0.35D, 0.20D, -480, DEEP_MAX_Y, 28.0D, 72.0D, 1.5D, 3.0D, 0.70D, 0.84D, Blocks.IRON_ORE, Blocks.DEEPSLATE_IRON_ORE),",
    "COPPER": "        COPPER(0x22B3C4D5E6F70112L, 56, 0.58D, 0.20D, -300, DEEP_MAX_Y, 22.0D, 56.0D, 1.8D, 3.4D, 0.62D, 0.80D, Blocks.COPPER_ORE, Blocks.DEEPSLATE_COPPER_ORE),",
    "GOLD": "        GOLD(0x33C4D5E6F7011223L, 48, 0.65D, 0.32D, -420, -128, 16.0D, 44.0D, 1.2D, 2.2D, 0.58D, 0.72D, Blocks.GOLD_ORE, Blocks.DEEPSLATE_GOLD_ORE),",
    "REDSTONE": "        REDSTONE(0x44D5E6F701122334L, 48, 0.44D, 0.26D, -480, -160, 20.0D, 54.0D, 1.0D, 1.9D, 0.52D, 0.70D, Blocks.REDSTONE_ORE, Blocks.DEEPSLATE_REDSTONE_ORE),",
    "LAPIS": "        LAPIS(0x55E6F70112233445L, 48, 0.46D, 0.28D, -360, -128, 12.0D, 30.0D, 1.0D, 2.0D, 0.46D, 0.74D, Blocks.LAPIS_ORE, Blocks.DEEPSLATE_LAPIS_ORE),",
    "DIAMOND": "        DIAMOND(0x66F7011223344556L, 48, 0.39D, 0.25D, -496, -160, 18.0D, 44.0D, 0.90D, 1.50D, 0.42D, 0.64D, Blocks.DIAMOND_ORE, Blocks.DEEPSLATE_DIAMOND_ORE),",
}

# Field-R7 is intentionally below the old ~vanilla total-density target.
# Player field screenshots showed ore walls/readability far above the desired
# flooded-world scarcity even though the aggregate FULL-chunk ratio passed.
# Keep salts, cell sizes, geometry and fill unchanged; only lower candidate
# frequency so buried deep deposits become scarcer while preserving shape.
R7 = {
    "COAL": R6["COAL"].replace(", 0.71D, 0.12D,", ", 0.60D, 0.12D,"),
    "IRON": R6["IRON"].replace(", 0.35D, 0.20D,", ", 0.32D, 0.20D,"),
    "COPPER": R6["COPPER"].replace(", 0.58D, 0.20D,", ", 0.46D, 0.20D,"),
    "GOLD": R6["GOLD"].replace(", 0.65D, 0.32D,", ", 0.52D, 0.32D,"),
    "REDSTONE": R6["REDSTONE"].replace(", 0.44D, 0.26D,", ", 0.38D, 0.26D,"),
    "LAPIS": R6["LAPIS"].replace(", 0.46D, 0.28D,", ", 0.39D, 0.28D,"),
    "DIAMOND": R6["DIAMOND"].replace(", 0.39D, 0.25D,", ", 0.31D, 0.25D,"),
}


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][NeverOverworld ore field-r7] {message}")


def patch(source: str) -> str:
    out = source
    for kind in R6:
        old, new = R6[kind], R7[kind]
        if out.count(new) == 1 and out.count(old) == 0:
            continue
        if out.count(old) != 1:
            fail(f"expected exactly one R6 {kind} entry, got {out.count(old)}")
        out = out.replace(old, new, 1)
    for kind, line in R7.items():
        if out.count(line) != 1:
            fail(f"R7 {kind} entry missing after patch")
    return out


def self_test() -> None:
    fixture = "class X { enum OreKind {\n" + "\n".join(R6.values()) + "\n}}"
    out = patch(fixture)
    for kind in R7:
        if R7[kind] not in out:
            fail(f"SELF-TEST: {kind} missing")
    scales = {
        "COAL": 0.60 / 0.71,
        "IRON": 0.32 / 0.35,
        "COPPER": 0.46 / 0.58,
        "GOLD": 0.52 / 0.65,
        "REDSTONE": 0.38 / 0.44,
        "LAPIS": 0.39 / 0.46,
        "DIAMOND": 0.31 / 0.39,
    }
    if not all(0.75 <= scale <= 0.93 for scale in scales.values()):
        fail(f"SELF-TEST: R7 frequency scale drifted: {scales}")
    if not (scales["DIAMOND"] < 0.82 and scales["COPPER"] < 0.82 and scales["GOLD"] <= 0.80):
        fail("SELF-TEST: screenshot-heavy valuable ores are not reduced enough")
    print("[NeverFolia][NeverOverworld ore field-r7] SELF-TEST OK", scales)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("folia", nargs="?", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if args.folia is None:
        parser.error("folia worktree path is required")
    self_test()
    helper = args.folia.resolve() / HELPER_REL
    if not helper.is_file():
        fail(f"helper missing: {helper}")
    helper.write_text(patch(helper.read_text(encoding="utf-8")), encoding="utf-8")
    print("[NeverFolia][NeverOverworld ore field-r7] screenshot-driven buried deep ore scarcity applied")
    print("  frequency scales vs R6: coal=.845 iron=.914 copper=.793 gold=.800 redstone=.864 lapis=.848 diamond=.795")


if __name__ == "__main__":
    main()
