#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

HELPER_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldFlood.java")
R8_FALLBACK_CALL = "        floodLargeBoundaryConnectedCaverns(chunk, minY, FLOOD_LEVEL, water);\n"
FLUID_STRIP_CALL = "        removeGeneratedFluids(chunk, minY, FLOOD_LEVEL, air);\n"
POWDER_CALL = "        removeDeepPowderSnow(chunk, minY, FLOOD_LEVEL - 1, air);\n"
LOG_LINE = "            || state.is(net.minecraft.tags.BlockTags.LOGS)\n"
LEAVES_LINE = "            || state.is(net.minecraft.tags.BlockTags.LEAVES)\n"
IS_FLOODABLE_SIG = "    private static boolean isFloodable(final BlockState state)"
POWDER_ANCHOR = "    private static void floodSurfaceConnectedVolume(\n"
SURFACE_SIG = "    private static BlockState drownedSurfaceState(\n"

POWDER_METHOD = r'''    /**
     * R9: powder snow generated below the new ocean plane is invalid terrain.
     * Removing it before the flood lets surface-connected cells become water,
     * while enclosed structures such as Trial Chambers keep ordinary air.
     */
    private static void removeDeepPowderSnow(
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
            if (sectionIndex < 0 || sectionIndex >= sections.length) continue;
            final LevelChunkSection section = sections[sectionIndex];
            if (!section.maybeHas(state -> state.is(Blocks.POWDER_SNOW))) continue;
            final int sectionMinY = SectionPos.sectionToBlockCoord(sectionY);
            final int scanMinY = Math.max(minY, sectionMinY);
            final int scanMaxY = Math.min(maxY, sectionMinY + 15);
            for (int y = scanMinY; y <= scanMaxY; ++y) {
                final int localY = SectionPos.sectionRelative(y);
                for (int localZ = 0; localZ < 16; ++localZ) {
                    for (int localX = 0; localX < 16; ++localX) {
                        if (!section.getBlockState(localX, localY, localZ).is(Blocks.POWDER_SNOW)) continue;
                        pos.set(minX + localX, y, minZ + localZ);
                        chunk.setBlockState(pos, air, 0);
                    }
                }
            }
        }
    }

'''

