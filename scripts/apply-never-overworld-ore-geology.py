#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

TASKS_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/chunk/status/ChunkStatusTasks.java")
HELPER_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldOreGeology.java")
HOOK_CALL = "net.minecraft.world.level.chunk.NeverOverworldOreGeology.apply(level, chunk);"


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][NeverOverworld geology] {message}")


def patch_tasks(source: str) -> str:
    if HOOK_CALL in source:
        fail("ChunkStatusTasks is already patched for native ore geology")

    needle = """      context.generator()
         .applyCarvers(
            region, level.getSeed(), level.getChunkSource().randomState(), level.getBiomeManager(), level.structureManager().forWorldGenRegion(region), chunk
         );
      return CompletableFuture.completedFuture(chunk);
"""
    if source.count(needle) != 1:
        fail("expected exactly one generateCarvers completion point")

    replacement = """      context.generator()
         .applyCarvers(
            region, level.getSeed(), level.getChunkSource().randomState(), level.getBiomeManager(), level.structureManager().forWorldGenRegion(region), chunk
         );
      // NeverFolia: CARVERS has blockStateWriteRadius(0). Generate deterministic
      // deep geology after caves are cut and before structures/features are placed.
      net.minecraft.world.level.chunk.NeverOverworldOreGeology.apply(level, chunk);
      return CompletableFuture.completedFuture(chunk);
"""
    return source.replace(needle, replacement, 1)


