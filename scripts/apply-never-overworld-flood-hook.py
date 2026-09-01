#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path

GENERATOR_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/chunk/ChunkGenerator.java")
HELPER_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldFlood.java")


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][NeverOverworld flood] {message}")


def matching_brace(source: str, open_brace: int) -> int:
    depth = 0
    in_string = False
    escaped = False
    for index in range(open_brace, len(source)):
        ch = source[index]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return index
    fail("unterminated Java block")


def patch_generator(source: str) -> str:
    marker = "NeverOverworldFlood.apply(level, chunk);"
    if marker in source:
        fail("ChunkGenerator is already patched")
    match = re.search(
        r"public\s+void\s+applyBiomeDecoration\s*\(\s*final\s+WorldGenLevel\s+level\s*,\s*final\s+ChunkAccess\s+chunk\s*,\s*final\s+StructureManager\s+structureManager\s*\)\s*\{",
        source,
        re.DOTALL,
    )
    if match is None:
        fail("ChunkGenerator.applyBiomeDecoration(...) not found")
    method_open = source.find("{", match.start(), match.end())
    method_close = matching_brace(source, method_open)
    insertion = "\n      // NeverFolia: deterministic NeverRaft flooding after structures/decorations.\n      NeverOverworldFlood.apply(level, chunk);\n"
    return source[:method_close] + insertion + source[method_close:]


def helper_source() -> str:
    return r'''package net.minecraft.world.level.chunk;

import net.minecraft.core.BlockPos;
import net.minecraft.world.level.WorldGenLevel;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.BlockState;

/**
 * NeverRaft VANILLA_FLOODED post-decoration pass.
 *
 * <p>Every invocation reads and writes only the chunk currently being decorated.
 * This is deliberate: Folia may decorate neighboring chunks concurrently, so the
 * result must not depend on neighboring region ownership or completion order.</p>
 */
final class NeverOverworldFlood {
    private static final int EXPECTED_MIN_Y = -512;
    private static final int EXPECTED_HEIGHT = 1024;
    private static final int FLOOD_LEVEL = 128;
    private static final int FULL_FLOOD_MIN_Y = 64;
    private static final int CONNECTIVITY_SEED_Y = 63;

    private NeverOverworldFlood() {}

    static void apply(final WorldGenLevel level, final ChunkAccess chunk) {
        if (level.getMinY() != EXPECTED_MIN_Y || level.getHeight() != EXPECTED_HEIGHT) {
            return;
        }

        final ChunkPos chunkPos = chunk.getPos();
        final int minX = chunkPos.getMinBlockX();
        final int minZ = chunkPos.getMinBlockZ();
        final BlockState water = Blocks.WATER.defaultBlockState();
        final BlockState air = Blocks.AIR.defaultBlockState();
        final BlockPos.MutableBlockPos pos = new BlockPos.MutableBlockPos();

        // Remove generated underground groundwater/lava. Player-placed fluids are
        // unaffected because this pass executes only during chunk generation.
        final int undergroundMinY = level.getMinY() + 1;
        for (int y = undergroundMinY; y < FULL_FLOOD_MIN_Y; ++y) {
            for (int localZ = 0; localZ < 16; ++localZ) {
                for (int localX = 0; localX < 16; ++localX) {
                    pos.set(minX + localX, y, minZ + localZ);
                    final BlockState state = chunk.getBlockState(pos);
                    if (state.is(Blocks.WATER) || state.is(Blocks.LAVA)) {
                        chunk.setBlockState(pos, air, 0);
                    }
                }
            }
        }

        // Y=64..128 is the globally flooded band. Solid terrain and structure
        // blocks survive; all air cells become stable source water.
        for (int y = FULL_FLOOD_MIN_Y; y <= FLOOD_LEVEL; ++y) {
            for (int localZ = 0; localZ < 16; ++localZ) {
                for (int localX = 0; localX < 16; ++localX) {
                    pos.set(minX + localX, y, minZ + localZ);
                    final BlockState state = chunk.getBlockState(pos);
                    if (state.is(Blocks.LAVA)) {
                        chunk.setBlockState(pos, air, 0);
                    }
                    if (chunk.getBlockState(pos).isAir()) {
                        chunk.setBlockState(pos, water, 0);
                    }
                }
            }
        }

        floodChunkLocalOceanConnections(chunk, minX, minZ, undergroundMinY, water);
    }

    /**
     * Flood only sub-Y64 cavities connected to the flooded/ocean boundary inside
     * this chunk. Closed caves remain dry. Cross-chunk connectivity is intentionally
     * not inferred from mutable neighboring chunk state; that keeps the result
     * strictly order-independent under Folia. A later NR revision can expand the
     * connectivity solver with seed/base-density sampling if visual tests require it.
     */
    private static void floodChunkLocalOceanConnections(
        final ChunkAccess chunk,
        final int minX,
        final int minZ,
        final int minY,
        final BlockState water
    ) {
        final int maxY = CONNECTIVITY_SEED_Y;
        final int layerCount = maxY - minY + 1;
        if (layerCount <= 0) {
            return;
        }

        final int capacity = layerCount * 256;
        final boolean[] visited = new boolean[capacity];
        final int[] queue = new int[capacity];
        int head = 0;
        int tail = 0;
        final BlockPos.MutableBlockPos pos = new BlockPos.MutableBlockPos();

        // Seed from Y=63 cells that are directly exposed to the new flood band at
        // Y=64. Existing ocean water at Y=63 is also considered connected.
        for (int localZ = 0; localZ < 16; ++localZ) {
            for (int localX = 0; localX < 16; ++localX) {
                pos.set(minX + localX, maxY, minZ + localZ);
                final BlockState state = chunk.getBlockState(pos);
                pos.set(minX + localX, FULL_FLOOD_MIN_Y, minZ + localZ);
                final boolean waterAbove = chunk.getBlockState(pos).is(Blocks.WATER);
                if ((state.isAir() && waterAbove) || state.is(Blocks.WATER)) {
                    final int encoded = encode(localX, maxY, localZ, minY);
                    visited[encoded] = true;
                    queue[tail++] = encoded;
                }
            }
        }

        while (head < tail) {
            final int encoded = queue[head++];
            final int localX = encoded & 15;
            final int localZ = (encoded >>> 4) & 15;
            final int y = minY + (encoded >>> 8);
            pos.set(minX + localX, y, minZ + localZ);
            final BlockState state = chunk.getBlockState(pos);
            if (state.isAir()) {
                chunk.setBlockState(pos, water, 0);
            } else if (!state.is(Blocks.WATER)) {
                continue;
            }

            tail = enqueue(chunk, queue, visited, tail, localX - 1, y, localZ, minX, minZ, minY, maxY);
            tail = enqueue(chunk, queue, visited, tail, localX + 1, y, localZ, minX, minZ, minY, maxY);
            tail = enqueue(chunk, queue, visited, tail, localX, y, localZ - 1, minX, minZ, minY, maxY);
            tail = enqueue(chunk, queue, visited, tail, localX, y, localZ + 1, minX, minZ, minY, maxY);
            tail = enqueue(chunk, queue, visited, tail, localX, y - 1, localZ, minX, minZ, minY, maxY);
            tail = enqueue(chunk, queue, visited, tail, localX, y + 1, localZ, minX, minZ, minY, maxY);
        }
    }

    private static int enqueue(
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
        final BlockState state = chunk.getBlockState(pos);
        if (!state.isAir() && !state.is(Blocks.WATER)) {
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
    fixture = '''package net.minecraft.world.level.chunk;
