package net.minecraft.world.level.chunk;

import net.minecraft.core.BlockPos;
import net.minecraft.tags.FluidTags;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.levelgen.Heightmap;

/** Shared write barrier for vegetation cleanup, including native fluid state. */
public final class NeverOverworldWaterPolicyR38 {
    private NeverOverworldWaterPolicyR38() {}

    public static BlockState afterPlantRemoval(ChunkAccess chunk, BlockPos pos, BlockState previous, boolean waterContact) {
        final var fluid = previous.getFluidState();
        // Removing a waterlogged plant is not permission to drain its water or
        // turn an existing flowing state into a new source.
        if (fluid.is(FluidTags.WATER)) return fluid.createLegacyBlock();
        final int floor = chunk.getHeight(Heightmap.Types.OCEAN_FLOOR_WG, pos.getX() & 15, pos.getZ() & 15);
        if (allowsNewWater(pos.getY(), floor, waterContact)
            && !NeverOverworldDryMinesR12.protectedCell(chunk, pos)) return Blocks.WATER.defaultBlockState();
        return Blocks.AIR.defaultBlockState();
    }

    public static boolean allowsNewWater(int y, int floor, boolean waterContact) {
        return waterContact && floor < 128 && y > floor && y <= 128;
    }
}
