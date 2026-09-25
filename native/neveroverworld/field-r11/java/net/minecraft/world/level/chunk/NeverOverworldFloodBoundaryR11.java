package net.minecraft.world.level.chunk;

import java.util.ArrayList;
import java.util.List;
import net.minecraft.core.BlockPos;
import net.minecraft.tags.BlockTags;
import net.minecraft.world.level.ChunkPos;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.WorldGenLevel;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.levelgen.structure.BoundingBox;
import net.minecraft.world.level.levelgen.structure.StructureStart;

/**
 * FIELD-R11 shallow cross-chunk flood continuity.
 *
 * <p>R9 deliberately keeps the LIGHT flood owner-chunk-only. That makes a cave
 * whose real water path crosses a chunk edge possible to persist as water on
 * one side and air on the other. The user-seed 15x15 audit found 2,555 such
 * border cells. A graph audit showed that 1,575,886 dry boundary-component
 * blocks are connected through neighbouring chunk faces to already wet
 * components, versus 12,641 blocks in disconnected boundary components.</p>
 *
 * <p>This policy therefore treats every floodable component that reaches a
 * horizontal chunk face in Y=-64..127 as part of the flooded shallow cavern
 * network. It never reads or writes a neighbour chunk, so opposite request
 * orders cannot change the decision. Valid structure-start boxes in the owner
 * chunk are barriers and are not overwritten.</p>
 *
 * <p>This is an explicit flooded-world rule, not vanilla cave semantics. Deep
 * caves below -64 and components fully enclosed inside one chunk stay dry.</p>
 */
public final class NeverOverworldFloodBoundaryR11 {
    static final int SCAN_MIN_Y = -64;
    static final int SCAN_MAX_Y = 127;

    private NeverOverworldFloodBoundaryR11() {}

    public static int apply(final WorldGenLevel level, final ChunkAccess chunk) {
        if (!level.getLevel().dimension().equals(Level.OVERWORLD)
            || level.getMinY() != -512
            || level.getHeight() != 1024) {
            return 0;
        }
        return floodBoundaryComponents(chunk);
    }

    static int floodBoundaryComponents(final ChunkAccess chunk) {
        if (chunk.getMinY() != -512 || chunk.getHeight() != 1024) {
            throw new IllegalStateException("FIELD-R11 requires NeverOverworld -512..511 envelope");
        }
        final int minY = Math.max(SCAN_MIN_Y, chunk.getMinY() + 1);
        final int maxY = Math.min(SCAN_MAX_Y, chunk.getMaxY() - 1);
        final int layerCount = maxY - minY + 1;
        if (layerCount <= 0) return 0;

        final int capacity = layerCount * 256;
        final boolean[] visited = new boolean[capacity];
        final int[] queue = new int[capacity];
        final List<BoundingBox> protectedBoxes = protectionBoxes(chunk);
        final ChunkPos cp = chunk.getPos();
        final int minX = cp.getMinBlockX();
        final int minZ = cp.getMinBlockZ();
        final BlockPos.MutableBlockPos pos = new BlockPos.MutableBlockPos();
        final BlockState water = Blocks.WATER.defaultBlockState();
        int changed = 0;

        for (int y = minY; y <= maxY; ++y) {
            for (int edge = 0; edge < 16; ++edge) {
                changed += floodFromSeed(chunk, protectedBoxes, visited, queue, 0, y, edge, minX, minZ, minY, maxY, pos, water);
                changed += floodFromSeed(chunk, protectedBoxes, visited, queue, 15, y, edge, minX, minZ, minY, maxY, pos, water);
                changed += floodFromSeed(chunk, protectedBoxes, visited, queue, edge, y, 0, minX, minZ, minY, maxY, pos, water);
                changed += floodFromSeed(chunk, protectedBoxes, visited, queue, edge, y, 15, minX, minZ, minY, maxY, pos, water);
            }
        }
        return changed;
    }

