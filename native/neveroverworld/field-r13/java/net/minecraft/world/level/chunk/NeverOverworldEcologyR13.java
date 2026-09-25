package net.minecraft.world.level.chunk;

import net.minecraft.core.BlockPos;
import net.minecraft.tags.FluidTags;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.WorldGenLevel;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.MossyCarpetBlock;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.properties.BlockStateProperties;
import net.minecraft.world.level.chunk.status.ChunkStatus;

/**
 * FIELD-R13 post-FEATURES ecology policy for the flooded Overworld.
 *
 * <p>Height-gated plants follow the same lower bound as standing trees:
 * Y >= 126 for the Y=128 ocean. The LIGHT cleanup then removes accidental
 * underwater/floating shoreline vegetation after the final flood state is known.
 * This is generation-only: FULL/player-time chunks are never changed.</p>
 */
public final class NeverOverworldEcologyR13 {
    public static final int OCEAN_Y = 128;
    public static final int MIN_PLANT_Y = 126;
    public static final int WATER_SUPPORT_SCAN_MAX_Y = 132;

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
        if (!scope(level)) return true;
        if (state.is(Blocks.SWEET_BERRY_BUSH)) return origin.getY() > OCEAN_Y;
        return !isHeightGated(state) || origin.getY() >= MIN_PLANT_Y;
    }

    static boolean isHeightGated(final BlockState state) {
        return state.is(Blocks.BROWN_MUSHROOM)
            || state.is(Blocks.RED_MUSHROOM)
            || state.is(Blocks.BROWN_MUSHROOM_BLOCK)
            || state.is(Blocks.RED_MUSHROOM_BLOCK)
            || state.is(Blocks.MUSHROOM_STEM)
            || state.is(Blocks.PUMPKIN)
            || state.is(Blocks.SWEET_BERRY_BUSH)
            || state.is(Blocks.BAMBOO)
            || state.is(Blocks.BAMBOO_SAPLING)
            || state.is(Blocks.MOSS_CARPET)
            || state.is(Blocks.PALE_MOSS_CARPET)
            || state.getBlock() instanceof MossyCarpetBlock;
    }

    /**
     * Dry shoreline vegetation that must not survive in/over the rebuilt ocean.
     * This is an explicit Minecraft 26.2 whitelist rather than a class/tag test:
     * standalone regression bootstrap does not bind datapack tags, while broad
     * VegetationBlock matching would also catch legitimate aquatic vegetation.
     * Lily pads, seagrass/kelp and sugar cane stay outside this policy.
     */
    static boolean isShorelinePlant(final BlockState state) {
        return state.is(Blocks.SHORT_GRASS)
            || state.is(Blocks.TALL_GRASS)
            || state.is(Blocks.FERN)
            || state.is(Blocks.LARGE_FERN)
            || state.is(Blocks.SHORT_DRY_GRASS)
            || state.is(Blocks.TALL_DRY_GRASS)
            || state.is(Blocks.DEAD_BUSH)
            || state.is(Blocks.BUSH)
            || state.is(Blocks.FIREFLY_BUSH)
            || state.is(Blocks.LEAF_LITTER)
            || state.is(Blocks.DANDELION)
            || state.is(Blocks.POPPY)
            || state.is(Blocks.BLUE_ORCHID)
            || state.is(Blocks.ALLIUM)
            || state.is(Blocks.AZURE_BLUET)
            || state.is(Blocks.RED_TULIP)
            || state.is(Blocks.ORANGE_TULIP)
            || state.is(Blocks.WHITE_TULIP)
            || state.is(Blocks.PINK_TULIP)
            || state.is(Blocks.OXEYE_DAISY)
            || state.is(Blocks.CORNFLOWER)
            || state.is(Blocks.LILY_OF_THE_VALLEY)
            || state.is(Blocks.WITHER_ROSE)
            || state.is(Blocks.TORCHFLOWER)
            || state.is(Blocks.PITCHER_PLANT)
            || state.is(Blocks.PINK_PETALS)
            || state.is(Blocks.WILDFLOWERS)
            || state.is(Blocks.CACTUS_FLOWER)
            || state.is(Blocks.CLOSED_EYEBLOSSOM)
            || state.is(Blocks.OPEN_EYEBLOSSOM)
            || state.is(Blocks.SUNFLOWER)
            || state.is(Blocks.LILAC)
            || state.is(Blocks.ROSE_BUSH)
            || state.is(Blocks.PEONY);
    }

    static boolean aquaticSensitive(final BlockState state) {
        return isHeightGated(state) || isShorelinePlant(state);
    }

    static boolean seamSensitive(final BlockState state, final int y, final int localX, final int localZ) {
        final boolean edge = localX == 0 || localX == 15 || localZ == 0 || localZ == 15;
        if (!edge) return false;
        return isHeightGated(state) ? y <= WATER_SUPPORT_SCAN_MAX_Y
            : isShorelinePlant(state) && y <= OCEAN_Y;
    }

    static boolean waterlogged(final BlockState state) {
        return state.hasProperty(BlockStateProperties.WATERLOGGED)
            && state.getValue(BlockStateProperties.WATERLOGGED);
    }

    static boolean shouldRemoveForWaterContext(
        final BlockState state,
        final int y,
        final boolean inWater,
        final boolean waterAbove,
        final boolean waterBelow,
        final boolean waterSide
    ) {
        if (state.is(Blocks.SWEET_BERRY_BUSH) && y <= OCEAN_Y) return true;
        if (isHeightGated(state) && y < MIN_PLANT_Y) return true;
        return y <= WATER_SUPPORT_SCAN_MAX_Y
            && aquaticSensitive(state)
            && (inWater || waterAbove || waterBelow || waterSide);
    }

    private static boolean water(final ChunkAccess chunk, final BlockPos.MutableBlockPos pos) {
        return chunk.getBlockState(pos).getFluidState().is(FluidTags.WATER);
    }

    /**
     * Runs after both flood passes. Height-gated blocks below Y126 are removed
     * everywhere. Up through Y130, dry shoreline plants and gated blocks are
     * removed when submerged or floating directly over water. Lily pads,
     * seagrass/kelp and shoreline sugar cane are intentionally outside this policy.
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

                        boolean inWater = waterlogged(state) || state.getFluidState().is(FluidTags.WATER);
                        boolean waterAbove = false;
                        boolean waterBelow = false;
                        boolean waterSide = false;
                        if (y <= WATER_SUPPORT_SCAN_MAX_Y) {
                            if (y + 1 < chunk.getMaxY()) {
                                probe.set(x, y + 1, z);
                                waterAbove = water(chunk, probe);
                            }
                            if (y - 1 >= chunk.getMinY()) {
                                probe.set(x, y - 1, z);
                                waterBelow = water(chunk, probe);
                            }
                            final int[][] side = {{1,0},{-1,0},{0,1},{0,-1}};
                            for (final int[] d : side) {
                                final int nx = x + d[0], nz = z + d[1];
                                if (nx < baseX || nx > baseX + 15 || nz < baseZ || nz > baseZ + 15) continue;
                                probe.set(nx, y, nz);
                                if (water(chunk, probe)) { waterSide = true; break; }
                            }
                        }
                        final boolean waterContact = inWater || waterAbove || waterBelow || waterSide;
                        final boolean seamCandidate = seamSensitive(state, y, lx, lz);
                        if (!shouldRemoveForWaterContext(state, y, inWater, waterAbove, waterBelow, waterSide)
                            && !seamCandidate) continue;

                        final BlockState replacement =
                            y <= OCEAN_Y && waterContact
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
