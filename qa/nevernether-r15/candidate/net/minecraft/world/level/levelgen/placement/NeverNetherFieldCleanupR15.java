package net.minecraft.world.level.levelgen.placement;

import java.util.ArrayDeque;
import java.util.HashMap;
import java.util.Map;
import net.minecraft.core.BlockPos;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.WorldGenLevel;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.chunk.ChunkAccess;
import net.minecraft.world.level.chunk.status.ChunkStatus;

/**
 * R15 field cleanup for defects proven to exist in the immutable CARVERS
 * substrate before R10 capture.
 *
 * <p>Only owner-chunk state is inspected. Tiny fully enclosed air components
 * of at most four blocks are filled only when every known boundary block is
 * natural Nether rock and the component never touches a chunk/Y boundary.
 * Unsupported source-lava shelf cells are solidified only when the cell has air
 * below and at least two horizontal source-lava neighbours. Large caves,
 * boundary-connected air and lavafall/edge cells are preserved.</p>
 */
public final class NeverNetherFieldCleanupR15 {
    static final int MIN_Y = -128;
    static final int MAX_Y = 511;
    static final int MAX_MICRO_POCKET = 4;
    private static final int[][] DIRECTIONS = {
        {1,0,0},{-1,0,0},{0,1,0},{0,-1,0},{0,0,1},{0,0,-1}
    };

    private NeverNetherFieldCleanupR15() {}

    public static Result clean(final ChunkAccess chunk) {
        validateEnvelope(chunk);
        final int pockets = fillMicroPockets(chunk, false);
        final int shelves = solidifyHangingLava(chunk);
        return new Result(pockets, shelves);
    }

    public static Result afterFeatures(final WorldGenLevel level, final ChunkAccess chunk) {
        if (!level.getLevel().dimension().equals(Level.NETHER)
            || level.getMinY() != MIN_Y
            || level.getHeight() != NeverNetherHeightR14.HEIGHT
            || chunk.getPersistedStatus().isOrAfter(ChunkStatus.FULL)
            || chunk.hasAnyStructureReferences()) {
            return new Result(0, 0);
        }
        validateEnvelope(chunk);
        return new Result(fillMicroPockets(chunk, true), 0);
    }

    private static void validateEnvelope(final ChunkAccess chunk) {
        if (chunk.getMinY() != MIN_Y || chunk.getMaxY() < MAX_Y + 1) {
            throw new IllegalStateException("R15 cleanup requires the NeverNether -128..511 generated body");
        }
    }

    static int fillMicroPockets(final ChunkAccess chunk) {
        return fillMicroPockets(chunk, false);
    }

    static int fillMicroPocketsPublished(final ChunkAccess chunk) {
        return fillMicroPockets(chunk, true);
    }

    private static int fillMicroPockets(final ChunkAccess chunk, final boolean published) {
        final int height = MAX_Y - MIN_Y + 1;
        final boolean[] visited = new boolean[height * 256];
        final int baseX = chunk.getPos().getMinBlockX();
        final int baseZ = chunk.getPos().getMinBlockZ();
        final BlockPos.MutableBlockPos pos = new BlockPos.MutableBlockPos();
        int changed = 0;

        for (int y = MIN_Y; y <= MAX_Y; ++y) {
            for (int lz = 0; lz < 16; ++lz) {
                for (int lx = 0; lx < 16; ++lx) {
                    final int startIndex = index(lx, y, lz);
                    if (visited[startIndex]) continue;
                    pos.set(baseX + lx, y, baseZ + lz);
                    if (!chunk.getBlockState(pos).isAir()) continue;

                    final ArrayDeque<Cell> queue = new ArrayDeque<>();
                    final java.util.ArrayList<Cell> cells = new java.util.ArrayList<>(MAX_MICRO_POCKET + 1);
                    final Map<BlockState,Integer> boundary = new HashMap<>();
                    boolean safe = true;
                    queue.add(new Cell(lx,y,lz));
                    visited[startIndex] = true;

                    while (!queue.isEmpty()) {
                        final Cell cell = queue.removeFirst();
                        if (cells.size() <= MAX_MICRO_POCKET) cells.add(cell);
                        if (cell.x == 0 || cell.x == 15 || cell.z == 0 || cell.z == 15
                            || cell.y == MIN_Y || cell.y == MAX_Y) {
                            safe = false;
                        }
                        for (int[] d : DIRECTIONS) {
                            final int nx = cell.x + d[0];
                            final int ny = cell.y + d[1];
                            final int nz = cell.z + d[2];
                            if (nx < 0 || nx > 15 || nz < 0 || nz > 15 || ny < MIN_Y || ny > MAX_Y) {
                                safe = false;
                                continue;
                            }
                            pos.set(baseX + nx, ny, baseZ + nz);
                            final BlockState adjacent = chunk.getBlockState(pos);
                            if (adjacent.isAir()) {
                                final int nextIndex = index(nx,ny,nz);
                                if (!visited[nextIndex]) {
                                    visited[nextIndex] = true;
                                    queue.addLast(new Cell(nx,ny,nz));
                                }
                            } else if (isNaturalRock(adjacent)) {
                                if (isFillMaterial(adjacent)) boundary.merge(adjacent,1,Integer::sum);
                            } else {
                                safe = false;
                            }
                        }
                    }

                    if (!safe || cells.isEmpty() || cells.size() > MAX_MICRO_POCKET) continue;
                    final BlockState replacement = chooseFill(boundary);
                    for (Cell cell : cells) {
                        write(chunk, cell.x, cell.y, cell.z, replacement, published, pos);
                        ++changed;
                    }
                }
            }
        }
        return changed;
    }

