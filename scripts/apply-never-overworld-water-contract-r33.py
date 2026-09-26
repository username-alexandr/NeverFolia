#!/usr/bin/env python3
"""FIELD-R33: preserve vanilla aquifer water and cap custom ocean flood depth.

The flooded-world overlay must not erase vanilla aquifer WATER and then try to
reconstruct it. R33 keeps native WATER intact, removes only generated LAVA, and
allows NeverFolia's synthetic ocean flood/seam handoff to create new WATER only
at Y>=96. Below that line vanilla aquifers remain authoritative.
"""
from __future__ import annotations
import argparse
from pathlib import Path

JAVA = Path("folia-server/src/minecraft/java")
OWNER = JAVA / "net/minecraft/world/level/chunk/NeverOverworldFlood.java"
R15 = JAVA / "net/minecraft/world/level/chunk/NeverOverworldFloodConnectivityR15.java"

OWNER_CONST = "    private static final int CUSTOM_FLOOD_MIN_Y = 96;\n"
R15_CONST = "    static final int CUSTOM_FLOOD_MIN_Y = 96;\n"

def fail(message: str) -> None:
    raise ValueError("[FIELD-R33] " + message)

def method_bounds(text: str, signature: str) -> tuple[int, int]:
    start = text.find(signature)
    if start < 0:
        fail("method signature missing: " + signature)
    brace = text.find("{", start)
    if brace < 0:
        fail("method opening brace missing: " + signature)
    depth = 0
    in_string = False
    escaped = False
    i = brace
    while i < len(text):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            i += 1
            continue
        if ch == '"':
            in_string = True
            i += 1
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return start, i + 1
        i += 1
    fail("unterminated method: " + signature)

LAVA_ONLY_CLEANUP = """    /**
     * R33: preserve every native/vanilla WATER decision. The flooded overlay
     * owns only the synthetic upper ocean; generated lava is still removed.
     */
    private static void removeGeneratedFluids(
        final ChunkAccess chunk,
        final int minY,
        final int maxY,
        final BlockState air
    ) {
        final int minSectionY = SectionPos.blockToSectionCoord(minY);
        final int maxSectionY = SectionPos.blockToSectionCoord(maxY);
        final LevelChunkSection[] sections = chunk.getSections();
        final ChunkPos chunkPos = chunk.getPos();
        final int minX = chunkPos.getMinBlockX();
        final int minZ = chunkPos.getMinBlockZ();
        final BlockPos.MutableBlockPos pos = new BlockPos.MutableBlockPos();

        for (int sectionY = minSectionY; sectionY <= maxSectionY; ++sectionY) {
            final int sectionIndex = chunk.getSectionIndexFromSectionY(sectionY);
            if (sectionIndex < 0 || sectionIndex >= sections.length) {
                continue;
            }
            final LevelChunkSection section = sections[sectionIndex];
            if (!section.maybeHas(state -> state.is(Blocks.LAVA))) {
                continue;
            }

            final int sectionMinY = SectionPos.sectionToBlockCoord(sectionY);
            final int scanMinY = Math.max(minY, sectionMinY);
            final int scanMaxY = Math.min(maxY, sectionMinY + 15);
            for (int y = scanMinY; y <= scanMaxY; ++y) {
                final int localY = SectionPos.sectionRelative(y);
                for (int localZ = 0; localZ < 16; ++localZ) {
                    for (int localX = 0; localX < 16; ++localX) {
                        final BlockState state = section.getBlockState(localX, localY, localZ);
                        if (!state.is(Blocks.LAVA)) {
                            continue;
                        }
                        pos.set(minX + localX, y, minZ + localZ);
                        chunk.setBlockState(pos, air, 0);
                    }
                }
            }
        }
    }"""

def replace_cleanup_method(text: str) -> str:
    start, end = method_bounds(text, "    private static void removeGeneratedFluids(")
    return text[:start] + LAVA_ONLY_CLEANUP + text[end:]

def patch_owner(text: str) -> str:
    if OWNER_CONST not in text:
        anchor = "    private static final int FLOOD_LEVEL = 128;\n"
        if text.count(anchor) != 1:
            fail("owner FLOOD_LEVEL anchor missing/duplicated")
        text = text.replace(anchor, anchor + OWNER_CONST, 1)

    if "R33: preserve every native/vanilla WATER decision" not in text:
        text = replace_cleanup_method(text)

    # Do not create synthetic flood below the hydraulic overlay depth.
    bounds_old = "y < minY || y > maxY"
    bounds_new = "y < Math.max(minY, CUSTOM_FLOOD_MIN_Y) || y > maxY"
    text = text.replace(bounds_old, bounds_new)

    write = "            chunk.setBlockState(pos, water, 0);\n"
    guarded = (
        "            if (y < CUSTOM_FLOOD_MIN_Y) {\n"
        "                continue;\n"
        "            }\n"
        + write
    )
    # The final owner helper has two custom flood write paths after the
    # historical transforms. Gate every unguarded write; do not assume one
    # exact source anchor.
    while write in text:
        pos = text.find(write)
        prefix = text[max(0, pos - 160):pos]
        if "if (y < CUSTOM_FLOOD_MIN_Y)" in prefix:
            # This occurrence is already guarded; skip past it by temporarily
            # marking only the write line and restore after the loop.
            text = text[:pos] + "            /* R33_GUARDED_WATER_WRITE */\n" + text[pos + len(write):]
            continue
        text = text[:pos] + guarded + text[pos + len(write):]
    text = text.replace("            /* R33_GUARDED_WATER_WRITE */\n", write)

    return text

