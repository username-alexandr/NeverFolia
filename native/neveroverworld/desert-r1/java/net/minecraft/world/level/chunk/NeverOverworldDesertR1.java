package net.minecraft.world.level.chunk;

import java.util.ArrayList;
import java.util.List;
import net.minecraft.core.BlockPos;
import net.minecraft.world.level.ChunkPos;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.WorldGenLevel;
import net.minecraft.world.level.biome.Biomes;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.LeavesBlock;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.levelgen.Heightmap;
import net.minecraft.world.level.levelgen.structure.BoundingBox;
import net.minecraft.world.level.levelgen.structure.StructureStart;

/**
 * DESERT-R1: rare chunk-owned desert oases.
 *
 * <p>Each naturally dry desert chunk gets an independent deterministic rare
 * chance. This avoids losing an entire desert cell when a pre-selected chunk
 * lands in water or on the biome edge. The oasis stays fully inside the owning
 * chunk, avoids structure starts and never reads/writes a neighbouring chunk.</p>
 */
public final class NeverOverworldDesertR1 {
    static final int OASIS_CHANCE_DENOMINATOR = 192;
    static final int FLOOD_LEVEL = 128;
    private static final long CELL_SALT = 0x4E4F574F41534953L;

    private NeverOverworldDesertR1() {}

    public static int generate(final WorldGenLevel level, final ChunkAccess chunk) {
        if (!level.getLevel().dimension().equals(Level.OVERWORLD)
            || level.getMinY() != -512
            || level.getHeight() != 1024) {
            return 0;
        }

        final ChunkPos cp = chunk.getPos();
        final long key = mix(level.getSeed() ^ CELL_SALT
            ^ ((long)cp.x() * 0x9E3779B97F4A7C15L)
            ^ ((long)cp.z() * 0xC2B2AE3D27D4EB4FL));
        final int centerLocalX = 6 + (int)Math.floorMod(mix(key ^ 0x632BE59BD9B4E019L), 4L);
        final int centerLocalZ = 6 + (int)Math.floorMod(mix(key ^ 0x94D049BB133111EBL), 4L);
        final int centerX = cp.getMinBlockX() + centerLocalX;
        final int centerZ = cp.getMinBlockZ() + centerLocalZ;
        final int centerSurfaceY = chunk.getHeight(Heightmap.Types.WORLD_SURFACE_WG, centerLocalX, centerLocalZ);
        if (centerSurfaceY <= FLOOD_LEVEL + 2 || centerSurfaceY >= chunk.getMaxY() - 12) return 0;

        final BlockPos center = new BlockPos(centerX, centerSurfaceY, centerZ);
        if (!level.getBiome(center).is(Biomes.DESERT)
            || !isDesertSurface(chunk.getBlockState(center))
            || intersectsStructure(chunk, centerX - 7, centerX + 7, centerZ - 7, centerZ + 7)
            || !selectedChunk(level.getSeed(), cp.x(), cp.z())) {
            return 0;
        }

        int minSurface = Integer.MAX_VALUE;
        int maxSurface = Integer.MIN_VALUE;
        int eligible = 0;
        final BlockPos.MutableBlockPos pos = new BlockPos.MutableBlockPos();
        for (int dz = -4; dz <= 4; ++dz) {
            for (int dx = -4; dx <= 4; ++dx) {
                final int lx = centerLocalX + dx;
                final int lz = centerLocalZ + dz;
                final int y = chunk.getHeight(Heightmap.Types.WORLD_SURFACE_WG, lx, lz);
                minSurface = Math.min(minSurface, y);
                maxSurface = Math.max(maxSurface, y);
                pos.set(cp.getMinBlockX() + lx, y, cp.getMinBlockZ() + lz);
                if (level.getBiome(pos).is(Biomes.DESERT) && isDesertSurface(chunk.getBlockState(pos))) ++eligible;
            }
        }
        if (maxSurface - minSurface > 4 || eligible < 48) return 0;

        final int waterY = minSurface;
        int changed = 0;
        for (int dz = -5; dz <= 5; ++dz) {
            for (int dx = -5; dx <= 5; ++dx) {
                final int lx = centerLocalX + dx;
                final int lz = centerLocalZ + dz;
                if (lx < 0 || lx > 15 || lz < 0 || lz > 15) continue;
                final int worldX = cp.getMinBlockX() + lx;
                final int worldZ = cp.getMinBlockZ() + lz;
                final double d2 = dx * dx + dz * dz;
                final long cell = mix(key ^ ((long)dx * 0xD6E8FEB86659FD93L) ^ ((long)dz * 0xA5A3564E27F886A7L));
                final double wobble = Math.floorMod(cell, 1000L) / 1000.0D;

                if (d2 <= 8.5D + wobble * 3.0D) {
                    final int surfaceY = chunk.getHeight(Heightmap.Types.WORLD_SURFACE_WG, lx, lz);
                    for (int y = waterY + 1; y <= surfaceY + 1; ++y) {
                        pos.set(worldX, y, worldZ);
                        final BlockState state = chunk.getBlockState(pos);
                        if (!state.isAir() && !state.canBeReplaced()) {
                            chunk.setBlockState(pos, Blocks.AIR.defaultBlockState(), 0);
                            ++changed;
                        }
                    }
                    pos.set(worldX, waterY, worldZ);
                    if (!chunk.getBlockState(pos).is(Blocks.WATER)) {
                        chunk.setBlockState(pos, Blocks.WATER.defaultBlockState(), 0);
                        ++changed;
                    }
                    pos.set(worldX, waterY - 1, worldZ);
                    if (!chunk.getBlockState(pos).is(Blocks.SAND)) {
                        chunk.setBlockState(pos, Blocks.SAND.defaultBlockState(), 0);
                        ++changed;
                    }
                } else if (d2 <= 24.0D && wobble < 0.76D) {
                    final int surfaceY = chunk.getHeight(Heightmap.Types.WORLD_SURFACE_WG, lx, lz);
                    pos.set(worldX, surfaceY, worldZ);
                    if (chunk.getBlockState(pos).is(Blocks.SAND)) {
                        chunk.setBlockState(pos, wobble < 0.58D ? Blocks.GRASS_BLOCK.defaultBlockState() : Blocks.COARSE_DIRT.defaultBlockState(), 0);
                        ++changed;
                    }
                }
            }
        }

        final int[][] palmOffsets = {
            {4, 1}, {-4, -1}, {1, 4}, {-1, -4}
        };
        int palms = 0;
        final int rotation = (int)Math.floorMod(mix(key ^ 0xDB4F0B9175AE2165L), 4L);
        for (int i = 0; i < palmOffsets.length && palms < 2; ++i) {
            final int[] off = palmOffsets[(i + rotation) & 3];
            if (placePalm(chunk, centerLocalX + off[0], centerLocalZ + off[1], key ^ i)) {
                ++palms;
            }
        }
        return changed + palms;
    }

