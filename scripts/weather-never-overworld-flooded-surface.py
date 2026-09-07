#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

HELPER_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldFlood.java")
CALL_ANCHOR = "        floodSurfaceConnectedVolume(chunk, minY, FLOOD_LEVEL, water);\n"
METHOD_ANCHOR = "    private static boolean isFloodable(final BlockState state) {\n"
MARKER = "// NEVERFOLIA: drowned surface weathering"
CALL = "        weatherSubmergedSurface(chunk, minY, FLOOD_LEVEL);\n"

METHODS = r'''    // NEVERFOLIA: drowned surface weathering
    // The flood is a persistent world-state change, not a momentary water fill.
    // Natural living topsoil that ended up below Y=128 is therefore weathered
    // into coherent patches of sediment and exposed substrate. This deliberately
    // does not touch structure blocks: only vanilla natural soil/snow/moss states
    // are eligible, and every read/write remains inside the owning chunk.
    private static void weatherSubmergedSurface(
        final ChunkAccess chunk,
        final int minY,
        final int maxY
    ) {
        final ChunkPos chunkPos = chunk.getPos();
        final int minX = chunkPos.getMinBlockX();
        final int minZ = chunkPos.getMinBlockZ();
        final BlockPos.MutableBlockPos surface = new BlockPos.MutableBlockPos();
        final BlockPos.MutableBlockPos above = new BlockPos.MutableBlockPos();

        for (int localZ = 0; localZ < 16; ++localZ) {
            for (int localX = 0; localX < 16; ++localX) {
                // Heightmaps store the first free Y above the ocean floor block.
                final int surfaceY = chunk.getHeight(Heightmap.Types.OCEAN_FLOOR_WG, localX, localZ) - 1;
                if (surfaceY < minY || surfaceY >= maxY) {
                    continue;
                }

                surface.set(minX + localX, surfaceY, minZ + localZ);
                above.set(minX + localX, surfaceY + 1, minZ + localZ);
                if (!chunk.getBlockState(above).is(Blocks.WATER)) {
                    continue;
                }

                final BlockState original = chunk.getBlockState(surface);
                if (!isWeatherableFloodedSurface(original)) {
                    continue;
                }

                final int waterDepth = maxY - surfaceY;
                final BlockState weathered = drownedSurfaceState(
                    minX + localX,
                    surfaceY,
                    minZ + localZ,
                    waterDepth
                );
                if (weathered != original) {
                    chunk.setBlockState(surface, weathered, 0);
                }
            }
        }
    }

    private static boolean isWeatherableFloodedSurface(final BlockState state) {
        return state.is(Blocks.GRASS_BLOCK)
            || state.is(Blocks.DIRT)
            || state.is(Blocks.COARSE_DIRT)
            || state.is(Blocks.ROOTED_DIRT)
            || state.is(Blocks.PODZOL)
            || state.is(Blocks.MYCELIUM)
            || state.is(Blocks.DIRT_PATH)
            || state.is(Blocks.MOSS_BLOCK)
            || state.is(Blocks.SNOW_BLOCK);
    }

    private static BlockState drownedSurfaceState(
        final int blockX,
        final int blockY,
        final int blockZ,
        final int waterDepth
    ) {
        // Use ~3x3 deterministic cells rather than per-block random noise. The
        // result reads as sediment patches and eroded shelves, not a checkerboard.
        final int cellX = Math.floorDiv(blockX, 3);
        final int cellZ = Math.floorDiv(blockZ, 3);
        int hash = cellX * 73428767 + cellZ * 912931 + Math.floorDiv(blockY, 4) * 19349663;
        hash ^= hash >>> 16;
        hash *= 1103515245;
        hash ^= hash >>> 13;
        final int roll = Math.floorMod(hash, 100);

        if (waterDepth <= 6) {
            if (roll < 28) return Blocks.DIRT.defaultBlockState();
            if (roll < 43) return Blocks.COARSE_DIRT.defaultBlockState();
            if (roll < 58) return Blocks.MUD.defaultBlockState();
            if (roll < 73) return Blocks.GRAVEL.defaultBlockState();
            if (roll < 88) return Blocks.SAND.defaultBlockState();
            if (roll < 95) return Blocks.CLAY.defaultBlockState();
            return Blocks.STONE.defaultBlockState();
        }

        if (waterDepth <= 24) {
            if (roll < 20) return Blocks.DIRT.defaultBlockState();
            if (roll < 32) return Blocks.COARSE_DIRT.defaultBlockState();
            if (roll < 47) return Blocks.MUD.defaultBlockState();
            if (roll < 69) return Blocks.GRAVEL.defaultBlockState();
            if (roll < 84) return Blocks.SAND.defaultBlockState();
            if (roll < 94) return Blocks.CLAY.defaultBlockState();
            if (roll < 98) return Blocks.STONE.defaultBlockState();
            return Blocks.ANDESITE.defaultBlockState();
        }

        if (roll < 12) return Blocks.DIRT.defaultBlockState();
        if (roll < 20) return Blocks.COARSE_DIRT.defaultBlockState();
        if (roll < 33) return Blocks.MUD.defaultBlockState();
        if (roll < 58) return Blocks.GRAVEL.defaultBlockState();
        if (roll < 76) return Blocks.SAND.defaultBlockState();
        if (roll < 90) return Blocks.CLAY.defaultBlockState();
        if (roll < 97) return Blocks.STONE.defaultBlockState();
        return Blocks.ANDESITE.defaultBlockState();
    }

'''


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][NeverOverworld drowned surface] {message}")


