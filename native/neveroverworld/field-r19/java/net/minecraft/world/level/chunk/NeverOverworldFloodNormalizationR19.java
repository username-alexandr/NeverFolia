package net.minecraft.world.level.chunk;

import net.minecraft.core.BlockPos;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.WorldGenLevel;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.levelgen.Heightmap;

/**
 * FIELD-R19 final owner-chunk ocean normalization.
 *
 * <p>R15 intentionally remained chunk-local, but a six-connected component can
 * contain the Y=128 ocean seed in one chunk and not in its neighbour. The result
 * is a chunk-aligned wall of source water against dry cave air. R19 does not
 * inspect neighbouring mutable chunks. It rebuilds the actual ocean water column
 * from the immutable OCEAN_FLOOR_WG heightmap and removes only flood-created
 * water that protrudes through dry-land columns and reaches a horizontal chunk
 * seam.</p>
 *
 * <p>The normalization band is Y=-64..128. This is the same shallow band audited
 * by the accepted R15 pass and covers the reported FIELD-R18 failures without
 * changing deep-cave or deep-geology semantics.</p>
 */
public final class NeverOverworldFloodNormalizationR19 {
    static final int EXPECTED_MIN_Y = -512;
    static final int EXPECTED_HEIGHT = 1024;
    static final int FLOOD_LEVEL = 128;
    static final int SCAN_MIN_Y = -64;

    private NeverOverworldFloodNormalizationR19() {}

    public static int apply(final WorldGenLevel level, final ChunkAccess chunk) {
        if (!level.getLevel().dimension().equals(Level.OVERWORLD)
            || level.getMinY() != EXPECTED_MIN_Y
            || level.getHeight() != EXPECTED_HEIGHT) {
            return 0;
        }

        final int scanMinY = Math.max(SCAN_MIN_Y, chunk.getMinY());
        final int scanMaxY = Math.min(FLOOD_LEVEL, chunk.getMaxY() - 1);
        if (scanMinY > scanMaxY) return 0;

        final int[] firstAvailable = new int[256];
        final boolean[] dryLand = new boolean[256];
        for (int localZ = 0; localZ < 16; ++localZ) {
            for (int localX = 0; localX < 16; ++localX) {
                final int index = (localZ << 4) | localX;
                final int surface = chunk.getHeight(Heightmap.Types.OCEAN_FLOOR_WG, localX, localZ);
                firstAvailable[index] = surface;
                dryLand[index] = surface > FLOOD_LEVEL;
            }
        }

        int changed = clearProtectedMineWater(chunk, scanMinY, scanMaxY);
        changed += rebuildOceanColumns(chunk, firstAvailable, scanMinY, scanMaxY);
        changed += drainBoundaryDryLandWater(chunk, dryLand, scanMinY, scanMaxY);
        return changed;
    }

    /** Fill the guaranteed open water volume from OCEAN_FLOOR_WG+ up to Y=128. */
    static int rebuildOceanColumns(
        final ChunkAccess chunk,
        final int[] firstAvailable,
        final int minY,
        final int maxY
    ) {
        final BlockState water = Blocks.WATER.defaultBlockState();
        final int minX = chunk.getPos().getMinBlockX();
        final int minZ = chunk.getPos().getMinBlockZ();
        final BlockPos.MutableBlockPos pos = new BlockPos.MutableBlockPos();
        int changed = 0;

        for (int localZ = 0; localZ < 16; ++localZ) {
            for (int localX = 0; localX < 16; ++localX) {
                final int column = (localZ << 4) | localX;
                final int bottom = Math.max(minY, firstAvailable[column]);
                if (bottom > maxY || firstAvailable[column] > FLOOD_LEVEL) continue;

                for (int y = bottom; y <= maxY; ++y) {
                    pos.set(minX + localX, y, minZ + localZ);
                    final BlockState state = chunk.getBlockState(pos);
                    if (NeverOverworldDryMinesR12.protectedCell(chunk, pos)) {
                        if (state.is(Blocks.WATER)) {
                            chunk.setBlockState(pos, Blocks.AIR.defaultBlockState(), 0);
                            ++changed;
                        }
                        continue;
                    }
                    if (state.is(Blocks.WATER)) continue;
                    if (!NeverOverworldFloodConnectivityR15.isFloodable(state)) continue;
                    if (NeverOverworldFloodConnectivityR15.hasAdjacentLava(chunk, pos)) continue;
                    chunk.setBlockState(pos, water, 0);
                    ++changed;
                }
            }
        }
        return changed;
    }