SURFACE_METHODS = r'''    private static BlockState drownedSurfaceState(
        final int blockX,
        final int blockY,
        final int blockZ,
        final int waterDepth
    ) {
        final double broad = sedimentNoise(blockX, blockZ, 24, 0x6A09E667F3BCC909L);
        final double detail = sedimentNoise(blockX + 173, blockZ - 91, 11, 0xBB67AE8584CAA73BL);
        final double field = broad * 0.72D + detail * 0.28D;

        if (waterDepth <= 6) {
            if (field < 0.22D) return Blocks.DIRT.defaultBlockState();
            if (field < 0.34D) return Blocks.COARSE_DIRT.defaultBlockState();
            if (field < 0.48D) return Blocks.MUD.defaultBlockState();
            if (field < 0.66D) return Blocks.GRAVEL.defaultBlockState();
            if (field < 0.83D) return Blocks.SAND.defaultBlockState();
            if (field < 0.94D) return Blocks.CLAY.defaultBlockState();
            return Blocks.STONE.defaultBlockState();
        }
        if (waterDepth <= 24) {
            if (field < 0.15D) return Blocks.DIRT.defaultBlockState();
            if (field < 0.26D) return Blocks.MUD.defaultBlockState();
            if (field < 0.49D) return Blocks.GRAVEL.defaultBlockState();
            if (field < 0.70D) return Blocks.SAND.defaultBlockState();
            if (field < 0.88D) return Blocks.CLAY.defaultBlockState();
            if (field < 0.97D) return Blocks.STONE.defaultBlockState();
            return Blocks.ANDESITE.defaultBlockState();
        }
        if (field < 0.10D) return Blocks.MUD.defaultBlockState();
        if (field < 0.38D) return Blocks.GRAVEL.defaultBlockState();
        if (field < 0.61D) return Blocks.SAND.defaultBlockState();
        if (field < 0.82D) return Blocks.CLAY.defaultBlockState();
        if (field < 0.96D) return Blocks.STONE.defaultBlockState();
        return Blocks.ANDESITE.defaultBlockState();
    }

    private static double sedimentNoise(final int blockX, final int blockZ, final int scale, final long salt) {
        final int gx = Math.floorDiv(blockX, scale);
        final int gz = Math.floorDiv(blockZ, scale);
        final double fx0 = Math.floorMod(blockX, scale) / (double)scale;
        final double fz0 = Math.floorMod(blockZ, scale) / (double)scale;
        final double fx = fx0 * fx0 * (3.0D - 2.0D * fx0);
        final double fz = fz0 * fz0 * (3.0D - 2.0D * fz0);
        final double v00 = sedimentCorner(gx, gz, salt);
        final double v10 = sedimentCorner(gx + 1, gz, salt);
        final double v01 = sedimentCorner(gx, gz + 1, salt);
        final double v11 = sedimentCorner(gx + 1, gz + 1, salt);
        final double a = v00 + (v10 - v00) * fx;
        final double b = v01 + (v11 - v01) * fx;
        return a + (b - a) * fz;
    }

    private static double sedimentCorner(final int gridX, final int gridZ, final long salt) {
        long value = salt;
        value ^= (long)gridX * 0x9E3779B97F4A7C15L;
        value ^= (long)gridZ * 0xC2B2AE3D27D4EB4FL;
        value = sedimentMix(value);
        return (double)(value >>> 11) * 0x1.0p-53;
    }

    private static long sedimentMix(long value) {
        value ^= value >>> 30;
        value *= 0xBF58476D1CE4E5B9L;
        value ^= value >>> 27;
        value *= 0x94D049BB133111EBL;
        value ^= value >>> 31;
        return value;
    }

'''


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][R9 flood stabilization] {message}")


def method_bounds(text: str, signature: str) -> tuple[int, int]:
    start = text.find(signature)
    if start < 0:
        fail(f"method signature not found: {signature.strip()}")
    opening = text.find("{", start)
    if opening < 0:
        fail(f"method opening brace not found: {signature.strip()}")
    depth = 0
    in_string = False
    in_char = False
    escaped = False
    i = opening
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
        if in_char:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == "'":
                in_char = False
            i += 1
            continue
        if ch == '"':
            in_string = True
        elif ch == "'":
            in_char = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return start, i + 1
        i += 1
    fail(f"unterminated method: {signature.strip()}")


def add_water_to_floodable(text: str) -> str:
    start, end = method_bounds(text, IS_FLOODABLE_SIG)
    method = text[start:end]
    if "state.is(Blocks.WATER)" in method:
        return text
    anchor = "return state.isAir()"
    if method.count(anchor) != 1:
        fail(f"isFloodable air-return anchor count mismatch: {method.count(anchor)}")
    method = method.replace(anchor, anchor + "\n            || state.is(Blocks.WATER)", 1)
    return text[:start] + method + text[end:]


def patch(text: str) -> str:
    if "// NeverFolia R9: interpolated drowned sediment" in text:
        validate(text)
        return text

    for marker in (
        R8_FALLBACK_CALL.strip(),
        "BlockTags.LOGS",
        "BlockTags.LEAVES",
        "Math.floorDiv(blockX, 3)",
        "isDrownedFrozenOverlay",
    ):
        if marker not in text:
            fail(f"expected R8 marker missing before R9 override: {marker}")

    if text.count(FLUID_STRIP_CALL) != 1:
        fail("generated-fluid strip call count mismatch")
    text = text.replace(FLUID_STRIP_CALL, POWDER_CALL, 1)

    if text.count(R8_FALLBACK_CALL) != 1:
        fail("R8 boundary fallback call count mismatch")
    text = text.replace(R8_FALLBACK_CALL, "", 1)

    if text.count(LOG_LINE) != 1 or text.count(LEAVES_LINE) != 1:
        fail("LOGS/LEAVES floodability count mismatch")
    text = text.replace(LOG_LINE, "", 1).replace(LEAVES_LINE, "", 1)
    text = add_water_to_floodable(text)

    if text.count(POWDER_ANCHOR) != 1:
        fail("floodSurfaceConnectedVolume insertion anchor missing")
    text = text.replace(POWDER_ANCHOR, POWDER_METHOD + POWDER_ANCHOR, 1)

    start, end = method_bounds(text, SURFACE_SIG)
    text = text[:start] + "    // NeverFolia R9: interpolated drowned sediment\n" + SURFACE_METHODS + text[end:]
    validate(text)
    return text


