#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path

TASKS_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/chunk/status/ChunkStatusTasks.java")
HELPER_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldFlood.java")
FLOOD_CALL = "net.minecraft.world.level.chunk.NeverOverworldFlood.apply(context.level(), chunk);"


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][NeverOverworld flood] {message}")


def matching_delimiter(source: str, start: int, opening: str, closing: str) -> int:
    depth = 0
    in_string = False
    in_char = False
    escaped = False
    index = start
    while index < len(source):
        ch = source[index]
        nxt = source[index + 1] if index + 1 < len(source) else ""

        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            index += 1
            continue
        if in_char:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == "'":
                in_char = False
            index += 1
            continue
        if ch == '"':
            in_string = True
            index += 1
            continue
        if ch == "'":
            in_char = True
            index += 1
            continue
        if ch == "/" and nxt == "/":
            newline = source.find("\n", index + 2)
            index = len(source) if newline < 0 else newline + 1
            continue
        if ch == "/" and nxt == "*":
            end = source.find("*/", index + 2)
            if end < 0:
                fail("unterminated Java block comment while parsing LIGHT method")
            index = end + 2
            continue

        if ch == opening:
            depth += 1
        elif ch == closing:
            depth -= 1
            if depth == 0:
                return index
        index += 1
    fail(f"unterminated Java delimiter {opening}{closing}")


def patch_tasks(source: str) -> str:
    if "NeverOverworldFlood.apply(" in source:
        fail("ChunkStatusTasks is already patched")

    method_pattern = re.compile(
        r"(?:public\s+|private\s+|protected\s+)?static\s+CompletableFuture\s*<\s*ChunkAccess\s*>\s+light\s*\(",
        re.MULTILINE,
    )
    matches = list(method_pattern.finditer(source))
    if len(matches) != 1:
        fail(f"expected exactly one ChunkStatusTasks.light(...) method, got {len(matches)}")

    match = matches[0]
    params_open = source.find("(", match.start(), match.end())
    params_close = matching_delimiter(source, params_open, "(", ")")
    params = source[params_open + 1 : params_close]

    context_match = re.search(r"\bWorldGenContext\s+(\w+)\b", params)
    chunk_match = re.search(r"\bChunkAccess\s+(\w+)\b", params)
    if context_match is None or chunk_match is None:
        fail("could not resolve WorldGenContext/ChunkAccess parameter names in LIGHT method")
    context_name = context_match.group(1)
    chunk_name = chunk_match.group(1)

    method_open = source.find("{", params_close)
    if method_open < 0:
        fail("ChunkStatusTasks.light(...) opening brace not found")

    # Ensure the brace belongs to this method rather than a following declaration.
    between = source[params_close + 1 : method_open]
    if ";" in between:
        fail("ChunkStatusTasks.light(...) appears to be a declaration without a body")

    line_start = source.rfind("\n", 0, method_open) + 1
    method_indent = source[line_start:method_open]
    body_indent = method_indent + "   "
    call = f"net.minecraft.world.level.chunk.NeverOverworldFlood.apply({context_name}.level(), {chunk_name});"
    insertion = (
        "\n"
        f"{body_indent}// NeverFolia: LIGHT has a radius-1 INITIALIZE_LIGHT dependency. Every\n"
        f"{body_indent}// neighboring chunk that can write FEATURES into this chunk has therefore\n"
        f"{body_indent}// finished decoration before the chunk-owned flood mutates final blocks.\n"
        f"{body_indent}{call}\n"
    )
    return source[: method_open + 1] + insertion + source[method_open + 1 :]