def patch_source(source: str) -> str:
    if MARKER in source:
        fail("drowned surface weathering is already applied")
    if source.count(CALL_ANCHOR) != 1:
        fail(f"expected one flood-volume call, got {source.count(CALL_ANCHOR)}")
    if source.count(METHOD_ANCHOR) != 1:
        fail(f"expected one isFloodable insertion anchor, got {source.count(METHOD_ANCHOR)}")

    source = source.replace(CALL_ANCHOR, CALL_ANCHOR + CALL, 1)
    source = source.replace(METHOD_ANCHOR, METHODS + METHOD_ANCHOR, 1)

    required = (
        MARKER,
        "weatherSubmergedSurface(chunk, minY, FLOOD_LEVEL)",
        "Heightmap.Types.OCEAN_FLOOR_WG",
        "Blocks.GRASS_BLOCK",
        "Blocks.DIRT",
        "Blocks.COARSE_DIRT",
        "Blocks.MUD",
        "Blocks.GRAVEL",
        "Blocks.SAND",
        "Blocks.CLAY",
        "Blocks.STONE",
        "Blocks.ANDESITE",
        "Blocks.PODZOL",
        "Blocks.MYCELIUM",
        "Blocks.MOSS_BLOCK",
        "Blocks.SNOW_BLOCK",
        "Math.floorDiv(blockX, 3)",
    )
    missing = [marker for marker in required if marker not in source]
    if missing:
        fail(f"patched helper missing markers: {missing}")
    return source


def self_test() -> None:
    fixture = '''public final class NeverOverworldFlood {
    public static void apply(final WorldGenLevel level, final ChunkAccess chunk) {
        final int minY = -511;
        final BlockState water = Blocks.WATER.defaultBlockState();
        floodSurfaceConnectedVolume(chunk, minY, FLOOD_LEVEL, water);
    }
    private static boolean isFloodable(final BlockState state) {
        return state.isAir();
    }
}
'''
    patched = patch_source(fixture)
    if patched.count(MARKER) != 1:
        fail("SELF-TEST: weathering marker count drifted")
    if patched.index("weatherSubmergedSurface(chunk, minY, FLOOD_LEVEL)") < patched.index("floodSurfaceConnectedVolume"):
        fail("SELF-TEST: submerged surface weathering must run after flood")
    for material in ("Blocks.MUD", "Blocks.GRAVEL", "Blocks.SAND", "Blocks.CLAY", "Blocks.STONE"):
        if material not in patched:
            fail(f"SELF-TEST: missing substrate material {material}")
    print("[NeverFolia][NeverOverworld drowned surface] SELF-TEST OK")


def main() -> None:
    parser = argparse.ArgumentParser(description="Weather NeverOverworld drowned natural topsoil into sediment patches")
    parser.add_argument("folia", nargs="?", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return
    if args.folia is None:
        parser.error("folia worktree is required unless --self-test is used")

    self_test()
    helper = args.folia.resolve() / HELPER_REL
    if not helper.is_file():
        fail(f"NeverOverworldFlood helper not found: {helper}")
    helper.write_text(patch_source(helper.read_text(encoding="utf-8")), encoding="utf-8")
    print("[NeverFolia][NeverOverworld drowned surface] drowned surface weathering applied")
    print("  living topsoil: grass/podzol/mycelium/path/moss/snow no longer survives underwater")
    print("  substrate: coherent dirt/coarse-dirt/mud/gravel/sand/clay/stone/andesite patches")
    print("  depth: deeper flooded shelves bias toward sediment and exposed mineral substrate")
    print("  ownership: all reads/writes remain inside the owning chunk")
    print(f"  helper: {helper}")


if __name__ == "__main__":
    main()