def validate(text: str) -> None:
    required = (
        "// NeverFolia R9: interpolated drowned sediment",
        POWDER_CALL.strip(),
        "sedimentNoise(blockX, blockZ, 24",
        "section.maybeHas(state -> state.is(Blocks.POWDER_SNOW))",
    )
    missing = [marker for marker in required if marker not in text]
    if missing:
        fail(f"R9 output missing markers: {missing}")

    flood_start, flood_end = method_bounds(text, IS_FLOODABLE_SIG)
    flood_method = text[flood_start:flood_end]
    if flood_method.count("state.is(Blocks.WATER)") != 1:
        fail("R9 isFloodable must preserve/traverse existing water exactly once")
    if "BlockTags.LOGS" in flood_method or "BlockTags.LEAVES" in flood_method:
        fail("R9 isFloodable must preserve partially flooded trees")

    for forbidden in (
        R8_FALLBACK_CALL.strip(),
        "Math.floorDiv(blockX, 3)",
        FLUID_STRIP_CALL.strip(),
    ):
        if forbidden in text:
            fail(f"obsolete R8 behavior survived R9: {forbidden}")


def self_test() -> None:
    fixture = '''class NeverOverworldFlood {
    void apply() {
        removeGeneratedFluids(chunk, minY, FLOOD_LEVEL, air);
        floodSurfaceConnectedVolume(chunk, minY, FLOOD_LEVEL, water);
        weatherSubmergedSurface(chunk, minY, FLOOD_LEVEL);
        floodLargeBoundaryConnectedCaverns(chunk, minY, FLOOD_LEVEL, water);
    }
    private static void floodSurfaceConnectedVolume(
        Object chunk, int minY, int maxY, Object water
    ) {}
    private static BlockState drownedSurfaceState(
        final int blockX, final int blockY, final int blockZ, final int waterDepth
    ) {
        final int cellX = Math.floorDiv(blockX, 3);
        final int cellZ = Math.floorDiv(blockZ, 3);
        return Blocks.DIRT.defaultBlockState();
    }
    private static boolean otherAirCheck(final BlockState state) {
        return state.isAir();
    }
    private static boolean isDrownedFrozenOverlay(Object state) { return true; }
    private static boolean isDrownedSurfaceOverlay(Object state) { return true; }
    private static boolean isFloodable(final BlockState state) {
        return state.isAir()
            || (state.getFluidState().isEmpty() && state.canBeReplaced())
            || state.is(net.minecraft.tags.BlockTags.LOGS)
            || state.is(net.minecraft.tags.BlockTags.LEAVES)
            || state.is(net.minecraft.tags.BlockTags.RAILS);
    }
}
'''
    out = patch(fixture)
    validate(out)
    if "otherAirCheck" not in out or "return state.isAir();" not in out:
        fail("SELF-TEST: non-isFloodable air predicate was modified")
    if patch(out) != out:
        fail("SELF-TEST: transformer is not idempotent")
    print("[NeverFolia][R9 flood stabilization] SELF-TEST OK")


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
    helper.write_text(patch(helper.read_text(encoding="utf-8")), encoding="utf-8")
    print("[NeverFolia][R9 flood stabilization] field fixes applied")


if __name__ == "__main__":
    main()
