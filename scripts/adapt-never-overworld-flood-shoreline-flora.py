#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

HELPER_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldFlood.java")
CAPTURE_ANCHOR = "        removeGeneratedFluids(chunk, minY, FLOOD_LEVEL, air);\n"
FLOOD_ANCHOR = "        floodSurfaceConnectedVolume(chunk, minY, FLOOD_LEVEL, water);\n"
METHOD_ANCHOR = "    private static boolean isFloodable(final BlockState state) {\n"
MARKER = "// NeverFolia: preserve biome-driven cane/lily presence at the new flood shoreline."

METHODS = r'''    // NeverFolia: preserve biome-driven cane/lily presence at the new flood shoreline.
    // Presence is sampled from vanilla FEATURES before flooding, then relocated
    // chunk-locally after the Y=128 waterline exists. No neighboring chunk is read.
    private static FloodShorelineSnapshot captureFloodShorelineFlora(final ChunkAccess chunk) {
        final boolean[] sugarCane = new boolean[256];
        final boolean[] lilyPads = new boolean[256];
        final ChunkPos chunkPos = chunk.getPos();
        final int minX = chunkPos.getMinBlockX();
        final int minZ = chunkPos.getMinBlockZ();
        final BlockPos.MutableBlockPos pos = new BlockPos.MutableBlockPos();

        for (int localZ = 0; localZ < 16; ++localZ) {
            for (int localX = 0; localX < 16; ++localX) {
                final int surfaceY = chunk.getHeight(Heightmap.Types.WORLD_SURFACE_WG, localX, localZ);
                if (surfaceY > FLOOD_LEVEL + 4) {
                    continue;
                }
                final int index = (localZ << 4) | localX;
                final int scanTop = Math.min(FLOOD_LEVEL + 4, surfaceY + 2);
                final int scanBottom = Math.max(chunk.getMinY(), surfaceY - 12);
                for (int y = scanTop; y >= scanBottom; --y) {
                    pos.set(minX + localX, y, minZ + localZ);
                    final BlockState state = chunk.getBlockState(pos);
                    if (state.is(Blocks.SUGAR_CANE)) {
                        sugarCane[index] = true;
                    } else if (state.is(Blocks.LILY_PAD)) {
                        lilyPads[index] = true;
                    }
                    if (sugarCane[index] && lilyPads[index]) {
                        break;
                    }
                }
            }
        }
        return new FloodShorelineSnapshot(sugarCane, lilyPads);
    }

    private static void restoreFloodShorelineFlora(
        final ChunkAccess chunk,
        final FloodShorelineSnapshot snapshot
    ) {
        final ChunkPos chunkPos = chunk.getPos();
        final int minX = chunkPos.getMinBlockX();
        final int minZ = chunkPos.getMinBlockZ();

        for (int index = 0; index < 256; ++index) {
            final int originX = index & 15;
            final int originZ = (index >>> 4) & 15;
            if (snapshot.lilyPads()[index]) {
                restoreLilyPad(chunk, minX, minZ, originX, originZ);
            }
            if (snapshot.sugarCane()[index]) {
                restoreSugarCane(chunk, minX, minZ, originX, originZ, index);
            }
        }
    }

    private static boolean restoreLilyPad(
        final ChunkAccess chunk,
        final int minX,
        final int minZ,
        final int originX,
        final int originZ
    ) {
        final BlockPos.MutableBlockPos pos = new BlockPos.MutableBlockPos();
        final BlockPos.MutableBlockPos below = new BlockPos.MutableBlockPos();
        for (int radius = 0; radius <= 7; ++radius) {
            for (int dz = -radius; dz <= radius; ++dz) {
                for (int dx = -radius; dx <= radius; ++dx) {
                    if (Math.max(Math.abs(dx), Math.abs(dz)) != radius) {
                        continue;
                    }
                    final int localX = originX + dx;
                    final int localZ = originZ + dz;
                    if (localX < 1 || localX > 14 || localZ < 1 || localZ > 14) {
                        continue;
                    }
                    pos.set(minX + localX, FLOOD_LEVEL + 1, minZ + localZ);
                    below.set(minX + localX, FLOOD_LEVEL, minZ + localZ);
                    if (chunk.getBlockState(pos).isAir() && chunk.getBlockState(below).is(Blocks.WATER)) {
                        chunk.setBlockState(pos, Blocks.LILY_PAD.defaultBlockState(), 0);
                        return true;
                    }
                }
            }
        }
        return false;
    }

    private static boolean restoreSugarCane(
        final ChunkAccess chunk,
        final int minX,
        final int minZ,
        final int originX,
        final int originZ,
        final int sourceIndex
    ) {
        final BlockPos.MutableBlockPos pos = new BlockPos.MutableBlockPos();
        final BlockPos.MutableBlockPos ground = new BlockPos.MutableBlockPos();
        for (int radius = 0; radius <= 7; ++radius) {
            for (int dz = -radius; dz <= radius; ++dz) {
                for (int dx = -radius; dx <= radius; ++dx) {
                    if (Math.max(Math.abs(dx), Math.abs(dz)) != radius) {
                        continue;
                    }
                    final int localX = originX + dx;
                    final int localZ = originZ + dz;
                    if (localX < 1 || localX > 14 || localZ < 1 || localZ > 14) {
                        continue;
                    }
                    pos.set(minX + localX, FLOOD_LEVEL + 1, minZ + localZ);
                    ground.set(minX + localX, FLOOD_LEVEL, minZ + localZ);
                    if (!chunk.getBlockState(pos).isAir() || !isSugarCaneGround(chunk.getBlockState(ground))) {
                        continue;
                    }
                    if (!hasChunkLocalWaterNeighbor(chunk, minX, minZ, localX, localZ)) {
                        continue;
                    }

                    // Minecraft 26.2 exposes ChunkPos coordinates as x()/z(); it has no
                    // instance toLong(). Build a stable local key directly from them.
                    final ChunkPos chunkPos = chunk.getPos();
                    final long chunkKey = ((long)chunkPos.x() * 0x9E3779B97F4A7C15L)
                        ^ ((long)chunkPos.z() * 0xC2B2AE3D27D4EB4FL);
                    final long hash = mix64(chunkKey ^ ((long)sourceIndex * 0x165667B19E3779F9L));
                    final int height = 1 + (int)Math.floorMod(hash, 3L);
                    for (int dy = 0; dy < height; ++dy) {
                        pos.set(minX + localX, FLOOD_LEVEL + 1 + dy, minZ + localZ);
                        if (!chunk.getBlockState(pos).isAir()) {
                            break;
                        }
                        chunk.setBlockState(pos, Blocks.SUGAR_CANE.defaultBlockState(), 0);
                    }
                    return true;
                }
            }
        }
        return false;
    }

    private static boolean isSugarCaneGround(final BlockState state) {
        return state.is(net.minecraft.tags.BlockTags.DIRT)
            || state.is(net.minecraft.tags.BlockTags.SAND);
    }

    private static boolean hasChunkLocalWaterNeighbor(
        final ChunkAccess chunk,
        final int minX,
        final int minZ,
        final int localX,
        final int localZ
    ) {
        final BlockPos.MutableBlockPos pos = new BlockPos.MutableBlockPos();
        pos.set(minX + localX - 1, FLOOD_LEVEL, minZ + localZ);
        if (chunk.getBlockState(pos).is(Blocks.WATER)) return true;
        pos.set(minX + localX + 1, FLOOD_LEVEL, minZ + localZ);
        if (chunk.getBlockState(pos).is(Blocks.WATER)) return true;
        pos.set(minX + localX, FLOOD_LEVEL, minZ + localZ - 1);
        if (chunk.getBlockState(pos).is(Blocks.WATER)) return true;
        pos.set(minX + localX, FLOOD_LEVEL, minZ + localZ + 1);
        return chunk.getBlockState(pos).is(Blocks.WATER);
    }

    private static long mix64(long value) {
        value ^= value >>> 33;
        value *= 0xff51afd7ed558ccdL;
        value ^= value >>> 33;
        value *= 0xc4ceb9fe1a85ec53L;
        value ^= value >>> 33;
        return value;
    }

    private record FloodShorelineSnapshot(boolean[] sugarCane, boolean[] lilyPads) {}

'''


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][flood shoreline flora] {message}")


