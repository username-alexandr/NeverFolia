package net.minecraft.world.level.levelgen.placement;

import net.minecraft.core.BlockPos;
import net.minecraft.server.level.WorldGenRegion;
import net.minecraft.world.level.WorldGenLevel;
import net.minecraft.world.level.block.state.BlockState;

/** R13 reconciliation: remote R12 planning and priorities, local natural-only
 * boundary and substrate eligibility. Never wraps structures/live ServerLevel.
 * No prior metadata profile is implicitly migrated by this change.
 */
public final class NeverNetherNaturalPolicyR13 {
    private NeverNetherNaturalPolicyR13() { }
    public static boolean handles(WorldGenLevel level) {
        // Deliberately do not unwrap TransformerLevelAccessor. It carries
        // structure write transforms that natural proposals must not bypass.
        return level instanceof WorldGenRegion && NeverNetherDecorationR8.inWorld(level);
    }
    public static boolean allowsPlantAt(BlockState substrate) {
        return !substrate.hasBlockEntity() && (substrate.isAir()
            || (substrate.canBeReplaced() && substrate.getFluidState().isEmpty()));
    }
    public static boolean proposeFlora(WorldGenLevel actual, BlockPos pos,
            BlockState state, int flags, int recursionLimit) {
        if (!NeverNetherDecorationR8.isDecoratedPlant(state))
            throw new IllegalArgumentException("R13 expects a plant proposal");
        if (!handles(actual))
            throw new IllegalArgumentException("R13 flora requires a bare natural WorldGenRegion");
        if (!allowsPlantAt(NeverNetherSubstrateR10.original(actual, pos))) return false;
        // Ownership and same-value external-write protection remain in the
        // persisted section mechanism; never reset its external-write bitmap.
        return NeverNetherSubstrateR10.proposeBlock(actual, pos, state, flags, recursionLimit);
    }
}