def helper_source() -> str:
    return r'''package net.minecraft.world.level.chunk;

import com.mojang.logging.LogUtils;
import java.util.concurrent.atomic.AtomicBoolean;
import net.minecraft.core.BlockPos;
import net.minecraft.world.level.ChunkPos;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.WorldGenLevel;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.BlockState;
import org.slf4j.Logger;

/**
 * Deterministic NR-DEV-1 deep ore geology.
 *
 * <p>Deposits are derived only from world seed, absolute coarse-cell coordinates
 * and per-ore salts. Every chunk independently evaluates all candidate segments
 * that can geometrically intersect it, then clips writes to its own 16x16 column.
 * No mutable neighboring chunk state and no shared Random instance are used.</p>
 *
 * <p>The pass runs immediately after CARVERS. Caves can therefore expose veins,
 * while later structure/feature placement remains authoritative over the rock.</p>
 */
public final class NeverOverworldOreGeology {
    private static final Logger LOGGER = LogUtils.getLogger();
    private static final AtomicBoolean LOGGED = new AtomicBoolean();
    private static final int EXPECTED_MIN_Y = -512;
    private static final int EXPECTED_HEIGHT = 1024;
    private static final int DEEP_MAX_Y = -96;
    private static final int PROVINCE_SCALE = 384;
    private static final double TAU = Math.PI * 2.0D;

    private NeverOverworldOreGeology() {}

    public static void apply(final WorldGenLevel level, final ChunkAccess chunk) {
        if (!level.getLevel().dimension().equals(Level.OVERWORLD)
            || level.getMinY() != EXPECTED_MIN_Y
            || level.getHeight() != EXPECTED_HEIGHT) {
            return;
        }

        if (LOGGED.compareAndSet(false, true)) {
            LOGGER.info(
                "[NeverFolia][NeverOverworld] Native ore geology active: seed/absolute-coordinate provinces and chunk-owned veins"
            );
        }

        final long seed = level.getSeed();
        for (OreKind kind : OreKind.values()) {
            generateKind(seed, chunk, kind);
        }
    }

    private static void generateKind(final long seed, final ChunkAccess chunk, final OreKind kind) {
        final ChunkPos chunkPos = chunk.getPos();
        final int chunkMinX = chunkPos.getMinBlockX();
        final int chunkMaxX = chunkMinX + 15;
        final int chunkMinZ = chunkPos.getMinBlockZ();
        final int chunkMaxZ = chunkMinZ + 15;
        final int reach = (int)Math.ceil(kind.maxLength * 0.5D + kind.maxRadius + 3.0D);

        final int minCellX = Math.floorDiv(chunkMinX - reach, kind.cellSize);
        final int maxCellX = Math.floorDiv(chunkMaxX + reach, kind.cellSize);
        final int minCellZ = Math.floorDiv(chunkMinZ - reach, kind.cellSize);
        final int maxCellZ = Math.floorDiv(chunkMaxZ + reach, kind.cellSize);
        final int minCellY = Math.floorDiv(kind.minY - reach, kind.cellSize);
        final int maxCellY = Math.floorDiv(kind.maxY + reach, kind.cellSize);

        for (int cellY = minCellY; cellY <= maxCellY; ++cellY) {
            for (int cellZ = minCellZ; cellZ <= maxCellZ; ++cellZ) {
                for (int cellX = minCellX; cellX <= maxCellX; ++cellX) {
                    generateCandidate(seed, chunk, kind, cellX, cellY, cellZ, chunkMinX, chunkMaxX, chunkMinZ, chunkMaxZ);
                }
            }
        }
    }

    private static void generateCandidate(
        final long seed,
        final ChunkAccess chunk,
        final OreKind kind,
        final int cellX,
        final int cellY,
        final int cellZ,
        final int chunkMinX,
        final int chunkMaxX,
        final int chunkMinZ,
        final int chunkMaxZ
    ) {
        long h = hashCell(seed, kind.salt, cellX, cellY, cellZ);
        final double gate = unit(h);
        h = mix64(h);

        final double centerX = cellX * (double)kind.cellSize + unit(h) * kind.cellSize;
        h = mix64(h);
        final double centerY = cellY * (double)kind.cellSize + unit(h) * kind.cellSize;
        if (centerY < kind.minY || centerY > kind.maxY) {
            return;
        }
        h = mix64(h);
        final double centerZ = cellZ * (double)kind.cellSize + unit(h) * kind.cellSize;

        final double province = provinceStrength(seed, centerX, centerZ, kind.salt ^ 0x6A09E667F3BCC909L);
        if (province < kind.minProvince) {
            return;
        }
        final double provinceChance = kind.baseChance * (0.55D + province * 0.75D);
        if (gate >= Math.min(0.98D, provinceChance)) {
            return;
        }

        h = mix64(h);
        final double yaw = unit(h) * TAU;
        h = mix64(h);
        final double pitch = (unit(h) - 0.5D) * kind.pitchSpan;
        h = mix64(h);
        final double length = lerp(kind.minLength, kind.maxLength, unit(h));
        h = mix64(h);
        final double radius = lerp(kind.minRadius, kind.maxRadius, unit(h));

        final double horizontal = Math.cos(pitch);
        final double dx = Math.cos(yaw) * horizontal;
        final double dy = Math.sin(pitch);
        final double dz = Math.sin(yaw) * horizontal;
        final double half = length * 0.5D;
        final double ax = centerX - dx * half;
        final double ay = centerY - dy * half;
        final double az = centerZ - dz * half;
        final double bx = centerX + dx * half;
        final double by = centerY + dy * half;
        final double bz = centerZ + dz * half;

        final int minX = Math.max(chunkMinX, floor(Math.min(ax, bx) - radius - 1.0D));
        final int maxX = Math.min(chunkMaxX, floor(Math.max(ax, bx) + radius + 1.0D));
        final int minZ = Math.max(chunkMinZ, floor(Math.min(az, bz) - radius - 1.0D));
        final int maxZ = Math.min(chunkMaxZ, floor(Math.max(az, bz) + radius + 1.0D));
        final int minY = Math.max(kind.minY, floor(Math.min(ay, by) - radius - 1.0D));
        final int maxY = Math.min(kind.maxY, floor(Math.max(ay, by) + radius + 1.0D));
        if (minX > maxX || minY > maxY || minZ > maxZ) {
            return;
        }

        final double vx = bx - ax;
        final double vy = by - ay;
        final double vz = bz - az;
        final double segmentLengthSquared = vx * vx + vy * vy + vz * vz;
        final BlockPos.MutableBlockPos pos = new BlockPos.MutableBlockPos();

        for (int y = minY; y <= maxY; ++y) {
            for (int z = minZ; z <= maxZ; ++z) {
                for (int x = minX; x <= maxX; ++x) {
                    final double px = x + 0.5D;
                    final double py = y + 0.5D;
                    final double pz = z + 0.5D;
                    double t = ((px - ax) * vx + (py - ay) * vy + (pz - az) * vz) / segmentLengthSquared;
                    t = Math.max(0.0D, Math.min(1.0D, t));
                    final double qx = ax + vx * t;
                    final double qy = ay + vy * t;
                    final double qz = az + vz * t;
                    final double ddx = px - qx;
                    final double ddy = py - qy;
                    final double ddz = pz - qz;

                    // The tube tapers at both ends and receives deterministic
                    // block-scale roughness. This avoids perfectly cylindrical ore.
                    final double taper = 0.58D + 0.42D * Math.sin(Math.PI * t);
                    final double roughness = 0.82D + 0.36D * unit(hashBlock(seed, kind.salt, x, y, z));
                    final double localRadius = radius * taper * roughness;
                    if (ddx * ddx + ddy * ddy + ddz * ddz > localRadius * localRadius) {
                        continue;
                    }

                    if (unit(hashBlock(seed ^ 0xD1B54A32D192ED03L, kind.salt, x, y, z)) > kind.fill) {
                        continue;
                    }

                    pos.set(x, y, z);
                    final BlockState current = chunk.getBlockState(pos);
                    final BlockState replacement = replacementFor(current, kind);
                    if (replacement != null) {
                        chunk.setBlockState(pos, replacement, 0);
                    }
                }
            }
        }
    }

    private static BlockState replacementFor(final BlockState current, final OreKind kind) {
        if (current.is(Blocks.DEEPSLATE) || current.is(Blocks.TUFF)) {
            return kind.deepOre.defaultBlockState();
        }
        if (current.is(Blocks.STONE)) {
            return kind.stoneOre.defaultBlockState();
        }
        return null;
    }

    /** Smooth deterministic value-noise used only to group veins into provinces. */
    private static double provinceStrength(final long seed, final double x, final double z, final long salt) {
        final int gx = floor(x / PROVINCE_SCALE);
        final int gz = floor(z / PROVINCE_SCALE);
        final double fx = smooth(x / PROVINCE_SCALE - gx);
        final double fz = smooth(z / PROVINCE_SCALE - gz);
        final double v00 = unit(hashCell(seed, salt, gx, 0, gz));
        final double v10 = unit(hashCell(seed, salt, gx + 1, 0, gz));
        final double v01 = unit(hashCell(seed, salt, gx, 0, gz + 1));
        final double v11 = unit(hashCell(seed, salt, gx + 1, 0, gz + 1));
        return lerp(lerp(v00, v10, fx), lerp(v01, v11, fx), fz);
    }

    private static double smooth(final double value) {
        return value * value * (3.0D - 2.0D * value);
    }

    private static double lerp(final double a, final double b, final double t) {
        return a + (b - a) * t;
    }

    private static int floor(final double value) {
        return (int)Math.floor(value);
    }

    private static long hashCell(final long seed, final long salt, final int x, final int y, final int z) {
        long value = seed ^ salt;
        value ^= (long)x * 0x9E3779B97F4A7C15L;
        value = mix64(value);
        value ^= (long)y * 0xC2B2AE3D27D4EB4FL;
        value = mix64(value);
        value ^= (long)z * 0x165667B19E3779F9L;
        return mix64(value);
    }

    private static long hashBlock(final long seed, final long salt, final int x, final int y, final int z) {
        return hashCell(seed ^ 0x94D049BB133111EBL, salt, x, y, z);
    }

    private static long mix64(long value) {
        value ^= value >>> 30;
        value *= 0xBF58476D1CE4E5B9L;
        value ^= value >>> 27;
        value *= 0x94D049BB133111EBL;
        value ^= value >>> 31;
        return value;
    }

    private static double unit(final long value) {
        return (double)(value >>> 11) * 0x1.0p-53;
    }

    private enum OreKind {
        IRON(0x11A2B3C4D5E6F701L, 96, 0.58D, 0.28D, -480, DEEP_MAX_Y, 36.0D, 96.0D, 1.8D, 3.8D, 0.70D, 0.86D, Blocks.IRON_ORE, Blocks.DEEPSLATE_IRON_ORE),
        COPPER(0x22B3C4D5E6F70112L, 112, 0.42D, 0.35D, -300, DEEP_MAX_Y, 28.0D, 72.0D, 2.0D, 4.0D, 0.62D, 0.80D, Blocks.COPPER_ORE, Blocks.DEEPSLATE_COPPER_ORE),
        GOLD(0x33C4D5E6F7011223L, 128, 0.24D, 0.50D, -420, -128, 20.0D, 56.0D, 1.2D, 2.4D, 0.58D, 0.72D, Blocks.GOLD_ORE, Blocks.DEEPSLATE_GOLD_ORE),
        REDSTONE(0x44D5E6F701122334L, 104, 0.40D, 0.35D, -480, -160, 30.0D, 80.0D, 1.2D, 2.3D, 0.52D, 0.72D, Blocks.REDSTONE_ORE, Blocks.DEEPSLATE_REDSTONE_ORE),
        LAPIS(0x55E6F70112233445L, 144, 0.18D, 0.52D, -360, -128, 16.0D, 40.0D, 1.4D, 2.8D, 0.46D, 0.75D, Blocks.LAPIS_ORE, Blocks.DEEPSLATE_LAPIS_ORE),
        DIAMOND(0x66F7011223344556L, 160, 0.10D, 0.64D, -480, -180, 14.0D, 34.0D, 0.8D, 1.45D, 0.40D, 0.58D, Blocks.DIAMOND_ORE, Blocks.DEEPSLATE_DIAMOND_ORE);

        final long salt;
        final int cellSize;
        final double baseChance;
        final double minProvince;
        final int minY;
        final int maxY;
        final double minLength;
        final double maxLength;
        final double minRadius;
        final double maxRadius;
        final double pitchSpan;
        final double fill;
        final Block stoneOre;
        final Block deepOre;

        OreKind(
            final long salt,
            final int cellSize,
            final double baseChance,
            final double minProvince,
            final int minY,
            final int maxY,
            final double minLength,
            final double maxLength,
            final double minRadius,
            final double maxRadius,
            final double pitchSpan,
            final double fill,
            final Block stoneOre,
            final Block deepOre
        ) {
            this.salt = salt;
            this.cellSize = cellSize;
            this.baseChance = baseChance;
            this.minProvince = minProvince;
            this.minY = minY;
            this.maxY = maxY;
            this.minLength = minLength;
            this.maxLength = maxLength;
            this.minRadius = minRadius;
            this.maxRadius = maxRadius;
            this.pitchSpan = pitchSpan;
            this.fill = fill;
            this.stoneOre = stoneOre;
            this.deepOre = deepOre;
        }
    }
}
'''