    static boolean selectedChunk(final long seed, final int chunkX, final int chunkZ) {
        final long h = mix(seed ^ CELL_SALT
            ^ ((long)chunkX * 0x9E3779B97F4A7C15L)
            ^ ((long)chunkZ * 0xC2B2AE3D27D4EB4FL));
        return Math.floorMod(h, OASIS_CHANCE_DENOMINATOR) == 0L;
    }

    private static boolean placePalm(final ChunkAccess chunk, final int localX, final int localZ, final long key) {
        if (localX < 2 || localX > 13 || localZ < 2 || localZ > 13) return false;
        final int groundY = chunk.getHeight(Heightmap.Types.WORLD_SURFACE_WG, localX, localZ);
        final int worldX = chunk.getPos().getMinBlockX() + localX;
        final int worldZ = chunk.getPos().getMinBlockZ() + localZ;
        final BlockPos.MutableBlockPos pos = new BlockPos.MutableBlockPos(worldX, groundY, worldZ);
        final BlockState ground = chunk.getBlockState(pos);
        if (!(ground.is(Blocks.GRASS_BLOCK) || ground.is(Blocks.COARSE_DIRT) || ground.is(Blocks.SAND))) return false;

        final int height = 5 + (int)Math.floorMod(mix(key), 3L);
        for (int y = groundY + 1; y <= groundY + height + 1; ++y) {
            pos.set(worldX, y, worldZ);
            if (!chunk.getBlockState(pos).isAir() && !chunk.getBlockState(pos).canBeReplaced()) return false;
        }
        for (int y = 1; y <= height; ++y) {
            pos.set(worldX, groundY + y, worldZ);
            chunk.setBlockState(pos, Blocks.JUNGLE_LOG.defaultBlockState(), 0);
        }

        final BlockState leaves = Blocks.JUNGLE_LEAVES.defaultBlockState().setValue(LeavesBlock.PERSISTENT, true);
        final int topY = groundY + height;
        final int[][] canopy = {
            {0,0,0},{1,0,0},{-1,0,0},{0,0,1},{0,0,-1},
            {2,0,0},{-2,0,0},{0,0,2},{0,0,-2},
            {1,0,1},{1,0,-1},{-1,0,1},{-1,0,-1},
            {1,-1,0},{-1,-1,0},{0,-1,1},{0,-1,-1},{0,1,0}
        };
        for (int[] c : canopy) {
            final int lx = localX + c[0];
            final int lz = localZ + c[2];
            if (lx < 0 || lx > 15 || lz < 0 || lz > 15) continue;
            pos.set(worldX + c[0], topY + c[1], worldZ + c[2]);
            final BlockState state = chunk.getBlockState(pos);
            if (state.isAir() || state.canBeReplaced()) chunk.setBlockState(pos, leaves, 0);
        }
        return true;
    }

    private static boolean isDesertSurface(final BlockState state) {
        return state.is(Blocks.SAND) || state.is(Blocks.SANDSTONE);
    }

    private static boolean intersectsStructure(final ChunkAccess chunk, final int minX, final int maxX, final int minZ, final int maxZ) {
        final List<BoundingBox> boxes = new ArrayList<>();
        for (StructureStart start : chunk.getAllStarts().values()) {
            if (start != null && start.isValid()) boxes.add(start.getBoundingBox());
        }
        for (BoundingBox box : boxes) {
            if (box.maxX() >= minX && box.minX() <= maxX && box.maxZ() >= minZ && box.minZ() <= maxZ) return true;
        }
        return false;
    }

    static long mix(long n) {
        n = (n ^ (n >>> 30)) * 0xBF58476D1CE4E5B9L;
        n = (n ^ (n >>> 27)) * 0x94D049BB133111EBL;
        return n ^ (n >>> 31);
    }
}
