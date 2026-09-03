#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

HELPER_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldOreGeology.java")

# Input state is the established native geology after coal/emerald extension and
# diamond/emerald balance v2. v3 deliberately keeps the deterministic salts and
# chunk-ownership model unchanged and only tunes deposit geometry/frequency.
OLD = {
    "COAL": "        COAL(0x07A8B9C0D1E2F314L, 120, 0.48D, 0.24D, -256, DEEP_MAX_Y, 32.0D, 88.0D, 1.8D, 3.6D, 0.68D, 0.82D, Blocks.COAL_ORE, Blocks.DEEPSLATE_COAL_ORE),",
    "IRON": "        IRON(0x11A2B3C4D5E6F701L, 96, 0.58D, 0.28D, -480, DEEP_MAX_Y, 36.0D, 96.0D, 1.8D, 3.8D, 0.70D, 0.86D, Blocks.IRON_ORE, Blocks.DEEPSLATE_IRON_ORE),",
    "COPPER": "        COPPER(0x22B3C4D5E6F70112L, 112, 0.42D, 0.35D, -300, DEEP_MAX_Y, 28.0D, 72.0D, 2.0D, 4.0D, 0.62D, 0.80D, Blocks.COPPER_ORE, Blocks.DEEPSLATE_COPPER_ORE),",
    "GOLD": "        GOLD(0x33C4D5E6F7011223L, 128, 0.24D, 0.50D, -420, -128, 20.0D, 56.0D, 1.2D, 2.4D, 0.58D, 0.72D, Blocks.GOLD_ORE, Blocks.DEEPSLATE_GOLD_ORE),",
    "REDSTONE": "        REDSTONE(0x44D5E6F701122334L, 104, 0.40D, 0.35D, -480, -160, 30.0D, 80.0D, 1.2D, 2.3D, 0.52D, 0.72D, Blocks.REDSTONE_ORE, Blocks.DEEPSLATE_REDSTONE_ORE),",
    "LAPIS": "        LAPIS(0x55E6F70112233445L, 144, 0.18D, 0.52D, -360, -128, 16.0D, 40.0D, 1.4D, 2.8D, 0.46D, 0.75D, Blocks.LAPIS_ORE, Blocks.DEEPSLATE_LAPIS_ORE),",
    "DIAMOND": "        DIAMOND(0x66F7011223344556L, 112, 0.20D, 0.50D, -496, -160, 14.0D, 36.0D, 0.85D, 1.55D, 0.42D, 0.62D, Blocks.DIAMOND_ORE, Blocks.DEEPSLATE_DIAMOND_ORE),",
    "EMERALD": "        EMERALD(0x77A8122334455667L, 144, 0.12D, 0.62D, -384, -96, 8.0D, 24.0D, 0.70D, 1.20D, 0.42D, 0.50D, Blocks.EMERALD_ORE, Blocks.DEEPSLATE_EMERALD_ORE);",
}