def patch_r15(text: str) -> str:
    if R15_CONST not in text:
        anchor = "    static final int SCAN_MAX_Y = 128;\n"
        if text.count(anchor) != 1:
            fail("R15 SCAN_MAX_Y anchor missing/duplicated")
        text = text.replace(anchor, anchor + R15_CONST, 1)

    # Every custom connectivity scan/handoff uses the same lower limit.
    text = text.replace("Math.max(SCAN_MIN_Y,", "Math.max(CUSTOM_FLOOD_MIN_Y,")

    # Older compact helper can still compare y against method minY.
    text = text.replace(
        "y < minY || y > maxY",
        "y < Math.max(minY, CUSTOM_FLOOD_MIN_Y) || y > maxY"
    )

    # Do not inject neighbour water below the custom-flood band.
    text = text.replace(
        "for (int y = minY; y < SCAN_MAX_Y; ++y)",
        "for (int y = Math.max(minY, CUSTOM_FLOOD_MIN_Y); y < SCAN_MAX_Y; ++y)"
    )

    # R24's drain pass can delete legitimate vanilla aquifer flow. R33 never
    # drains existing WATER; unverified components are simply left unchanged.
    drain_old = "            if(allowSeams){\n                boolean hasFlowingWater=false;"
    drain_new = "            if(false && allowSeams){\n                boolean hasFlowingWater=false;"
    if drain_old in text:
        text = text.replace(drain_old, drain_new, 1)

    return text

def verify(owner: str, r15: str) -> None:
    if OWNER_CONST not in owner:
        fail("owner custom-flood lower bound missing")
    if "R33: preserve every native/vanilla WATER decision" not in owner:
        fail("owner lava-only cleanup method missing")
    start, end = method_bounds(owner, "    private static void removeGeneratedFluids(")
    cleanup = owner[start:end]
    if "state.is(Blocks.WATER)" in cleanup:
        fail("owner cleanup still references WATER")
    if "state.is(Blocks.LAVA)" not in cleanup:
        fail("owner cleanup lost LAVA filter")
    if "y < CUSTOM_FLOOD_MIN_Y" not in owner:
        fail("owner final water write is not depth-gated")

    for marker in (
        "CUSTOM_FLOOD_MIN_Y = 96",
        "Math.max(CUSTOM_FLOOD_MIN_Y,",
        "false && allowSeams",
    ):
        if marker not in r15:
            fail("R15 missing marker: " + marker)
    if "for (int y = minY; y < SCAN_MAX_Y; ++y)" in r15:
        fail("R15 neighbour handoff still reaches deep caves")

def self_test() -> None:
    owner = """class NeverOverworldFlood {
    private static final int FLOOD_LEVEL = 128;
    private static void removeGeneratedFluids(
        final ChunkAccess chunk, final int minY, final int maxY, final BlockState air
    ) {
        if (!state.is(Blocks.WATER) && !state.is(Blocks.LAVA)) { return; }
    }
    void flood(int y,int minY,int maxY) {
        if (y < minY || y > maxY) return;
        pos.set(0,y,0);
            chunk.setBlockState(pos, water, 0);
    }
}
"""
    r15 = """class NeverOverworldFloodConnectivityR15 {
    static final int SCAN_MIN_Y = -64;
    static final int SCAN_MAX_Y = 128;
    void x(int minY,int maxY) {
        int q=Math.max(SCAN_MIN_Y,0);
        for (int y = minY; y < SCAN_MAX_Y; ++y) {}
        if (y < minY || y > maxY) return;
        if(!hasOceanSeed){
            if(allowSeams){
                boolean hasFlowingWater=false;
            }
        }
    }
}
"""
    po = patch_owner(owner)
    pr = patch_r15(r15)
    verify(po, pr)
    if patch_owner(po) != po or patch_r15(pr) != pr:
        fail("transform is not idempotent")
    print("[FIELD-R33] SELF-TEST OK")

def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("folia", nargs="?", type=Path)
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--check-only", action="store_true")
    a = p.parse_args()

    if a.self_test:
        self_test()
        return
    if a.folia is None:
        p.error("folia worktree is required")

    owner_path = a.folia.resolve() / OWNER
    r15_path = a.folia.resolve() / R15
    if not owner_path.is_file() or not r15_path.is_file():
        fail("materialized flood sources missing")

    owner = owner_path.read_text(encoding="utf-8")
    r15 = r15_path.read_text(encoding="utf-8")
    if a.check_only:
        verify(owner, r15)
        print("[FIELD-R33] final aquifer-preserving flood invariants OK")
        return

    self_test()
    owner = patch_owner(owner)
    r15 = patch_r15(r15)
    verify(owner, r15)
    owner_path.write_text(owner, encoding="utf-8")
    r15_path.write_text(r15, encoding="utf-8")
    print("[FIELD-R33] installed: vanilla WATER preserved; custom flood Y>=96")

if __name__ == "__main__":
    main()