def self_test() -> None:
    fixture = '''class ChunkStatusTasks {
   static CompletableFuture<ChunkAccess> generateCarvers(
      final WorldGenContext context, final ChunkStep step, final StaticCache2D<GenerationChunkHolder> chunks, final ChunkAccess chunk
   ) {
      ServerLevel level = context.level();
      WorldGenRegion region = new WorldGenRegion(level, chunks, step, chunk);
      context.generator()
         .applyCarvers(
            region, level.getSeed(), level.getChunkSource().randomState(), level.getBiomeManager(), level.structureManager().forWorldGenRegion(region), chunk
         );
      return CompletableFuture.completedFuture(chunk);
   }
}
'''
    patched = patch_tasks(fixture)
    if patched.count(HOOK_CALL) != 1:
        fail("SELF-TEST: geology hook not injected exactly once")
    if patched.index("applyCarvers") > patched.index(HOOK_CALL):
        fail("SELF-TEST: geology must run after carvers")

    helper = helper_source()
    for marker in (
        "EXPECTED_MIN_Y = -512",
        "EXPECTED_HEIGHT = 1024",
        "DEEP_MAX_Y = -96",
        "provinceStrength",
        "hashCell",
        "hashBlock",
        "Math.floorDiv",
        "chunk.getPos()",
        "chunk.setBlockState",
        "IRON(",
        "COPPER(",
        "GOLD(",
        "REDSTONE(",
        "LAPIS(",
        "DIAMOND(",
        "Native ore geology active",
    ):
        if marker not in helper:
            fail(f"SELF-TEST: helper missing {marker!r}")
    for forbidden in (
        "new Random(",
        "RandomSource",
        "level.getChunk(",
    ):
        if forbidden in helper:
            fail(f"SELF-TEST: order-dependent/random neighbor dependency present: {forbidden!r}")

    print("[NeverFolia][NeverOverworld geology] NATIVE ORE GEOLOGY SELF-TEST OK")


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply deterministic native NR-DEV-1 ore geology")
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

    print("[NeverFolia][NeverOverworld geology] native chunk-owned ore geology applied")
    print(f"  tasks: {tasks}")
    print(f"  helper: {helper}")


if __name__ == "__main__":
    main()
