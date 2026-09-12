#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

HELPER_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldFlood.java")
APPLY_SIG = "    public static void apply(final WorldGenLevel level, final ChunkAccess chunk)"
METHOD_ANCHOR = "    private static void removeDeepPowderSnow("
CALL = "        removeUpperLapisDiamondAfterNeighbourFeatures(chunk);\n"
MARKER = "NeverFolia R9: final owner-chunk upper lapis/diamond cleanup at LIGHT"

METHOD = r'''    /**
     * NeverFolia R9: final owner-chunk upper lapis/diamond cleanup at LIGHT.
     *
     * LIGHT has a radius-1 INITIALIZE_LIGHT dependency in the NeverFolia hook,
     * so every neighboring FEATURES pass that can write a cross-chunk vanilla
     * ore vein has completed before this method runs. This is therefore the
     * authoritative final suppression pass for the R9 Y=-64..319 contract.
     * Reads and writes stay inside the owning chunk.
     */
    private static void removeUpperLapisDiamondAfterNeighbourFeatures(final ChunkAccess chunk) {
        final int minY = -64;
        final int maxY = 319;
        final int minSectionY = SectionPos.blockToSectionCoord(minY);
        final int maxSectionY = SectionPos.blockToSectionCoord(maxY);
        final LevelChunkSection[] sections = chunk.getSections();
        final ChunkPos chunkPos = chunk.getPos();
        final int minX = chunkPos.getMinBlockX();
        final int minZ = chunkPos.getMinBlockZ();
        final BlockPos.MutableBlockPos pos = new BlockPos.MutableBlockPos();

        for (int sectionY = minSectionY; sectionY <= maxSectionY; ++sectionY) {
            final int sectionIndex = chunk.getSectionIndexFromSectionY(sectionY);
            if (sectionIndex < 0 || sectionIndex >= sections.length) continue;
            final LevelChunkSection section = sections[sectionIndex];
            if (!section.maybeHas(state -> isUpperForbiddenOre(state))) continue;

            final int sectionMinY = SectionPos.sectionToBlockCoord(sectionY);
            final int scanMinY = Math.max(minY, sectionMinY);
            final int scanMaxY = Math.min(maxY, sectionMinY + 15);
            for (int y = scanMinY; y <= scanMaxY; ++y) {
                final int localY = SectionPos.sectionRelative(y);
                for (int localZ = 0; localZ < 16; ++localZ) {
                    for (int localX = 0; localX < 16; ++localX) {
                        final BlockState state = section.getBlockState(localX, localY, localZ);
                        if (!isUpperForbiddenOre(state)) continue;
                        final BlockState host = state.is(Blocks.DEEPSLATE_LAPIS_ORE)
                            || state.is(Blocks.DEEPSLATE_DIAMOND_ORE)
                            ? Blocks.DEEPSLATE.defaultBlockState()
                            : Blocks.STONE.defaultBlockState();
                        pos.set(minX + localX, y, minZ + localZ);
                        chunk.setBlockState(pos, host, 0);
                    }
                }
            }
        }
    }

    private static boolean isUpperForbiddenOre(final BlockState state) {
        return state.is(Blocks.LAPIS_ORE)
            || state.is(Blocks.DEEPSLATE_LAPIS_ORE)
            || state.is(Blocks.DIAMOND_ORE)
            || state.is(Blocks.DEEPSLATE_DIAMOND_ORE);
    }

'''


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][R9 upper ore LIGHT cleanup] {message}")


def method_bounds(text: str, signature: str) -> tuple[int, int]:
    start = text.find(signature)
    if start < 0:
        fail(f"method signature not found: {signature.strip()}")
    opening = text.find("{", start)
    if opening < 0:
        fail("method opening brace missing")
    depth = 0
    in_string = in_char = escaped = False
    i = opening
    while i < len(text):
        ch = text[i]
        if in_string:
            if escaped: escaped = False
            elif ch == "\\": escaped = True
            elif ch == '"': in_string = False
            i += 1; continue
        if in_char:
            if escaped: escaped = False
            elif ch == "\\": escaped = True
            elif ch == "'": in_char = False
            i += 1; continue
        if ch == '"': in_string = True
        elif ch == "'": in_char = True
        elif ch == "{": depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0: return start, i + 1
        i += 1
    fail("unterminated method")


def patch(text: str) -> str:
    if MARKER in text:
        validate(text)
        return text
    start, end = method_bounds(text, APPLY_SIG)
    apply = text[start:end]
    anchor = "        final BlockState water = Blocks.WATER.defaultBlockState();\n"
    if anchor not in apply:
        fail("apply() water-state anchor missing")
    apply = apply.replace(anchor, anchor + "\n" + CALL, 1)
    text = text[:start] + apply + text[end:]
    if METHOD_ANCHOR not in text:
        fail("removeDeepPowderSnow insertion anchor missing; R9 flood override not applied")
    text = text.replace(METHOD_ANCHOR, METHOD + METHOD_ANCHOR, 1)
    validate(text)
    return text


def validate(text: str) -> None:
    required = (
        MARKER,
        CALL.strip(),
        "final int minY = -64;",
        "final int maxY = 319;",
        "section.maybeHas(state -> isUpperForbiddenOre(state))",
        "Blocks.LAPIS_ORE",
        "Blocks.DEEPSLATE_LAPIS_ORE",
        "Blocks.DIAMOND_ORE",
        "Blocks.DEEPSLATE_DIAMOND_ORE",
        "Blocks.DEEPSLATE.defaultBlockState()",
        "Blocks.STONE.defaultBlockState()",
    )
    missing = [needle for needle in required if needle not in text]
    if missing:
        fail(f"missing markers: {missing}")
    start, end = method_bounds(text, APPLY_SIG)
    apply = text[start:end]
    if apply.count(CALL.strip()) != 1:
        fail("cleanup call must occur exactly once in apply()")


def self_test() -> None:
    fixture = '''class NeverOverworldFlood {
    public static void apply(final WorldGenLevel level, final ChunkAccess chunk) {
        if (false) return;
        final int minY = level.getMinY() + 1;
        final BlockState air = Blocks.AIR.defaultBlockState();
        final BlockState water = Blocks.WATER.defaultBlockState();
        removeDeepPowderSnow(chunk, minY, FLOOD_LEVEL - 1, air);
    }
    private static void removeDeepPowderSnow(
        final ChunkAccess chunk, final int minY, final int maxY, final BlockState air
    ) {}
}
'''
    out = patch(fixture)
    validate(out)
    if patch(out) != out:
        fail("SELF-TEST: transformer is not idempotent")
    print("[NeverFolia][R9 upper ore LIGHT cleanup] SELF-TEST OK")
    print("  final Y=-64..319 lapis/diamond cleanup after neighbouring FEATURES")
    print("  owner-chunk only; section maybeHas fast-path")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("folia", nargs="?", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test(); return
    if args.folia is None:
        parser.error("folia worktree path is required")
    self_test()
    helper = args.folia.resolve() / HELPER_REL
    if not helper.is_file():
        fail(f"NeverOverworldFlood helper missing: {helper}")
    helper.write_text(patch(helper.read_text(encoding="utf-8")), encoding="utf-8")
    print("[NeverFolia][R9 upper ore LIGHT cleanup] final suppression applied")
    print(f"  helper: {helper}")


if __name__ == "__main__":
    main()