def helper_source() -> str:
    return r'''package net.minecraft.world.level.chunk;

import net.minecraft.core.BlockPos;
import net.minecraft.core.SectionPos;
import net.minecraft.world.level.ChunkPos;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.WorldGenLevel;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.levelgen.Heightmap;

/**
 * NeverRaft VANILLA_FLOODED pass.
 *
 * <p>The hook runs at the beginning of the LIGHT chunk status. Minecraft 26.2
 * requires radius-1 INITIALIZE_LIGHT for LIGHT, and every INITIALIZE_LIGHT chunk
 * has already completed FEATURES. Consequently all neighboring decoration that
 * may write into the owning chunk is complete before the flood is applied.</p>
 *
 * <p>The pass itself is chunk-owned: it never reads mutable neighboring chunks
 * and never writes outside the current chunk. Flooding is surface-connected rather
 * than a blanket Y fill, so sealed caves and enclosed structures stay dry.</p>
 */
public final class NeverOverworldFlood {
    private static final int EXPECTED_MIN_Y = -512;
    private static final int EXPECTED_HEIGHT = 1024;
    private static final int FLOOD_LEVEL = 128;

    private NeverOverworldFlood() {}

    public static void apply(final WorldGenLevel level, final ChunkAccess chunk) {
        if (!level.getLevel().dimension().equals(Level.OVERWORLD)
            || level.getMinY() != EXPECTED_MIN_Y
            || level.getHeight() != EXPECTED_HEIGHT) {
            return;
        }

        final int minY = level.getMinY() + 1;
        final BlockState air = Blocks.AIR.defaultBlockState();
        final BlockState water = Blocks.WATER.defaultBlockState();

        removeGeneratedFluids(chunk, minY, FLOOD_LEVEL, air);
        floodSurfaceConnectedAir(chunk, minY, FLOOD_LEVEL, water);
    }

    /**
     * Remove pure generated water/lava only. Waterlogged structure blocks are
     * preserved because replacing them would destroy the block itself. This pass
     * executes during generation, so later player-placed fluids are unaffected.
     *
     * <p>Sections without any fluid are skipped through LevelChunkSection's cached
     * fluid count; solid deep sections cost O(sections), not O(height).</p>
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
            if (!section.hasFluid()) {
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
                        if (!state.is(Blocks.WATER) && !state.is(Blocks.LAVA)) {
                            continue;
                        }
                        pos.set(minX + localX, y, minZ + localZ);
                        chunk.setBlockState(pos, air, 0);
                    }
                }
            }
        }
    }

    /**
     * Seed only columns whose fluid-ignoring terrain surface lies below Y=128.
     * OCEAN_FLOOR_WG is not confused by water removed immediately beforehand.
     * A sealed cavern below a mountain is not a seed because its exterior terrain
     * surface remains above the flood plane.
     *
     * <p>BFS follows air inside the owning chunk only. Coastlines, valleys, ravines
     * and cave mouths connected to the flooded exterior fill with source water;
     * enclosed caves/mineshafts/Trial Chambers/Ancient City spaces remain dry.</p>
     */
    private static void floodSurfaceConnectedAir(
        final ChunkAccess chunk,
        final int minY,
        final int maxY,
        final BlockState water
    ) {
        final int layerCount = maxY - minY + 1;
        if (layerCount <= 0) {
            return;
        }

        final int capacity = layerCount * 256;
        final boolean[] visited = new boolean[capacity];
        final int[] queue = new int[capacity];
        int head = 0;
        int tail = 0;
        final ChunkPos chunkPos = chunk.getPos();
        final int minX = chunkPos.getMinBlockX();
        final int minZ = chunkPos.getMinBlockZ();
        final BlockPos.MutableBlockPos pos = new BlockPos.MutableBlockPos();

        for (int localZ = 0; localZ < 16; ++localZ) {
            for (int localX = 0; localX < 16; ++localX) {
                final int surfaceY = chunk.getHeight(Heightmap.Types.OCEAN_FLOOR_WG, localX, localZ);
                if (surfaceY >= maxY) {
                    continue;
                }
                pos.set(minX + localX, maxY, minZ + localZ);
                if (!chunk.getBlockState(pos).isAir()) {
                    continue;
                }
                final int encoded = encode(localX, maxY, localZ, minY);
                visited[encoded] = true;
                queue[tail++] = encoded;
            }
        }

        while (head < tail) {
            final int encoded = queue[head++];
            final int localX = encoded & 15;
            final int localZ = (encoded >>> 4) & 15;
            final int y = minY + (encoded >>> 8);
            pos.set(minX + localX, y, minZ + localZ);
            if (!chunk.getBlockState(pos).isAir()) {
                continue;
            }

            chunk.setBlockState(pos, water, 0);

            tail = enqueueAir(chunk, queue, visited, tail, localX - 1, y, localZ, minX, minZ, minY, maxY);
            tail = enqueueAir(chunk, queue, visited, tail, localX + 1, y, localZ, minX, minZ, minY, maxY);
            tail = enqueueAir(chunk, queue, visited, tail, localX, y, localZ - 1, minX, minZ, minY, maxY);
            tail = enqueueAir(chunk, queue, visited, tail, localX, y, localZ + 1, minX, minZ, minY, maxY);
            tail = enqueueAir(chunk, queue, visited, tail, localX, y - 1, localZ, minX, minZ, minY, maxY);
            tail = enqueueAir(chunk, queue, visited, tail, localX, y + 1, localZ, minX, minZ, minY, maxY);
        }
    }

    private static int enqueueAir(
        final ChunkAccess chunk,
        final int[] queue,
        final boolean[] visited,
        int tail,
        final int localX,
        final int y,
        final int localZ,
        final int minX,
        final int minZ,
        final int minY,
        final int maxY
    ) {
        if (localX < 0 || localX > 15 || localZ < 0 || localZ > 15 || y < minY || y > maxY) {
            return tail;
        }
        final int encoded = encode(localX, y, localZ, minY);
        if (visited[encoded]) {
            return tail;
        }
        final BlockPos pos = new BlockPos(minX + localX, y, minZ + localZ);
        if (!chunk.getBlockState(pos).isAir()) {
            return tail;
        }
        visited[encoded] = true;
        queue[tail++] = encoded;
        return tail;
    }

    private static int encode(final int localX, final int y, final int localZ, final int minY) {
        return ((y - minY) << 8) | (localZ << 4) | localX;
    }
}
'''


