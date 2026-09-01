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
import net.minecraft.core.SectionPos;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.WorldGenLevel;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.levelgen.Heightmap;

/**
 * NeverRaft VANILLA_FLOODED post-decoration pass.
 *
 * <p>The pass is deliberately chunk-owned: it never reads mutable neighboring
 * chunks and never writes outside the chunk currently being decorated. That makes
 * the result independent of Folia region ownership and chunk completion order.</p>
 *
 * <p>Flooding is surface-connected rather than a blanket Y fill. Generated
 * groundwater/lava is removed first, then only air reachable from an externally
 * open column at Y=128 is refilled. Sealed caves and enclosed structures therefore
 * remain dry even when their Y is below the flood plane.</p>
 */
final class NeverOverworldFlood {
    private static final int EXPECTED_MIN_Y = -512;
    private static final int EXPECTED_HEIGHT = 1024;
    private static final int FLOOD_LEVEL = 128;

    private NeverOverworldFlood() {}

    static void apply(final WorldGenLevel level, final ChunkAccess chunk) {
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
     * Remove only pure generated water/lava blocks. Waterlogged structure blocks
     * are preserved because replacing them would destroy the block itself. This
     * runs during generation only, so later player-placed fluids are unaffected.
     *
     * <p>Sections without any fluid are skipped through LevelChunkSection's cached
     * fluid count; solid deep sections therefore cost O(sections), not O(height).</p>
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
     * Seed the flood only from columns whose motion-blocking terrain surface lies
     * below Y=128. OCEAN_FLOOR_WG deliberately ignores fluid and is not confused by
     * the water removed in the preceding pass. A sealed cavern under a mountain has
     * a surface above the flood plane and therefore cannot become a seed.
     *
     * <p>BFS then follows only air inside this chunk. This floods coastlines, open
     * valleys, ravines, cave mouths and local continuations down to the extended
     * world floor while preserving enclosed caves/mineshafts/Trial Chambers/Ancient
     * City spaces that have no open path to the flood surface.</p>
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
        "Level.OVERWORLD",
        "Heightmap.Types.OCEAN_FLOOR_WG",
        "section.hasFluid()",
        "floodSurfaceConnectedAir",
        "chunk.setBlockState",
    ):
        if required not in helper:
            fail(f"SELF-TEST: helper missing {required!r}")
    for forbidden in (
        "FULL_FLOOD_MIN_Y",
        "floodChunkLocalOceanConnections",
    ):
        if forbidden in helper:
            fail(f"SELF-TEST: obsolete blanket-flood marker remains: {forbidden!r}")
    print("[NeverFolia][NeverOverworld flood] SURFACE-CONNECTED V2 SELF-TEST OK")


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply deterministic NeverOverworld surface-connected flood hook")
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
    print("[NeverFolia][NeverOverworld flood] surface-connected v2 hook applied")
    print(f"  generator: {generator}")
    print(f"  helper: {helper}")


if __name__ == "__main__":
    main()