    /**
     * Drain only pure-water components under dry-land columns that reach a
     * horizontal chunk face. These are precisely the components for which a
     * chunk-local ocean seed decision can produce a visible water/air seam.
     */
    static int drainBoundaryDryLandWater(
        final ChunkAccess chunk,
        final boolean[] dryLand,
        final int minY,
        final int maxY
    ) {
        final int layers = maxY - minY + 1;
        final int capacity = layers * 256;
        final boolean[] visited = new boolean[capacity];
        final int[] queue = new int[capacity];
        final BlockPos.MutableBlockPos pos = new BlockPos.MutableBlockPos();
        final int minX = chunk.getPos().getMinBlockX();
        final int minZ = chunk.getPos().getMinBlockZ();
        int changed = 0;

        for (int y = minY; y <= maxY; ++y) {
            for (int localZ = 0; localZ < 16; ++localZ) {
                for (int localX = 0; localX < 16; ++localX) {
                    final int column = (localZ << 4) | localX;
                    if (!dryLand[column]) continue;
                    final int seed = encode(localX, y, localZ, minY);
                    if (visited[seed]) continue;

                    pos.set(minX + localX, y, minZ + localZ);
                    if (!chunk.getBlockState(pos).is(Blocks.WATER)) {
                        visited[seed] = true;
                        continue;
                    }

                    int head = 0;
                    int tail = 0;
                    boolean touchesHorizontalBoundary = false;
                    visited[seed] = true;
                    queue[tail++] = seed;

                    while (head < tail) {
                        final int encoded = queue[head++];
                        final int x = encoded & 15;
                        final int z = (encoded >>> 4) & 15;
                        final int cy = minY + (encoded >>> 8);
                        if (x == 0 || x == 15 || z == 0 || z == 15) {
                            touchesHorizontalBoundary = true;
                        }
                        tail = enqueueWater(chunk, dryLand, queue, visited, tail, x - 1, cy, z, minX, minZ, minY, maxY);
                        tail = enqueueWater(chunk, dryLand, queue, visited, tail, x + 1, cy, z, minX, minZ, minY, maxY);
                        tail = enqueueWater(chunk, dryLand, queue, visited, tail, x, cy, z - 1, minX, minZ, minY, maxY);
                        tail = enqueueWater(chunk, dryLand, queue, visited, tail, x, cy, z + 1, minX, minZ, minY, maxY);
                        tail = enqueueWater(chunk, dryLand, queue, visited, tail, x, cy - 1, z, minX, minZ, minY, maxY);
                        tail = enqueueWater(chunk, dryLand, queue, visited, tail, x, cy + 1, z, minX, minZ, minY, maxY);
                    }

                    if (!touchesHorizontalBoundary) continue;
                    for (int i = 0; i < tail; ++i) {
                        final int encoded = queue[i];
                        final int x = encoded & 15;
                        final int z = (encoded >>> 4) & 15;
                        final int cy = minY + (encoded >>> 8);
                        pos.set(minX + x, cy, minZ + z);
                        if (chunk.getBlockState(pos).is(Blocks.WATER)) {
                            chunk.setBlockState(pos, Blocks.AIR.defaultBlockState(), 0);
                            ++changed;
                        }
                    }
                }
            }
        }
        return changed;
    }

    private static int clearProtectedMineWater(final ChunkAccess chunk, final int minY, final int maxY) {
        final int minX = chunk.getPos().getMinBlockX();
        final int minZ = chunk.getPos().getMinBlockZ();
        final BlockPos.MutableBlockPos pos = new BlockPos.MutableBlockPos();
        int changed = 0;
        for (int y = minY; y <= maxY; ++y) {
            for (int localZ = 0; localZ < 16; ++localZ) {
                for (int localX = 0; localX < 16; ++localX) {
                    pos.set(minX + localX, y, minZ + localZ);
                    if (chunk.getBlockState(pos).is(Blocks.WATER)
                        && NeverOverworldDryMinesR12.protectedCell(chunk, pos)) {
                        chunk.setBlockState(pos, Blocks.AIR.defaultBlockState(), 0);
                        ++changed;
                    }
                }
            }
        }
        return changed;
    }

    private static int enqueueWater(
        final ChunkAccess chunk,
        final boolean[] dryLand,
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
        if (!dryLand[(localZ << 4) | localX]) return tail;
        final int encoded = encode(localX, y, localZ, minY);
        if (visited[encoded]) return tail;
        final BlockPos pos = new BlockPos(minX + localX, y, minZ + localZ);
        if (!chunk.getBlockState(pos).is(Blocks.WATER)) {
            visited[encoded] = true;
            return tail;
        }
        visited[encoded] = true;
        queue[tail++] = encoded;
        return tail;
    }

    private static int encode(final int x, final int y, final int z, final int minY) {
        return ((y - minY) << 8) | (z << 4) | x;
    }
}