def self_test() -> None:
    fixtures = (
        '''package net.minecraft.world.level.chunk.status;
class ChunkStatusTasks {
   static CompletableFuture<ChunkAccess> light(
      final WorldGenContext context, final ChunkStep step, final StaticCache2D<GenerationChunkHolder> chunks, final ChunkAccess chunk
   ) {
      boolean lighted = isLighted(chunk);
      return null;
   }
}
''',
        '''class ChunkStatusTasks {
   public static CompletableFuture < ChunkAccess > light(
      final WorldGenContext worldContext,
      final ChunkStep step,
      final StaticCache2D<GenerationChunkHolder> cache,
      final ChunkAccess centerChunk
   )
   {
      // Folia formatting may differ from Mojmap.
      return doLight(centerChunk);
   }
}
''',
    )
    expected_calls = (
        "net.minecraft.world.level.chunk.NeverOverworldFlood.apply(context.level(), chunk);",
        "net.minecraft.world.level.chunk.NeverOverworldFlood.apply(worldContext.level(), centerChunk);",
    )
    for fixture, expected in zip(fixtures, expected_calls):
        patched = patch_tasks(fixture)
        if patched.count(expected) != 1:
            fail(f"SELF-TEST: structural LIGHT parser did not inject expected call: {expected}")

    helper = helper_source()
    for required in (
        "import net.minecraft.world.level.ChunkPos;",
        "public final class NeverOverworldFlood",
        "public static void apply",
        "EXPECTED_MIN_Y = -512",
        "FLOOD_LEVEL = 128",
        "Level.OVERWORLD",
        "Heightmap.Types.OCEAN_FLOOR_WG",
        "section.hasFluid()",
        "floodSurfaceConnectedAir",
        "chunk.setBlockState",
        "beginning of the LIGHT chunk status",
    ):
        if required not in helper:
            fail(f"SELF-TEST: helper missing {required!r}")
    for forbidden in (
        "FULL_FLOOD_MIN_Y",
        "applyBiomeDecoration",
        "floodChunkLocalOceanConnections",
    ):
        if forbidden in helper:
            fail(f"SELF-TEST: obsolete flood marker remains: {forbidden!r}")
    print("[NeverFolia][NeverOverworld flood] STRUCTURAL LIGHT-BARRIER V3 SELF-TEST OK")


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply deterministic NeverOverworld LIGHT-barrier flood hook")
    parser.add_argument("folia", nargs="?", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if args.folia is None:
        parser.error("folia worktree path is required unless --self-test is used")

    folia = args.folia.resolve()
    tasks = folia / TASKS_REL
    helper = folia / HELPER_REL
    if not tasks.is_file():
        fail(f"ChunkStatusTasks source not found: {tasks}")
    tasks.write_text(patch_tasks(tasks.read_text(encoding="utf-8")), encoding="utf-8")
    helper.write_text(helper_source(), encoding="utf-8")
    print("[NeverFolia][NeverOverworld flood] structural LIGHT-barrier v3 hook applied")
    print(f"  tasks: {tasks}")
    print(f"  helper: {helper}")


if __name__ == "__main__":
    main()