    static int solidifyHangingLava(final ChunkAccess chunk) {
        final int baseX = chunk.getPos().getMinBlockX();
        final int baseZ = chunk.getPos().getMinBlockZ();
        final BlockPos.MutableBlockPos pos = new BlockPos.MutableBlockPos();
        int changed = 0;
        for (int y = MIN_Y + 1; y < MAX_Y; ++y) {
            for (int lz = 0; lz < 16; ++lz) {
                for (int lx = 0; lx < 16; ++lx) {
                    pos.set(baseX + lx, y, baseZ + lz);
                    final BlockState state = chunk.getBlockState(pos);
                    if (!sourceLava(state)) continue;
                    pos.set(baseX + lx, y - 1, baseZ + lz);
                    if (!chunk.getBlockState(pos).isAir()) continue;
                    int horizontal = 0;
                    for (int[] d : new int[][]{{1,0},{-1,0},{0,1},{0,-1}}) {
                        final int nx = lx + d[0];
                        final int nz = lz + d[1];
                        if (nx < 0 || nx > 15 || nz < 0 || nz > 15) continue;
                        pos.set(baseX + nx, y, baseZ + nz);
                        if (sourceLava(chunk.getBlockState(pos))) ++horizontal;
                    }
                    if (horizontal < 2) continue;
                    final BlockState replacement = surroundingRock(chunk, lx, y, lz, pos);
                    directSet(chunk, lx, y, lz, replacement);
                    ++changed;
                }
            }
        }
        return changed;
    }

    private static void write(
        final ChunkAccess chunk,
        final int localX,
        final int y,
        final int localZ,
        final BlockState state,
        final boolean published,
        final BlockPos.MutableBlockPos pos
    ) {
        if (!published) {
            directSet(chunk, localX, y, localZ, state);
            return;
        }
        pos.set(chunk.getPos().getMinBlockX() + localX, y, chunk.getPos().getMinBlockZ() + localZ);
        chunk.setBlockState(pos, state, 0);
    }

    private static void directSet(
        final ChunkAccess chunk,
        final int localX,
        final int y,
        final int localZ,
        final BlockState state
    ) {
        final var section = chunk.getSection(chunk.getSectionIndex(y));
        section.getStates().set(localX & 15, y & 15, localZ & 15, state);
        section.recalcBlockCounts();
    }

    static boolean sourceLava(final BlockState state) {
        return state.is(Blocks.LAVA) && state.getFluidState().isSource();
    }

    static boolean isNaturalRock(final BlockState state) {
        return state.is(Blocks.NETHERRACK)
            || state.is(Blocks.BASALT)
            || state.is(Blocks.SMOOTH_BASALT)
            || state.is(Blocks.BLACKSTONE)
            || state.is(Blocks.MAGMA_BLOCK)
            || state.is(Blocks.SOUL_SAND)
            || state.is(Blocks.SOUL_SOIL)
            || state.is(Blocks.CRIMSON_NYLIUM)
            || state.is(Blocks.WARPED_NYLIUM)
            || state.is(Blocks.NETHER_QUARTZ_ORE)
            || state.is(Blocks.NETHER_GOLD_ORE)
            || state.is(Blocks.ANCIENT_DEBRIS)
            || state.is(Blocks.GRAVEL)
            || state.is(Blocks.BEDROCK);
    }

    private static boolean isFillMaterial(final BlockState state) {
        return !state.is(Blocks.NETHER_QUARTZ_ORE)
            && !state.is(Blocks.NETHER_GOLD_ORE)
            && !state.is(Blocks.ANCIENT_DEBRIS)
            && !state.is(Blocks.BEDROCK);
    }

    private static BlockState chooseFill(final Map<BlockState,Integer> counts) {
        BlockState best = Blocks.NETHERRACK.defaultBlockState();
        int bestCount = -1;
        int bestId = Integer.MAX_VALUE;
        for (var entry : counts.entrySet()) {
            final int id = Block.getId(entry.getKey());
            final int count = entry.getValue();
            if (count > bestCount || count == bestCount && id < bestId) {
                best = entry.getKey();
                bestCount = count;
                bestId = id;
            }
        }
        return best;
    }

    private static BlockState surroundingRock(
        final ChunkAccess chunk,
        final int lx,
        final int y,
        final int lz,
        final BlockPos.MutableBlockPos pos
    ) {
        final int baseX = chunk.getPos().getMinBlockX();
        final int baseZ = chunk.getPos().getMinBlockZ();
        final Map<BlockState,Integer> counts = new HashMap<>();
        for (int dy = -1; dy <= 1; ++dy) {
            for (int dz = -1; dz <= 1; ++dz) {
                for (int dx = -1; dx <= 1; ++dx) {
                    if (dx == 0 && dy == 0 && dz == 0) continue;
                    final int nx = lx + dx;
                    final int ny = y + dy;
                    final int nz = lz + dz;
                    if (nx < 0 || nx > 15 || nz < 0 || nz > 15 || ny < MIN_Y || ny > MAX_Y) continue;
                    pos.set(baseX + nx, ny, baseZ + nz);
                    final BlockState state = chunk.getBlockState(pos);
                    if (isNaturalRock(state) && isFillMaterial(state)) counts.merge(state,1,Integer::sum);
                }
            }
        }
        return chooseFill(counts);
    }

    private static int index(final int x, final int y, final int z) {
        return (y - MIN_Y) * 256 + z * 16 + x;
    }

    private record Cell(int x,int y,int z) {}
    public record Result(int microPocketBlocksFilled,int hangingLavaCellsSolidified) {}
}
