package net.minecraft.world.level.levelgen.placement;

import net.minecraft.core.BlockPos;
import net.minecraft.resources.Identifier;
import net.minecraft.server.level.WorldGenRegion;
import net.minecraft.util.RandomSource;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.WorldGenLevel;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.BlockState;

/** Candidate R8: stable support RNG and geological (not previously decorated) floor layers.
 * Scope is the native NeverNether envelope and two exact support resources.
 * No world writes, source counts, materials or weights are removed by this helper.
 */
public final class NeverNetherDecorationR8 {
    private NeverNetherDecorationR8() { }
    public static boolean inWorld(WorldGenLevel level) {
        WorldGenLevel current = level;
        for (int depth = 0; depth < 8; depth++) {
            if (current instanceof WorldGenRegion)
                return current.getMinY() == -128 && current.getHeight() == 1024
                    && current.getLevel().dimension().equals(Level.NETHER);
            if (!(current instanceof org.bukkit.craftbukkit.util.DelegatedLevelAccessor wrapper)) return false;
            current = wrapper.getDelegate();
        }
        return false;
    }
    public static RandomSource supportRandom(PlacedFeature feature, WorldGenLevel level, BlockPos origin, RandomSource fallback) {
        if (!inWorld(level)) return fallback;
        Identifier id = feature.feature().unwrapKey().map(key -> key.identifier()).orElse(null);
        if (id == null || !id.getNamespace().equals("nova_structures")) return fallback;
        long salt;
        switch (id.getPath()) {
            case "nether_bricks_base" -> salt = 0x4E4E524842524943L;
            case "blackstone_bricks_base" -> salt = 0x4E4E5238424C4143L;
            default -> { return fallback; }
        }
        // Full coordinate lanes: no packed BlockPos aliasing at extended world heights.
        long seed = mix(level.getSeed() ^ salt);
        seed = mix(seed ^ (long)origin.getX() * 0x9e3779b97f4a7c15L);
        seed = mix(seed ^ (long)origin.getY() * 0xc2b2ae3d27d4eb4fL);
        seed = mix(seed ^ (long)origin.getZ() * 0x165667b19e3779f9L);
        return RandomSource.create(seed);
    }
    public static WorldGenLevel supportView(PlacedFeature feature, WorldGenLevel level) {
        if (!inWorld(level)) return level;
        Identifier id = feature.feature().unwrapKey().map(key -> key.identifier()).orElse(null);
        if (id == null || !id.getNamespace().equals("nova_structures")
            || !(id.getPath().equals("nether_bricks_base") || id.getPath().equals("blackstone_bricks_base"))) return level;
        var view = new org.bukkit.craftbukkit.util.DelegatedLevelAccessor() {
            @Override public BlockState getBlockState(BlockPos p) {
                BlockState state = super.getBlockState(p);
                return isDecoratedPlant(state) ? Blocks.AIR.defaultBlockState() : state;
            }
            @Override public boolean isEmptyBlock(BlockPos p) { return getBlockState(p).isAir(); }
            @Override public boolean isStateAtPosition(BlockPos p, java.util.function.Predicate<BlockState> test) { return test.test(getBlockState(p)); }
            @Override public net.minecraft.world.level.material.FluidState getFluidState(BlockPos p) { return getBlockState(p).getFluidState(); }
        };
        view.setDelegate(level);return view;
    }
    private static long mix(long x) {
        x = (x ^ (x >>> 30)) * 0xbf58476d1ce4e5b9L;
        x = (x ^ (x >>> 27)) * 0x94d049bb133111ebL;
        return x ^ (x >>> 31);
    }
    public static boolean isDecoratedPlant(BlockState state) {
        return state.is(Blocks.CRIMSON_STEM) || state.is(Blocks.WARPED_STEM)
            || state.is(Blocks.NETHER_WART_BLOCK) || state.is(Blocks.WARPED_WART_BLOCK)
            || state.is(Blocks.SHROOMLIGHT) || state.is(Blocks.CRIMSON_ROOTS) || state.is(Blocks.WARPED_ROOTS)
            || state.is(Blocks.CRIMSON_FUNGUS) || state.is(Blocks.WARPED_FUNGUS) || state.is(Blocks.NETHER_SPROUTS)
            || state.is(Blocks.WEEPING_VINES) || state.is(Blocks.WEEPING_VINES_PLANT)
            || state.is(Blocks.TWISTING_VINES) || state.is(Blocks.TWISTING_VINES_PLANT);
    }
}