def patch_source(source: str) -> str:
    if MARKER in source:
        fail("shoreline flora adaptation already applied")
    if source.count(CAPTURE_ANCHOR) != 1:
        fail(f"expected one generated-fluid call, got {source.count(CAPTURE_ANCHOR)}")
    if source.count(FLOOD_ANCHOR) != 1:
        fail(f"expected one flood-volume call, got {source.count(FLOOD_ANCHOR)}")
    if source.count(METHOD_ANCHOR) != 1:
        fail(f"expected one isFloodable insertion anchor, got {source.count(METHOD_ANCHOR)}")

    source = source.replace(
        CAPTURE_ANCHOR,
        "        final FloodShorelineSnapshot shorelineFlora = captureFloodShorelineFlora(chunk);\n" + CAPTURE_ANCHOR,
        1,
    )
    source = source.replace(
        FLOOD_ANCHOR,
        FLOOD_ANCHOR + "        restoreFloodShorelineFlora(chunk, shorelineFlora);\n",
        1,
    )
    source = source.replace(METHOD_ANCHOR, METHODS + METHOD_ANCHOR, 1)

    for marker in (
        MARKER,
        "captureFloodShorelineFlora(chunk)",
        "restoreFloodShorelineFlora(chunk, shorelineFlora)",
        "Blocks.SUGAR_CANE",
        "Blocks.LILY_PAD",
        "BlockTags.DIRT",
        "BlockTags.SAND",
        "localX < 1 || localX > 14",
        "chunkPos.x()",
        "chunkPos.z()",
    ):
        if marker not in source:
            fail(f"patched source missing {marker!r}")
    if ".toLong()" in source:
        fail("obsolete ChunkPos.toLong() API survived shoreline patch")
    return source