class ChunkGenerator {
    public void applyBiomeDecoration(final WorldGenLevel level, final ChunkAccess chunk, final StructureManager structureManager) {
        if (true) {
            doSomething();
        }
    }
}
'''
    patched = patch_generator(fixture)
    if patched.count("NeverOverworldFlood.apply(level, chunk);") != 1:
        fail("SELF-TEST: flood call was not injected exactly once")
    helper = helper_source()
    for required in (
        "EXPECTED_MIN_Y = -512",
        "FLOOD_LEVEL = 128",
        "FULL_FLOOD_MIN_Y = 64",
        "floodChunkLocalOceanConnections",
        "chunk.setBlockState",
    ):
        if required not in helper:
            fail(f"SELF-TEST: helper missing {required!r}")
    print("[NeverFolia][NeverOverworld flood] SELF-TEST OK")


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply deterministic NeverOverworld flood hook")
    parser.add_argument("folia", nargs="?", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if args.folia is None:
        parser.error("folia worktree path is required unless --self-test is used")

    folia = args.folia.resolve()
    generator = folia / GENERATOR_REL
    helper = folia / HELPER_REL
    if not generator.is_file():
        fail(f"ChunkGenerator source not found: {generator}")
    source = generator.read_text(encoding="utf-8")
    generator.write_text(patch_generator(source), encoding="utf-8")
    helper.write_text(helper_source(), encoding="utf-8")
    print("[NeverFolia][NeverOverworld flood] hook applied")
    print(f"  generator: {generator}")
    print(f"  helper: {helper}")


if __name__ == "__main__":
    main()
