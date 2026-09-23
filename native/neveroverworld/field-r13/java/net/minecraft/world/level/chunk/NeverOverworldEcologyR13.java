package net.minecraft.world.level.chunk;

import net.minecraft.core.BlockPos;
import net.minecraft.tags.FluidTags;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.WorldGenLevel;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.BushBlock;
import net.minecraft.world.level.block.MossyCarpetBlock;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.properties.BlockStateProperties;
import net.minecraft.world.level.chunk.status.ChunkStatus;

/**
 * FIELD-R13 post-FEATURES ecology policy for the flooded Overworld.
 *
 * <p>Height-gated plants follow the same lower bound as standing trees:
 * Y >= 126 for the Y=128 ocean. The LIGHT cleanup then removes accidental
 * underwater/floating bushes after the final flood state is known. This is
 * generation-only: FULL/player-time chunks are never changed.</p>
 */
public final class NeverOverworldEcologyR13 {
    public static final int OCEAN_Y = 128;
    public static final int MIN_PLANT_Y = 126;
    public static final int WATER_SUPPORT_SCAN_MAX_Y = 130;

    private NeverOverworldEcologyR13() {}

    private static boolean scope(final WorldGenLevel level) {
        return level.getLevel().dimension().equals(Level.OVERWORLD)
            && level.getMinY() == -512 && level.getHeight() == 1024;
    }

    public static boolean allowHeightGatedOrigin(final WorldGenLevel level, final BlockPos origin) {
        return !scope(level) || origin.getY() >= MIN_PLANT_Y;
    }

    public static boolean allowSimpleBlock(
        final WorldGenLevel level,
        final BlockPos origin,
        final BlockState state
    ) {
        return !scope(level) || !isHeightGated(state) || origin.getY() >= MIN_PLANT_Y;
    }

    static boolean isHeightGated(final BlockState state) {
        return state.is(Blocks.BROWN_MUSHROOM)
            || state.is(Blocks.RED_MUSHROOM)
            || state.is(Blocks.BROWN_MUSHROOM_BLOCK)
            || state.is(Blocks.RED_MUSHROOM_BLOCK)
            || state.is(Blocks.MUSHROOM_STEM)
            || state.is(Blocks.PUMPKIN)
            || state.is(Blocks.BAMBOO)
            || state.is(Blocks.BAMBOO_SAPLING)
            || state.is(Blocks.MOSS_CARPET)
            || state.is(Blocks.PALE_MOSS_CARPET)
            || state.getBlock() instanceof MossyCarpetBlock;
    }

    static boolean aquaticSensitive(final BlockState state) {
        return isHeightGated(state) || state.getBlock() instanceof BushBlock;
    }

    static boolean waterlogged(final BlockState state) {
        return state.hasProperty(BlockStateProperties.WATERLOGGED)
            && state.getValue(BlockStateProperties.WATERLOGGED);
    }

    private static boolean water(final ChunkAccess chunk, final BlockPos.MutableBlockPos pos) {
        return chunk.getBlockState(pos).getFluidState().is(FluidTags.WATER);
    }

    /**
     * Runs after both flood passes. Height-gated blocks below Y126 are removed
     * everywhere. Up through Y130, bushes/flowers/grass and gated blocks are
     * removed when submerged or floating directly over water. Lily pads are not
     * BushBlock and shoreline sugar cane is intentionally outside this policy.
     */
    public static int cleanup(final WorldGenLevel level, final ChunkAccess chunk) {
        if (!scope(level) || chunk.getPersistedStatus().isOrAfter(ChunkStatus.FULL)) return 0;

        int changed = 0;
        final BlockPos.MutableBlockPos pos = new BlockPos.MutableBlockPos();
        final BlockPos.MutableBlockPos probe = new BlockPos.MutableBlockPos();
        final int baseX = chunk.getPos().getMinBlockX();
        final int baseZ = chunk.getPos().getMinBlockZ();

        for (int sectionY = chunk.getMinSectionY(); sectionY <= chunk.getMaxSectionY(); ++sectionY) {
            final int index = chunk.getSectionIndexFromSectionY(sectionY);
            if (index < 0 || index >= chunk.getSections().length) continue;
            final LevelChunkSection section = chunk.getSections()[index];
            if (!section.maybeHas(NeverOverworldEcologyR13::aquaticSensitive)) continue;

            final int baseY = sectionY << 4;
            for (int ly = 0; ly < 16; ++ly) {
                final int y = baseY + ly;
                if (y > WATER_SUPPORT_SCAN_MAX_Y && y >= MIN_PLANT_Y) continue;
                for (int lz = 0; lz < 16; ++lz) {
                    for (int lx = 0; lx < 16; ++lx) {
                        final BlockState state = section.getBlockState(lx, ly, lz);
                        if (!aquaticSensitive(state)) continue;

                        final int x = baseX + lx;
                        final int z = baseZ + lz;
                        pos.set(x, y, z);

                        boolean remove = isHeightGated(state) && y < MIN_PLANT_Y;
                        boolean inWater = waterlogged(state) || state.getFluidState().is(FluidTags.WATER);
                        boolean waterAbove = false;
                        boolean waterBelow = false;
                        if (y <= WATER_SUPPORT_SCAN_MAX_Y) {
                            if (y + 1 < chunk.getMaxY()) {
                                probe.set(x, y + 1, z);
                                waterAbove = water(chunk, probe);
                            }
                            if (y - 1 >= chunk.getMinY()) {
                                probe.set(x, y - 1, z);
                                waterBelow = water(chunk, probe);
                            }
                            if (inWater || waterAbove || waterBelow) remove = true;
                        }
                        if (!remove) continue;

                        final BlockState replacement =
                            y <= OCEAN_Y && (inWater || waterAbove || waterBelow)
                                ? Blocks.WATER.defaultBlockState()
                                : Blocks.AIR.defaultBlockState();
                        chunk.setBlockState(pos, replacement, 0);
                        ++changed;
                    }
                }
            }
        }
        return changed;
    }
}