def self_test() -> None:
    fixture = '''public final class NeverOverworldFlood {
    private static final int FLOOD_LEVEL = 128;
    public static void apply(final WorldGenLevel level, final ChunkAccess chunk) {
        final int minY = -511;
        final BlockState air = Blocks.AIR.defaultBlockState();
        final BlockState water = Blocks.WATER.defaultBlockState();
        removeGeneratedFluids(chunk, minY, FLOOD_LEVEL, air);
        floodSurfaceConnectedVolume(chunk, minY, FLOOD_LEVEL, water);
    }
    private static boolean isFloodable(final BlockState state) {
        return state.isAir();
    }
}
'''
    patched = patch_source(fixture)
    if patched.index("captureFloodShorelineFlora(chunk)") > patched.index("removeGeneratedFluids"):
        fail("SELF-TEST: flora snapshot must precede generated-fluid removal")
    if patched.index("restoreFloodShorelineFlora(chunk, shorelineFlora)") < patched.index("floodSurfaceConnectedVolume"):
        fail("SELF-TEST: flora restore must follow flood")
    if "chunkPos.x()" not in patched or "chunkPos.z()" not in patched or ".toLong()" in patched:
        fail("SELF-TEST: Minecraft 26.2 ChunkPos API normalization failed")
    print("[NeverFolia][flood shoreline flora] SELF-TEST OK")


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
    path.write_text(patch_source(path.read_text(encoding="utf-8")), encoding="utf-8")
    print("[NeverFolia][flood shoreline flora] flood shoreline adaptation applied")
    print("  drowned old cane/lily: removed by flood")
    print("  vanilla presence signal: relocated to Y=128 shoreline chunk-locally")
    print("  chunk key: Minecraft 26.2 x()/z() accessors; no ChunkPos.toLong()")
    print(f"  helper: {path}")


if __name__ == "__main__":
    main()
