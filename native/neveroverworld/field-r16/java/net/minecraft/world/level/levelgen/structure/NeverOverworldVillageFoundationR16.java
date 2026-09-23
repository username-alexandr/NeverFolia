package net.minecraft.world.level.levelgen.structure;

import net.minecraft.core.BlockPos;
import net.minecraft.core.registries.Registries;
import net.minecraft.world.level.ChunkPos;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.WorldGenLevel;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.chunk.ChunkAccess;

/**
 * FIELD-R16 local village foundations.
 *
 * <p>VILLAGE-NOFILL remains authoritative: this never reclaims a village bbox
 * or fills terrain to the Y=128 ocean. It only repairs short unsupported gaps
 * directly beneath columns that demonstrably contain a placed village piece.</p>
 */
public final class NeverOverworldVillageFoundationR16 {
    static final int MAX_SUPPORT_DEPTH = 10;
    static final int PIECE_FLOOR_SCAN = 4;
    static final int STRUCTURE_EVIDENCE_SCAN = 8;

    private NeverOverworldVillageFoundationR16() {}

    public static int apply(final WorldGenLevel level, final StructureStart start, final ChunkPos owner) {
        if (!level.getLevel().dimension().equals(Level.OVERWORLD)
            || level.getMinY() != -512 || level.getHeight() != 1024
            || start == null || !start.isValid()) return 0;

        final String id = String.valueOf(
            level.registryAccess().lookupOrThrow(Registries.STRUCTURE).getKey(start.getStructure())
        );
        if (!id.startsWith("minecraft:village_")) return 0;

        final ChunkAccess chunk = level.getChunk(owner.x(), owner.z());
        final int minX = owner.getMinBlockX(), minZ = owner.getMinBlockZ();
        final int maxX = minX + 15, maxZ = minZ + 15;
        final boolean desert = "minecraft:village_desert".equals(id);
        final BlockState fill = desert ? Blocks.SANDSTONE.defaultBlockState() : Blocks.COBBLESTONE.defaultBlockState();
        final boolean[] done = new boolean[256];
        final BlockPos.MutableBlockPos pos = new BlockPos.MutableBlockPos();
        int changed = 0;

        for (final StructurePiece piece : start.getPieces()) {
            final BoundingBox box = piece.getBoundingBox();
            if (box.maxX() < minX || box.minX() > maxX || box.maxZ() < minZ || box.minZ() > maxZ) continue;
            final int ax = Math.max(minX, box.minX()), bx = Math.min(maxX, box.maxX());
            final int az = Math.max(minZ, box.minZ()), bz = Math.min(maxZ, box.maxZ());

            for (int z = az; z <= bz; ++z) for (int x = ax; x <= bx; ++x) {
                final int index = ((z - minZ) << 4) | (x - minX);
                if (done[index]) continue;

                final int floorY = placedFloorY(chunk, box, x, z, pos);
                if (floorY == Integer.MIN_VALUE) continue;
                done[index] = true;

                final int supportY = supportBelow(chunk, x, floorY, z, pos);
                if (supportY == Integer.MIN_VALUE || supportY >= floorY - 1) continue;

                boolean lava = false;
                for (int y = supportY + 1; y < floorY; ++y) {
                    pos.set(x, y, z);
                    if (chunk.getBlockState(pos).is(Blocks.LAVA)) { lava = true; break; }
                }
                if (lava) continue;

                for (int y = supportY + 1; y < floorY; ++y) {
                    pos.set(x, y, z);
                    final BlockState state = chunk.getBlockState(pos);
                    if (!gap(state)) break;
                    chunk.setBlockState(pos, fill, 0);
                    ++changed;
                }
            }
        }
        return changed;
    }

    static int placedFloorY(
        final ChunkAccess chunk, final BoundingBox box, final int x, final int z,
        final BlockPos.MutableBlockPos pos
    ) {
        final int evidenceTop = Math.min(box.maxY(), box.minY() + STRUCTURE_EVIDENCE_SCAN);
        boolean structureEvidence = false;
        for (int y = box.minY(); y <= evidenceTop; ++y) {
            pos.set(x, y, z);
            final BlockState state = chunk.getBlockState(pos);
            if (isStructureEvidence(state)) { structureEvidence = true; break; }
        }
        if (!structureEvidence) return Integer.MIN_VALUE;

        final int floorTop = Math.min(box.maxY(), box.minY() + PIECE_FLOOR_SCAN);
        for (int y = box.minY(); y <= floorTop; ++y) {
            pos.set(x, y, z);
            final BlockState state = chunk.getBlockState(pos);
            if (!gap(state)) return y;
        }
        return Integer.MIN_VALUE;
    }

    static int supportBelow(
        final ChunkAccess chunk, final int x, final int floorY, final int z,
        final BlockPos.MutableBlockPos pos
    ) {
        final int bottom = Math.max(chunk.getMinY() + 1, floorY - MAX_SUPPORT_DEPTH - 1);
        for (int y = floorY - 1; y >= bottom; --y) {
            pos.set(x, y, z);
            final BlockState state = chunk.getBlockState(pos);
            if (!gap(state)) return y;
        }
        return Integer.MIN_VALUE;
    }

    static boolean gap(final BlockState state) {
        return state.isAir()
            || state.is(Blocks.WATER)
            || state.is(Blocks.SNOW)
            || state.canBeReplaced();
    }

    static boolean isStructureEvidence(final BlockState state) {
        if (gap(state)) return false;
        return !state.is(Blocks.DIRT)
            && !state.is(Blocks.GRASS_BLOCK)
            && !state.is(Blocks.COARSE_DIRT)
            && !state.is(Blocks.PODZOL)
            && !state.is(Blocks.STONE)
            && !state.is(Blocks.DEEPSLATE)
            && !state.is(Blocks.GRAVEL)
            && !state.is(Blocks.SAND)
            && !state.is(Blocks.RED_SAND)
            && !state.is(Blocks.SNOW_BLOCK)
            && !state.is(Blocks.ICE)
            && !state.is(Blocks.PACKED_ICE)
            && !state.is(Blocks.BLUE_ICE);
    }
}