    private static int floodFromSeed(
        final ChunkAccess chunk,
        final List<BoundingBox> protectedBoxes,
        final boolean[] visited,
        final int[] queue,
        final int seedX,
        final int seedY,
        final int seedZ,
        final int minX,
        final int minZ,
        final int minY,
        final int maxY,
        final BlockPos.MutableBlockPos pos,
        final BlockState water
    ) {
        final int seed = encode(seedX, seedY, seedZ, minY);
        if (visited[seed]) return 0;
        final int worldX = minX + seedX;
        final int worldZ = minZ + seedZ;
        pos.set(worldX, seedY, worldZ);
        if (!isFloodable(chunk.getBlockState(pos)) || isProtected(protectedBoxes, worldX, seedY, worldZ)) {
            visited[seed] = true;
            return 0;
        }

        int head = 0;
        int tail = 0;
        visited[seed] = true;
        queue[tail++] = seed;
        while (head < tail) {
            final int encoded = queue[head++];
            final int x = encoded & 15;
            final int z = (encoded >>> 4) & 15;
            final int y = minY + (encoded >>> 8);
            tail = enqueue(chunk, protectedBoxes, visited, queue, tail, x - 1, y, z, minX, minZ, minY, maxY);
            tail = enqueue(chunk, protectedBoxes, visited, queue, tail, x + 1, y, z, minX, minZ, minY, maxY);
            tail = enqueue(chunk, protectedBoxes, visited, queue, tail, x, y, z - 1, minX, minZ, minY, maxY);
            tail = enqueue(chunk, protectedBoxes, visited, queue, tail, x, y, z + 1, minX, minZ, minY, maxY);
            tail = enqueue(chunk, protectedBoxes, visited, queue, tail, x, y - 1, z, minX, minZ, minY, maxY);
            tail = enqueue(chunk, protectedBoxes, visited, queue, tail, x, y + 1, z, minX, minZ, minY, maxY);
        }

        int changed = 0;
        for (int i = 0; i < tail; ++i) {
            final int encoded = queue[i];
            final int x = encoded & 15;
            final int z = (encoded >>> 4) & 15;
            final int y = minY + (encoded >>> 8);
            final int worldX2 = minX + x;
            final int worldZ2 = minZ + z;
            if (isProtected(protectedBoxes, worldX2, y, worldZ2)) continue;
            pos.set(worldX2, y, worldZ2);
            final BlockState state = chunk.getBlockState(pos);
            if (isFloodable(state) && !state.is(Blocks.WATER)) {
                chunk.setBlockState(pos, water, 0);
                ++changed;
            }
        }
        return changed;
    }

    private static int enqueue(
        final ChunkAccess chunk,
        final List<BoundingBox> protectedBoxes,
        final boolean[] visited,
        final int[] queue,
        int tail,
        final int localX,
        final int y,
        final int localZ,
        final int minX,
        final int minZ,
        final int minY,
        final int maxY
    ) {
        if (localX < 0 || localX > 15 || localZ < 0 || localZ > 15 || y < minY || y > maxY) return tail;
        final int encoded = encode(localX, y, localZ, minY);
        if (visited[encoded]) return tail;
        final int x = minX + localX;
        final int z = minZ + localZ;
        final BlockPos pos = new BlockPos(x, y, z);
        if (!isFloodable(chunk.getBlockState(pos)) || isProtected(protectedBoxes, x, y, z)) {
            visited[encoded] = true;
            return tail;
        }
        visited[encoded] = true;
        queue[tail++] = encoded;
        return tail;
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

    private static List<BoundingBox> protectionBoxes(final ChunkAccess chunk) {
        final ArrayList<BoundingBox> result = new ArrayList<>();
        for (StructureStart start : chunk.getAllStarts().values()) {
            if (start != null && start.isValid()) result.add(start.getBoundingBox());
        }
        return result;
    }

    private static boolean isProtected(final List<BoundingBox> boxes, final int x, final int y, final int z) {
        for (BoundingBox box : boxes) {
            if (x >= box.minX() - 1 && x <= box.maxX() + 1
                && y >= box.minY() - 1 && y <= box.maxY() + 1
                && z >= box.minZ() - 1 && z <= box.maxZ() + 1) return true;
        }
        return false;
    }

    private static int encode(final int localX, final int y, final int localZ, final int minY) {
        return ((y - minY) << 8) | (localZ << 4) | localX;
    }
}
