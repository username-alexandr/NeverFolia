#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

HELPER_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldOreGeology.java")
PREFLIGHT = Path(__file__).with_name("preflight-never-overworld-native-ore-geometry.py")
COST_PREFLIGHT = Path(__file__).with_name("preflight-never-overworld-ore-cost.py")

# Input state is the established native geology after coal/emerald extension and
# diamond/emerald balance v2. v3 keeps deterministic salts and chunk ownership
# unchanged; only deposit geometry/frequency is tuned.
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

# Native-only recalibration after restoring original vanilla 26.2 placed-feature
# anchors/write bounds. Earlier persisted deep totals were partially contaminated
# by vanilla resource ores whose relative height anchors shifted into NR's
# extended -512..511 dimension, so they are not a valid native-density baseline.
#
# Clean true-vanilla 26.2 reference (230 common FULL chunks, seed
# NeverOverworld-CI-Test-1): coal 88.07, iron 69.92, copper 74.21, gold 32.10,
# redstone 34.99, lapis 21.80, diamond 23.91 blocks/FULL chunk.
#
# Runtime calibration on candidate b6b0195 measured native/vanilla ratios:
# coal 0.529, iron 1.061, copper 0.899, gold 0.593, redstone 0.923,
# lapis 1.342, diamond 1.340. Candidate 9f33d6f then measured:
# coal 1.198, iron 1.063, copper 0.898, gold 0.873, redstone 0.922,
# lapis 0.917, diamond 0.950.
#
# After field-r1 integration, authoritative full candidate a8946ac measured
# coal 1.201 and iron 1.212 while every other calibrated ore remained inside
# the preferred 0.85..1.15 band. This micro-pass therefore adjusts only the
# candidate gate frequency of coal and iron. Coal moves 0.79 -> 0.70; because
# its high-province chance was partially capped at 0.98 this targets ~1.08x
# rather than a pure linear 1.06x estimate. Iron is uncapped and moves
# 0.46 -> 0.41, targeting ~1.08x. Geometry, salts, fills and ownership stay
# unchanged.
NEW = {
    "COAL": "        COAL(0x07A8B9C0D1E2F314L, 48, 0.70D, 0.12D, -256, DEEP_MAX_Y, 26.0D, 60.0D, 1.7D, 3.2D, 0.68D, 0.65D, Blocks.COAL_ORE, Blocks.DEEPSLATE_COAL_ORE),",
    "IRON": "        IRON(0x11A2B3C4D5E6F701L, 64, 0.41D, 0.20D, -480, DEEP_MAX_Y, 28.0D, 72.0D, 1.5D, 3.0D, 0.70D, 0.84D, Blocks.IRON_ORE, Blocks.DEEPSLATE_IRON_ORE),",
    "COPPER": "        COPPER(0x22B3C4D5E6F70112L, 56, 0.63D, 0.20D, -300, DEEP_MAX_Y, 22.0D, 56.0D, 1.8D, 3.4D, 0.62D, 0.80D, Blocks.COPPER_ORE, Blocks.DEEPSLATE_COPPER_ORE),",
    "GOLD": "        GOLD(0x33C4D5E6F7011223L, 48, 0.66D, 0.32D, -420, -128, 16.0D, 44.0D, 1.2D, 2.2D, 0.58D, 0.72D, Blocks.GOLD_ORE, Blocks.DEEPSLATE_GOLD_ORE),",
    "REDSTONE": "        REDSTONE(0x44D5E6F701122334L, 48, 0.47D, 0.26D, -480, -160, 20.0D, 54.0D, 1.0D, 1.9D, 0.52D, 0.70D, Blocks.REDSTONE_ORE, Blocks.DEEPSLATE_REDSTONE_ORE),",
    "LAPIS": "        LAPIS(0x55E6F70112233445L, 48, 0.52D, 0.28D, -360, -128, 12.0D, 30.0D, 1.0D, 2.0D, 0.46D, 0.74D, Blocks.LAPIS_ORE, Blocks.DEEPSLATE_LAPIS_ORE),",
    "DIAMOND": "        DIAMOND(0x66F7011223344556L, 48, 0.48D, 0.25D, -496, -160, 18.0D, 44.0D, 0.90D, 1.50D, 0.42D, 0.64D, Blocks.DIAMOND_ORE, Blocks.DEEPSLATE_DIAMOND_ORE),",
    # Vanilla emerald is biome-specific and the deterministic clean reference
    # sample contains no mountain emerald. Keep the proven sparse native deep
    # value instead of inventing an all-biome density target.
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
    if not all(", 48," in NEW[kind] for kind in ("COAL", "GOLD", "REDSTONE", "LAPIS", "DIAMOND")):
        fail("SELF-TEST: frequent deep ores drifted away from the 48-block cell calibration")
    for preflight in (PREFLIGHT, COST_PREFLIGHT):
        if not preflight.is_file():
            fail(f"SELF-TEST: ore preflight missing: {preflight}")
        subprocess.run([sys.executable, str(preflight), "--self-test"], check=True)
    print("[NeverFolia][NeverOverworld ore balance v3] NATIVE-ONLY VANILLA-LIKE SELF-TEST OK")
    print("  clean vanilla targets blocks/FULL-chunk:", TARGET_BLOCKS_PER_FULL_CHUNK)


def main() -> None:
    parser = argparse.ArgumentParser(description="Tune NR-DEV-1 native deep ores toward clean vanilla 26.2 FULL-chunk density")
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
    print("[NeverFolia][NeverOverworld ore balance v3] native-only vanilla-like deep ore calibration applied")
    print(f"  helper: {helper}")
    print("  clean vanilla targets: coal=88.07 iron=69.92 copper=74.21 gold=32.10 redstone=34.99 lapis=21.80 diamond=23.91")


if __name__ == "__main__":
    main()
