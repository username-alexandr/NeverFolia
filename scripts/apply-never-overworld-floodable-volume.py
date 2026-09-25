#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

HELPER_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldFlood.java")
OLD_GUARD = "if (!chunk.getBlockState(pos).isAir()) {"
NEW_GUARD = "if (!isFloodable(chunk.getBlockState(pos))) {"
ENCODE_ANCHOR = "    private static int encode(final int localX, final int y, final int localZ, final int minY) {\n"
FLOODABLE_METHOD = '''    /**
     * Flood air and dry replaceable worldgen decoration, but never erase an
     * existing fluid/waterlogged state. This makes the result independent from
     * whether a radius-1 FEATURES write (for example leaf litter) reaches the
     * owning chunk immediately before or immediately after its LIGHT task.
     */
    private static boolean isFloodable(final BlockState state) {
        return state.isAir() || (state.getFluidState().isEmpty() && state.canBeReplaced());
    }

'''


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][NeverOverworld floodable volume] {message}")


def patch_helper(source: str) -> str:
    if "state.getFluidState().isEmpty() && state.canBeReplaced()" in source:
        fail("NeverOverworldFlood is already patched for floodable volume")
    if "public final class NeverOverworldFlood" not in source:
        fail("NeverOverworldFlood class marker not found")

    guard_count = source.count(OLD_GUARD)
    if guard_count != 3:
        fail(f"expected exactly 3 air-only BFS guards, got {guard_count}")
    if source.count(ENCODE_ANCHOR) != 1:
        fail("expected exactly one encode() insertion anchor")
    if source.count("floodSurfaceConnectedAir") != 2:
        fail("expected floodSurfaceConnectedAir call + declaration")
    if source.count("enqueueAir") != 7:
        fail("expected six enqueueAir calls + declaration")

    patched = source.replace("floodSurfaceConnectedAir", "floodSurfaceConnectedVolume")
    patched = patched.replace("enqueueAir", "enqueueFloodable")
    patched = patched.replace(OLD_GUARD, NEW_GUARD)
    patched = patched.replace(ENCODE_ANCHOR, FLOODABLE_METHOD + ENCODE_ANCHOR, 1)
    patched = patched.replace(
        "BFS follows air inside the owning chunk only.",
        "BFS follows air and dry replaceable decoration inside the owning chunk only.",
    )

    for required in (
        "floodSurfaceConnectedVolume",
        "enqueueFloodable",
        "private static boolean isFloodable(final BlockState state)",
        "state.getFluidState().isEmpty()",
        "state.canBeReplaced()",
    ):
        if required not in patched:
            fail(f"patched helper missing {required!r}")
    if patched.count(NEW_GUARD) != 3:
        fail("patched helper must contain exactly three floodable BFS guards")
    for forbidden in ("floodSurfaceConnectedAir", "enqueueAir", OLD_GUARD):
        if forbidden in patched:
            fail(f"obsolete air-only marker remains: {forbidden!r}")
    return patched


def self_test() -> None:
    fixture = '''public final class NeverOverworldFlood {
    void apply() { floodSurfaceConnectedAir(chunk, minY, maxY, water); }
    private static void floodSurfaceConnectedAir(Object chunk, int minY, int maxY, Object water) {
        if (!chunk.getBlockState(pos).isAir()) {
            return;
        }
        if (!chunk.getBlockState(pos).isAir()) {
            return;
        }
        enqueueAir(); enqueueAir(); enqueueAir(); enqueueAir(); enqueueAir(); enqueueAir();
    }
    private static int enqueueAir() {
        if (!chunk.getBlockState(pos).isAir()) {
            return 0;
        }
        return 1;
    }
    private static int encode(final int localX, final int y, final int localZ, final int minY) {
        return 0;
    }
}
'''
    patched = patch_helper(fixture)
    if patched.count("isFloodable(chunk.getBlockState(pos))") != 3:
        fail("SELF-TEST: floodable guards were not rewritten exactly three times")
    if "state.getFluidState().isEmpty() && state.canBeReplaced()" not in patched:
        fail("SELF-TEST: safe replaceable predicate missing")
    print("[NeverFolia][NeverOverworld floodable volume] SELF-TEST OK")


def main() -> None:
    parser = argparse.ArgumentParser(description="Make NeverOverworld flood replace dry replaceable worldgen decoration deterministically")
    parser.add_argument("folia", nargs="?", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if args.folia is None:
        parser.error("folia worktree path is required unless --self-test is used")

    # Run the structural fixture before touching the materialized source.
    self_test()
    helper = args.folia.resolve() / HELPER_REL
    if not helper.is_file():
        fail(f"NeverOverworldFlood helper not found: {helper}")
    helper.write_text(patch_helper(helper.read_text(encoding="utf-8")), encoding="utf-8")
    print("[NeverFolia][NeverOverworld floodable volume] deterministic replaceable-volume semantics applied")
    print(f"  helper: {helper}")


if __name__ == "__main__":
    main()
