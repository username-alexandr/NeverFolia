package net.minecraft.world.level.levelgen.placement;

import net.minecraft.core.BlockPos;
import net.minecraft.resources.Identifier;
import net.minecraft.util.RandomSource;
import net.minecraft.world.level.WorldGenLevel;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.BlockState;

/** R9 opt-in extension for the observed Sealing Halls blackstone support path. */
public final class NeverNetherSupportCandidateR9 {
    private NeverNetherSupportCandidateR9() { }
    public static boolean matches(Identifier id) {
        return id != null && id.getNamespace().equals("nova_structures") && id.getPath().equals("blackstone_base");
    }
    public static boolean handles(PlacedFeature feature, WorldGenLevel level) {
        if (!NeverNetherDecorationR8.inWorld(level) || feature == null) return false;
        Identifier id = feature.feature().unwrapKey().map(key -> key.identifier()).orElse(null);
        return matches(id);
    }
    public static RandomSource supportRandom(PlacedFeature feature, WorldGenLevel level, BlockPos origin, RandomSource fallback) {
        if (!handles(feature, level)) return NeverNetherDecorationR8.supportRandom(feature,level,origin,fallback);
        long seed = mix(level.getSeed() ^ 0x4E4E5239424C4143L);
        seed = mix(seed ^ (long)origin.getX() * 0x9e3779b97f4a7c15L);
        seed = mix(seed ^ (long)origin.getY() * 0xc2b2ae3d27d4eb4fL);
        seed = mix(seed ^ (long)origin.getZ() * 0x165667b19e3779f9L);
        return RandomSource.create(seed);
    }
    private static long mix(long x) {
        x=(x^(x>>>30))*0xbf58476d1ce4e5b9L;
        x=(x^(x>>>27))*0x94d049bb133111ebL;
        return x^(x>>>31);
    }
    public static WorldGenLevel supportView(PlacedFeature feature, WorldGenLevel level) {
        if (!handles(feature,level)) return NeverNetherDecorationR8.supportView(feature,level);
        var view = new org.bukkit.craftbukkit.util.DelegatedLevelAccessor() {
            @Override public BlockState getBlockState(BlockPos p) {
                BlockState state=super.getBlockState(p);
                return NeverNetherDecorationR8.isDecoratedPlant(state)?Blocks.AIR.defaultBlockState():state;
            }
            @Override public boolean isEmptyBlock(BlockPos p){return getBlockState(p).isAir();}
            @Override public boolean isStateAtPosition(BlockPos p,java.util.function.Predicate<BlockState> test){return test.test(getBlockState(p));}
            @Override public net.minecraft.world.level.material.FluidState getFluidState(BlockPos p){return getBlockState(p).getFluidState();}
        };
        view.setDelegate(level);return view;
    }
}
