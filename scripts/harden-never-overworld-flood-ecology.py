#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

HELPER_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldFlood.java")
WEATHER_SCRIPT = Path(__file__).with_name("weather-never-overworld-flooded-surface.py")
OLD = "return state.isAir() || (state.getFluidState().isEmpty() && state.canBeReplaced());"
NEW = '''return state.isAir()
            || (state.getFluidState().isEmpty() && state.canBeReplaced())
            || state.is(net.minecraft.tags.BlockTags.LOGS)
            || state.is(net.minecraft.tags.BlockTags.LEAVES)
            || state.is(net.minecraft.tags.BlockTags.RAILS)
            || state.is(net.minecraft.world.level.block.Blocks.SUGAR_CANE)
            || state.is(net.minecraft.world.level.block.Blocks.LILY_PAD)
            || state.is(net.minecraft.world.level.block.Blocks.MUSHROOM_STEM)
            || state.is(net.minecraft.world.level.block.Blocks.RED_MUSHROOM_BLOCK)
            || state.is(net.minecraft.world.level.block.Blocks.BROWN_MUSHROOM_BLOCK);'''


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][NeverOverworld flood ecology] {message}")


def load_weather_module():
    if not WEATHER_SCRIPT.is_file():
        fail(f"drowned-surface weathering transformer not found: {WEATHER_SCRIPT}")
    spec = importlib.util.spec_from_file_location("never_overworld_drowned_surface", WEATHER_SCRIPT)
    if spec is None or spec.loader is None:
        fail("could not load drowned-surface weathering transformer")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
        "Blocks.MUSHROOM_STEM",
        "Blocks.RED_MUSHROOM_BLOCK",
        "Blocks.BROWN_MUSHROOM_BLOCK",
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
    for marker in (
        "BlockTags.RAILS",
        "Blocks.SUGAR_CANE",
        "Blocks.LILY_PAD",
        "Blocks.MUSHROOM_STEM",
        "Blocks.RED_MUSHROOM_BLOCK",
        "Blocks.BROWN_MUSHROOM_BLOCK",
    ):
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

    text = patch_source(path.read_text(encoding="utf-8"))

    # R4: the same LIGHT-barrier pass now also ages the former land surface.
    # Keeping this chained to the existing ecology transformer guarantees the
    # new behaviour is applied by every existing build/QA workflow without a
    # second shell-level patch hook.
    weather = load_weather_module()
    weather.self_test()
    text = weather.patch_source(text)

    path.write_text(text, encoding="utf-8")
    print("[NeverFolia][NeverOverworld flood ecology] flooded vegetation/rail cleanup applied")
    print("  removes submerged logs, leaves, rails, cane, lily pads and giant mushroom blocks")
    print("  R4 drowned surface: living topsoil is weathered into sediment/mineral patches")
    print(f"  helper: {path}")


if __name__ == "__main__":
    main()