# Calibrated first pass from persisted FULL-chunk measurements.
# True vanilla 26.2 reference (230 FULL chunks, seed NeverOverworld-CI-Test-1):
# coal 88.07, iron 69.92, copper 74.21, gold 32.10, redstone 34.99,
# lapis 21.80 and diamond 23.91 ore blocks / FULL chunk.
#
# The NeverOverworld deposits remain province/vein based rather than copying
# vanilla CountPlacement. A later persisted runtime gate measures the result and
# is authoritative; these parameters are intentionally only the first fit.
NEW = {
    "COAL": "        COAL(0x07A8B9C0D1E2F314L, 80, 0.65D, 0.14D, -256, DEEP_MAX_Y, 40.0D, 100.0D, 2.8D, 5.2D, 0.68D, 0.84D, Blocks.COAL_ORE, Blocks.DEEPSLATE_COAL_ORE),",
    "IRON": "        IRON(0x11A2B3C4D5E6F701L, 96, 0.70D, 0.24D, -480, DEEP_MAX_Y, 36.0D, 96.0D, 1.8D, 3.8D, 0.70D, 0.86D, Blocks.IRON_ORE, Blocks.DEEPSLATE_IRON_ORE),",
    "COPPER": "        COPPER(0x22B3C4D5E6F70112L, 80, 0.62D, 0.24D, -300, DEEP_MAX_Y, 28.0D, 72.0D, 2.5D, 4.8D, 0.62D, 0.82D, Blocks.COPPER_ORE, Blocks.DEEPSLATE_COPPER_ORE),",
    "GOLD": "        GOLD(0x33C4D5E6F7011223L, 72, 0.48D, 0.38D, -420, -128, 20.0D, 56.0D, 1.6D, 2.8D, 0.58D, 0.74D, Blocks.GOLD_ORE, Blocks.DEEPSLATE_GOLD_ORE),",
    "REDSTONE": "        REDSTONE(0x44D5E6F701122334L, 104, 0.32D, 0.35D, -480, -160, 30.0D, 80.0D, 1.2D, 2.3D, 0.52D, 0.72D, Blocks.REDSTONE_ORE, Blocks.DEEPSLATE_REDSTONE_ORE),",
    "LAPIS": "        LAPIS(0x55E6F70112233445L, 128, 0.24D, 0.52D, -360, -128, 16.0D, 40.0D, 1.4D, 2.8D, 0.46D, 0.75D, Blocks.LAPIS_ORE, Blocks.DEEPSLATE_LAPIS_ORE),",
    "DIAMOND": "        DIAMOND(0x66F7011223344556L, 104, 0.25D, 0.50D, -496, -160, 14.0D, 36.0D, 0.85D, 1.55D, 0.42D, 0.62D, Blocks.DIAMOND_ORE, Blocks.DEEPSLATE_DIAMOND_ORE),",
    # Vanilla emerald is biome-specific and the deterministic reference sample
    # contains no mountain emerald. Preserve the proven sparse native deep value
    # instead of inventing an all-biome vanilla target.
    "EMERALD": OLD["EMERALD"],
}

TARGET_BLOCKS_PER_FULL_CHUNK = {
    "coal": 88.065217,
    "iron": 69.917391,
    "copper": 74.208696,
    "gold": 32.095652,
    "redstone": 34.986957,
    "lapis": 21.804348,
    "diamond": 23.913043,
}


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][NeverOverworld ore balance v3] {message}")


def patch_helper(source: str) -> str:
    for kind, new_entry in NEW.items():
        old_entry = OLD[kind]
        if new_entry != old_entry and new_entry in source:
            fail(f"ore balance v3 is already applied for {kind}")
        if source.count(old_entry) != 1:
            fail(f"expected exactly one v2 {kind} entry, got {source.count(old_entry)}")

    patched = source
    for kind in OLD:
        if NEW[kind] != OLD[kind]:
            patched = patched.replace(OLD[kind], NEW[kind], 1)

    for kind, entry in NEW.items():
        if patched.count(entry) != 1:
            fail(f"patched helper does not contain exactly one v3 {kind} entry")
    return patched


def self_test() -> None:
    fixture = "class NeverOverworldOreGeology {\n    private enum OreKind {\n" + "\n".join(OLD.values()) + "\n    }\n}\n"
    patched = patch_helper(fixture)
    for kind, entry in NEW.items():
        if patched.count(entry) != 1:
            fail(f"SELF-TEST: {kind} v3 entry missing")
    if NEW["EMERALD"] != OLD["EMERALD"]:
        fail("SELF-TEST: emerald must remain on the proven sparse v2 setting")
    for kind, target in TARGET_BLOCKS_PER_FULL_CHUNK.items():
        if target <= 0.0:
            fail(f"SELF-TEST: invalid vanilla target for {kind}")
    print("[NeverFolia][NeverOverworld ore balance v3] VANILLA-LIKE ALL-ORE SELF-TEST OK")
    print("  targets blocks/FULL-chunk:", TARGET_BLOCKS_PER_FULL_CHUNK)


def main() -> None:
    parser = argparse.ArgumentParser(description="Tune NR-DEV-1 native deep ores toward measured vanilla 26.2 FULL-chunk density")
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
    print("[NeverFolia][NeverOverworld ore balance v3] vanilla-like deep ore calibration applied")
    print(f"  helper: {helper}")
    print("  measured vanilla targets: coal=88.07 iron=69.92 copper=74.21 gold=32.10 redstone=34.99 lapis=21.80 diamond=23.91")


if __name__ == "__main__":
    main()
