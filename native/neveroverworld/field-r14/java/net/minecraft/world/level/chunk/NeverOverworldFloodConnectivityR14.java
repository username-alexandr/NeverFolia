package net.minecraft.world.level.chunk;

import net.minecraft.core.BlockPos;
import net.minecraft.tags.BlockTags;
import net.minecraft.world.level.ChunkPos;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.WorldGenLevel;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.BlockState;

/**
 * FIELD-R14 conservative cross-chunk flood continuity.
 *
 * <p>R11 treated every shallow component touching a horizontal chunk face as
 * ocean-connected. That can flood sealed caves/mineshafts merely because they
 * cross a chunk border. R14 only extends components that already contain source
 * water created by the verified surface-ocean flood in this owner chunk.</p>
 *
 * <p>Cells touching lava on any in-chunk face are barriers: no water is written
 * there and flood traversal does not pass through them. No neighbour chunk is
 * read or written, preserving Folia chunk-order independence.</p>
 */
public final class NeverOverworldFloodConnectivityR14 {
    static final int SCAN_MIN_Y = -64;
    static final int SCAN_MAX_Y = 127;

    private NeverOverworldFloodConnectivityR14() {}

    public static int apply(final WorldGenLevel level, final ChunkAccess chunk) {
        if (!level.getLevel().dimension().equals(Level.OVERWORLD)
            || level.getMinY() != -512
            || level.getHeight() != 1024) {
            return 0;
        }
        return floodVerifiedBoundaryComponents(chunk);
    }

    static int floodVerifiedBoundaryComponents(final ChunkAccess chunk) {
        final int minY = Math.max(SCAN_MIN_Y, chunk.getMinY() + 1);
        final int maxY = Math.min(SCAN_MAX_Y, chunk.getMaxY() - 1);
        final int layers = maxY - minY + 1;
        if (layers <= 0) return 0;

        final int capacity = layers * 256;
        final boolean[] visited = new boolean[capacity];
        final int[] queue = new int[capacity];
        int changed = 0;

        for (int y = minY; y <= maxY; ++y) {
            for (int edge = 0; edge < 16; ++edge) {
                changed += scan(chunk, visited, queue, 0, y, edge, minY, maxY);
                changed += scan(chunk, visited, queue, 15, y, edge, minY, maxY);
                changed += scan(chunk, visited, queue, edge, y, 0, minY, maxY);
                changed += scan(chunk, visited, queue, edge, y, 15, minY, maxY);
            }
        }
        return changed;
    }

    private static int scan(
        final ChunkAccess chunk,
        final boolean[] visited,
        final int[] queue,
        final int seedX,
        final int seedY,
        final int seedZ,
        final int minY,
        final int maxY
    ) {
        final int seed = encode(seedX, seedY, seedZ, minY);
        if (visited[seed]) return 0;

        final ChunkPos cp = chunk.getPos();
        final int baseX = cp.getMinBlockX();
        final int baseZ = cp.getMinBlockZ();
        final BlockPos.MutableBlockPos pos = new BlockPos.MutableBlockPos();
        pos.set(baseX + seedX, seedY, baseZ + seedZ);
        if (!traversable(chunk, pos)) {
            visited[seed] = true;
            return 0;
        }

        int head = 0;
        int tail = 0;
        boolean hasWaterSeed = false;
        visited[seed] = true;
        queue[tail++] = seed;

        while (head < tail) {
            final int encoded = queue[head++];
            final int lx = encoded & 15;
            final int lz = (encoded >>> 4) & 15;
            final int y = minY + (encoded >>> 8);
            pos.set(baseX + lx, y, baseZ + lz);
            if (chunk.getBlockState(pos).is(Blocks.WATER)) hasWaterSeed = true;

            tail = enqueue(chunk, visited, queue, tail, lx - 1, y, lz, minY, maxY);
            tail = enqueue(chunk, visited, queue, tail, lx + 1, y, lz, minY, maxY);
            tail = enqueue(chunk, visited, queue, tail, lx, y, lz - 1, minY, maxY);
            tail = enqueue(chunk, visited, queue, tail, lx, y, lz + 1, minY, maxY);
            tail = enqueue(chunk, visited, queue, tail, lx, y - 1, lz, minY, maxY);
            tail = enqueue(chunk, visited, queue, tail, lx, y + 1, lz, minY, maxY);
        }

        if (!hasWaterSeed) return 0;

        int changed = 0;
        final BlockState water = Blocks.WATER.defaultBlockState();
        for (int i = 0; i < tail; ++i) {
            final int encoded = queue[i];
            final int lx = encoded & 15;
            final int lz = (encoded >>> 4) & 15;
            final int y = minY + (encoded >>> 8);
            pos.set(baseX + lx, y, baseZ + lz);
            final BlockState state = chunk.getBlockState(pos);
            if (!state.is(Blocks.WATER) && traversable(chunk, pos)) {
                chunk.setBlockState(pos, water, 0);
                ++changed;
            }
        }
        return changed;
    }

    private static int enqueue(
        final ChunkAccess chunk,
        final boolean[] visited,
        final int[] queue,
        int tail,
        final int lx,
        final int y,
        final int lz,
        final int minY,
        final int maxY
    ) {
        if (lx < 0 || lx > 15 || lz < 0 || lz > 15 || y < minY || y > maxY) return tail;
        final int encoded = encode(lx, y, lz, minY);
        if (visited[encoded]) return tail;
        final BlockPos pos = new BlockPos(
            chunk.getPos().getMinBlockX() + lx,
            y,
            chunk.getPos().getMinBlockZ() + lz
        );
        visited[encoded] = true;
        if (!traversable(chunk, pos)) return tail;
        queue[tail++] = encoded;
        return tail;
    }

    static boolean traversable(final ChunkAccess chunk, final BlockPos pos) {
        if (NeverOverworldDryMinesR12.protectedCell(chunk, pos)) return false;
        final BlockState state = chunk.getBlockState(pos);
        return isFloodable(state) && !hasAdjacentLava(chunk, pos);
    }

    static boolean hasAdjacentLava(final ChunkAccess chunk, final BlockPos pos) {
        final int minX = chunk.getPos().getMinBlockX();
        final int minZ = chunk.getPos().getMinBlockZ();
        final int x = pos.getX(), y = pos.getY(), z = pos.getZ();
        final BlockPos.MutableBlockPos probe = new BlockPos.MutableBlockPos();
        final int[][] d = {{1,0,0},{-1,0,0},{0,1,0},{0,-1,0},{0,0,1},{0,0,-1}};
        for (int[] v : d) {
            final int nx=x+v[0], ny=y+v[1], nz=z+v[2];
            if (nx < minX || nx > minX + 15 || nz < minZ || nz > minZ + 15
                || ny < chunk.getMinY() || ny >= chunk.getMaxY()) continue;
            probe.set(nx,ny,nz);
            if (chunk.getBlockState(probe).is(Blocks.LAVA)) return true;
        }
        return false;
    }

    static boolean isFloodable(final BlockState state) {
        return state.isAir()
            || state.is(Blocks.WATER)
            || (state.getFluidState().isEmpty() && state.canBeReplaced())
            || state.is(BlockTags.RAILS)
            || state.is(Blocks.SUGAR_CANE)
            || state.is(Blocks.LILY_PAD)
            || state.is(Blocks.MUSHROOM_STEM)
            || state.is(Blocks.RED_MUSHROOM_BLOCK)
            || state.is(Blocks.BROWN_MUSHROOM_BLOCK);
    }

    private static int encode(final int x, final int y, final int z, final int minY) {
        return ((y - minY) << 8) | (z << 4) | x;
    }
}
