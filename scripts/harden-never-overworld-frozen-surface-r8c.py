#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

HELPER_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldFlood.java")
OLD_LOOP = '''                    if (isDrownedSurfaceOverlay(original)) {
                        continue;
                    }
'''
NEW_LOOP = '''                    if (isDrownedFrozenOverlay(original)) {
                        chunk.setBlockState(pos, Blocks.WATER.defaultBlockState(), 0);
                        continue;
                    }

                    if (isDrownedSurfaceOverlay(original)) {
                        continue;
                    }
'''
METHOD_ANCHOR = '''    private static boolean isDrownedSurfaceOverlay(final BlockState state) {
'''
FROZEN_METHOD = '''    /**
     * R8-C: former snowy/frozen land below the new Y=128 ocean must not persist
     * as white caps inside deep water. Melt only natural frozen surface states
     * encountered by the existing drowned-column scan, then continue downward
     * until the real substrate can be weathered. This runs during generation
     * only and never touches blocks after a chunk has been generated.
     */
    private static boolean isDrownedFrozenOverlay(final BlockState state) {
        return state.is(Blocks.SNOW)
            || state.is(Blocks.SNOW_BLOCK)
            || state.is(Blocks.POWDER_SNOW)
            || state.is(Blocks.ICE)
            || state.is(Blocks.PACKED_ICE)
            || state.is(Blocks.BLUE_ICE);
    }

'''


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][NeverOverworld frozen surface R8-C] {message}")


def patch_source(source: str) -> str:
    if "isDrownedFrozenOverlay" in source:
        required = (
            "Blocks.SNOW",
            "Blocks.SNOW_BLOCK",
            "Blocks.POWDER_SNOW",
            "Blocks.ICE",
            "Blocks.PACKED_ICE",
            "Blocks.BLUE_ICE",
            "chunk.setBlockState(pos, Blocks.WATER.defaultBlockState(), 0)",
        )
        missing = [marker for marker in required if marker not in source]
        if missing:
            fail(f"R8-C appears partially applied; missing {missing}")
        return source

    if source.count(OLD_LOOP) != 1:
        fail(f"expected one drowned overlay loop anchor, got {source.count(OLD_LOOP)}")
    if source.count(METHOD_ANCHOR) != 1:
        fail(f"expected one drowned overlay method anchor, got {source.count(METHOD_ANCHOR)}")
    if "// NEVERFOLIA: drowned surface weathering" not in source:
        fail("drowned surface weathering must be applied before R8-C")

    out = source.replace(OLD_LOOP, NEW_LOOP, 1)
    out = out.replace(METHOD_ANCHOR, FROZEN_METHOD + METHOD_ANCHOR, 1)

    for marker in (
        "isDrownedFrozenOverlay(original)",
        "Blocks.SNOW",
        "Blocks.SNOW_BLOCK",
        "Blocks.POWDER_SNOW",
        "Blocks.ICE",
        "Blocks.PACKED_ICE",
        "Blocks.BLUE_ICE",
        "Blocks.WATER.defaultBlockState()",
    ):
        if marker not in out:
            fail(f"patched helper missing {marker!r}")
    return out


def self_test() -> None:
    fixture = '''class NeverOverworldFlood {
    // NEVERFOLIA: drowned surface weathering
    void weather(ChunkAccess chunk, BlockPos.MutableBlockPos pos, BlockState original) {
                    if (isDrownedSurfaceOverlay(original)) {
                        continue;
                    }
    }
    private static boolean isDrownedSurfaceOverlay(final BlockState state) {
        return state.isAir();
    }
}
'''
    out = patch_source(fixture)
    if out.count("isDrownedFrozenOverlay(original)") != 1:
        fail("SELF-TEST: frozen overlay check count drifted")
    if out.index("isDrownedFrozenOverlay(original)") > out.index("isDrownedSurfaceOverlay(original)"):
        fail("SELF-TEST: frozen remnants must be melted before generic overlay skip")
    if out.count("Blocks.WATER.defaultBlockState()") != 1:
        fail("SELF-TEST: frozen overlay does not become source water")
    again = patch_source(out)
    if again != out:
        fail("SELF-TEST: transformer is not idempotent")
    print("[NeverFolia][NeverOverworld frozen surface R8-C] SELF-TEST OK")
    print("  melts: snow layer, snow block, powder snow, ice, packed ice, blue ice")
    print("  scope: existing drowned-column scan only; no extra chunk pass")


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
        fail(f"NeverOverworldFlood helper missing: {helper}")
    helper.write_text(patch_source(helper.read_text(encoding="utf-8")), encoding="utf-8")
    print("[NeverFolia][NeverOverworld frozen surface R8-C] drowned frozen remnants cleanup applied")
    print(f"  helper: {helper}")


if __name__ == "__main__":
    main()
