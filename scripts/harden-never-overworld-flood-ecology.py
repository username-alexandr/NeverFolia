#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

HELPER_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldFlood.java")
OLD = "return state.isAir() || (state.getFluidState().isEmpty() && state.canBeReplaced());"
NEW = '''return state.isAir()
            || (state.getFluidState().isEmpty() && state.canBeReplaced())
            || state.is(net.minecraft.tags.BlockTags.LOGS)
            || state.is(net.minecraft.tags.BlockTags.LEAVES)
            || state.is(net.minecraft.tags.BlockTags.RAILS)
            || state.is(net.minecraft.world.level.block.Blocks.SUGAR_CANE)
            || state.is(net.minecraft.world.level.block.Blocks.LILY_PAD);'''


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][NeverOverworld flood ecology] {message}")


def patch_source(source: str) -> str:
    if "BlockTags.RAILS" in source:
        fail("flood ecology cleanup is already applied")
    if source.count(OLD) != 1:
        fail(f"expected one floodable predicate, got {source.count(OLD)}")
    source = source.replace(OLD, NEW, 1)
    for marker in (
        "BlockTags.LOGS",
        "BlockTags.LEAVES",
        "BlockTags.RAILS",
        "Blocks.SUGAR_CANE",
        "Blocks.LILY_PAD",
    ):
        if marker not in source:
            fail(f"patched helper missing {marker}")
    return source


def self_test() -> None:
    fixture = '''public final class NeverOverworldFlood {
    private static boolean isFloodable(final BlockState state) {
        return state.isAir() || (state.getFluidState().isEmpty() && state.canBeReplaced());
    }
}
'''
    patched = patch_source(fixture)
    for marker in ("BlockTags.RAILS", "Blocks.SUGAR_CANE", "Blocks.LILY_PAD"):
        if patched.count(marker) != 1:
            fail(f"SELF-TEST: cleanup marker count drifted for {marker}")
    print("[NeverFolia][NeverOverworld flood ecology] SELF-TEST OK")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("folia", nargs="?", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if args.folia is None:
        parser.error("folia worktree is required unless --self-test is used")
    self_test()
    path = args.folia.resolve() / HELPER_REL
    if not path.is_file():
        fail(f"NeverOverworldFlood helper not found: {path}")
    path.write_text(patch_source(path.read_text(encoding="utf-8")), encoding="utf-8")
    print("[NeverFolia][NeverOverworld flood ecology] flooded vegetation/rail cleanup applied")
    print("  removes submerged logs, leaves, rails, sugar cane and lily pads")
    print(f"  helper: {path}")


if __name__ == "__main__":
    main()
