#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

HELPER_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldOreGeology.java")

OLD_DIAMOND = (
    "        DIAMOND(0x66F7011223344556L, 160, 0.10D, 0.64D, -480, -180, "
    "14.0D, 34.0D, 0.8D, 1.45D, 0.40D, 0.58D, Blocks.DIAMOND_ORE, Blocks.DEEPSLATE_DIAMOND_ORE),"
)
NEW_DIAMOND = (
    "        DIAMOND(0x66F7011223344556L, 112, 0.20D, 0.50D, -496, -160, "
    "14.0D, 36.0D, 0.85D, 1.55D, 0.42D, 0.62D, Blocks.DIAMOND_ORE, Blocks.DEEPSLATE_DIAMOND_ORE),"
)

OLD_EMERALD = (
    "        EMERALD(0x77A8122334455667L, 192, 0.075D, 0.72D, -360, -128, "
    "10.0D, 26.0D, 0.70D, 1.25D, 0.42D, 0.46D, Blocks.EMERALD_ORE, Blocks.DEEPSLATE_EMERALD_ORE);"
)
NEW_EMERALD = (
    "        EMERALD(0x77A8122334455667L, 144, 0.12D, 0.62D, -384, -96, "
    "8.0D, 24.0D, 0.70D, 1.20D, 0.42D, 0.50D, Blocks.EMERALD_ORE, Blocks.DEEPSLATE_EMERALD_ORE);"
)


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][NeverOverworld ore balance v2] {message}")


def patch_helper(source: str) -> str:
    if NEW_DIAMOND in source or NEW_EMERALD in source:
        fail("ore balance v2 is already applied")
    if source.count(OLD_DIAMOND) != 1:
        fail(f"expected exactly one baseline DIAMOND entry, got {source.count(OLD_DIAMOND)}")
    if source.count(OLD_EMERALD) != 1:
        fail(f"expected exactly one baseline EMERALD entry, got {source.count(OLD_EMERALD)}")

    patched = source.replace(OLD_DIAMOND, NEW_DIAMOND, 1)
    patched = patched.replace(OLD_EMERALD, NEW_EMERALD, 1)

    for marker in (
        NEW_DIAMOND,
        NEW_EMERALD,
        "Blocks.DIAMOND_ORE",
        "Blocks.DEEPSLATE_DIAMOND_ORE",
        "Blocks.EMERALD_ORE",
        "Blocks.DEEPSLATE_EMERALD_ORE",
        "current.is(Blocks.DEEPSLATE) || current.is(Blocks.TUFF)",
        "current.is(Blocks.STONE)",
    ):
        if marker not in patched:
            fail(f"patched helper missing {marker!r}")

    return patched


def self_test() -> None:
    fixture = f'''class NeverOverworldOreGeology {{
    private static BlockState replacementFor(BlockState current, OreKind kind) {{
        if (current.is(Blocks.DEEPSLATE) || current.is(Blocks.TUFF)) return kind.deepOre.defaultBlockState();
        if (current.is(Blocks.STONE)) return kind.stoneOre.defaultBlockState();
        return null;
    }}
    private enum OreKind {{
{OLD_DIAMOND}
{OLD_EMERALD}
    }}
}}
'''
    patched = patch_helper(fixture)
    if patched.count(NEW_DIAMOND) != 1 or patched.count(NEW_EMERALD) != 1:
        fail("SELF-TEST: tuned entries were not written exactly once")
    if OLD_DIAMOND in patched or OLD_EMERALD in patched:
        fail("SELF-TEST: baseline sparse entries survived")

    # Guard the intent from the old NeverRaft regression: diamonds must cover
    # the deepest playable geology and emerald must exist in native deep geology.
    if "-496, -160" not in NEW_DIAMOND:
        fail("SELF-TEST: diamond deep range changed unexpectedly")
    if "-384, -96" not in NEW_EMERALD:
        fail("SELF-TEST: emerald deep range changed unexpectedly")

    print("[NeverFolia][NeverOverworld ore balance v2] DIAMOND + EMERALD BALANCE SELF-TEST OK")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Tune NR-DEV-1 native deep diamond/emerald density while preserving deterministic chunk ownership"
    )
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
    print("[NeverFolia][NeverOverworld ore balance v2] deep diamond + emerald balance applied")
    print(f"  helper: {helper}")


if __name__ == "__main__":
    main()
