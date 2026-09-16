package net.minecraft.world.level.levelgen.structure;

import java.util.List;
import net.minecraft.core.BlockPos;
import net.minecraft.core.registries.Registries;
import net.minecraft.world.level.ChunkPos;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.WorldGenLevel;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.chunk.ChunkAccess;

/**
 * NeverFolia field fix: village reclamation without rectangular village slabs.
 *
 * <p>Only columns that contain an actual generated village piece are eligible.
 * Support is local to each piece footprint, clipped to the owning chunk, and
 * requires natural/structure support within a bounded depth. The old whole-start
 * bounding-box fill and unconditional Y=80 fallback are deliberately removed.</p>
 */
public final class NeverOverworldVillageReclamation {
    private static final int EXPECTED_MIN_Y = -512;
    private static final int EXPECTED_HEIGHT = 1024;
    private static final int FLOOD_LEVEL = 128;
    private static final int MAX_FOUNDATION_DEPTH = 24;
    private static final int MAX_STRUCTURE_SCAN_ABOVE = 24;
    private static final boolean DEBUG = Boolean.getBoolean("neverfolia.debugVillageReclamation");

    private NeverOverworldVillageReclamation() {}

    public static void apply(final WorldGenLevel level, final StructureStart start, final ChunkPos chunkPos) {
        if (!level.getLevel().dimension().equals(Level.OVERWORLD)
            || level.getMinY() != EXPECTED_MIN_Y
            || level.getHeight() != EXPECTED_HEIGHT
            || start == null
            || !start.isValid()) {
            return;
        }

        final String structureId = String.valueOf(
            level.registryAccess().lookupOrThrow(Registries.STRUCTURE).getKey(start.getStructure())
        );
        if (!isVillage(structureId)) {
            return;
        }

        final ChunkAccess chunk = level.getChunk(chunkPos.x(), chunkPos.z());
        final int chunkMinX = chunkPos.getMinBlockX();
        final int chunkMinZ = chunkPos.getMinBlockZ();
        final int chunkMaxX = chunkMinX + 15;
        final int chunkMaxZ = chunkMinZ + 15;
        final BlockPos.MutableBlockPos pos = new BlockPos.MutableBlockPos();
        final boolean[] processed = new boolean[256];
        final boolean desert = "minecraft:village_desert".equals(structureId);
        final BlockState cap = desert ? Blocks.SAND.defaultBlockState() : Blocks.GRASS_BLOCK.defaultBlockState();
        final BlockState shallowFill = desert ? Blocks.SANDSTONE.defaultBlockState() : Blocks.DIRT.defaultBlockState();
        final BlockState deepFill = Blocks.STONE.defaultBlockState();

        int eligibleColumns = 0;
        int supportedColumns = 0;
        int changedBlocks = 0;
        for (StructurePiece piece : start.getPieces()) {
            final BoundingBox box = piece.getBoundingBox();
            if (box.maxX() < chunkMinX || box.minX() > chunkMaxX || box.maxZ() < chunkMinZ || box.minZ() > chunkMaxZ) {
                continue;
            }
            final int minX = Math.max(box.minX(), chunkMinX);
            final int maxX = Math.min(box.maxX(), chunkMaxX);
            final int minZ = Math.max(box.minZ(), chunkMinZ);
            final int maxZ = Math.min(box.maxZ(), chunkMinZ);
            for (int z = minZ; z <= maxZ; ++z) {
                for (int x = minX; x <= maxX; ++x) {
                    final int index = ((z - chunkMinZ) << 4) | (x - chunkMinX);
                    if (processed[index]) continue;
                    if (!pieceOccupiesColumn(chunk, box, x, z, pos)) continue;
                    processed[index] = true;
                    ++eligibleColumns;

                    final int baseY = findNaturalSupport(chunk, x, z, pos);
                    if (baseY == Integer.MIN_VALUE) {
                        continue;
                    }
                    boolean changed = false;
                    for (int y = baseY + 1; y <= FLOOD_LEVEL; ++y) {
                        pos.set(x, y, z);
                        final BlockState existing = chunk.getBlockState(pos);
                        if (!fillable(existing)) continue;
                        final BlockState fill = y == FLOOD_LEVEL
                            ? cap
                            : (y >= FLOOD_LEVEL - 3 ? shallowFill : deepFill);
                        chunk.setBlockState(pos, fill, 0);
                        ++changedBlocks;
                        changed = true;
                    }
                    if (changed) ++supportedColumns;
                }
            }
        }

        if (DEBUG && (eligibleColumns > 0 || changedBlocks > 0)) {
            System.out.println(
                "[NeverFolia][FIELD_VILLAGE_FOUNDATION] structure=" + structureId
                    + " chunk=" + chunkPos.x() + "," + chunkPos.z()
                    + " eligible=" + eligibleColumns
                    + " supported=" + supportedColumns
                    + " blocks=" + changedBlocks
            );
        }
    }

    static boolean pieceOccupiesColumn(
        final ChunkAccess chunk,
        final BoundingBox box,
        final int x,
        final int z,
        final BlockPos.MutableBlockPos pos
    ) {
        final int top = Math.min(box.maxY(), FLOOD_LEVEL + MAX_STRUCTURE_SCAN_ABOVE);
        final int bottom = Math.max(box.minY(), FLOOD_LEVEL);
        if (bottom > top) return false;
        for (int y = bottom; y <= top; ++y) {
            pos.set(x, y, z);
            if (!fillable(chunk.getBlockState(pos))) return true;
        }
        return false;
    }

    static int findNaturalSupport(
        final ChunkAccess chunk,
        final int x,
        final int z,
        final BlockPos.MutableBlockPos pos
    ) {
        final int minY = FLOOD_LEVEL - MAX_FOUNDATION_DEPTH;
        for (int y = FLOOD_LEVEL - 1; y >= minY; --y) {
            pos.set(x, y, z);
            if (!fillable(chunk.getBlockState(pos))) return y;
        }
        return Integer.MIN_VALUE;
    }

    private static boolean fillable(final BlockState state) {
        return state.isAir()
            || state.is(Blocks.WATER)
            || state.is(Blocks.LAVA)
            || state.canBeReplaced();
    }

    private static boolean isVillage(final String id) {
        return "minecraft:village_plains".equals(id)
            || "minecraft:village_desert".equals(id)
            || "minecraft:village_savanna".equals(id)
            || "minecraft:village_snowy".equals(id)
            || "minecraft:village_taiga".equals(id);
    }
}
