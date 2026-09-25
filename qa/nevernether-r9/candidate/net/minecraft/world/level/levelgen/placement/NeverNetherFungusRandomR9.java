package net.minecraft.world.level.levelgen.placement;
import net.minecraft.core.BlockPos;
import net.minecraft.util.RandomSource;
import net.minecraft.world.level.WorldGenLevel;

/** Per-cell randomness prevents a blocked neighbor cell from shifting the whole canopy. */
public final class NeverNetherFungusRandomR9 {
    private NeverNetherFungusRandomR9() { }
    private static long mix(long x) {
        x=(x^(x>>>30))*0xbf58476d1ce4e5b9L;
        x=(x^(x>>>27))*0x94d049bb133111ebL;
        return x^(x>>>31);
    }
    private static long position(long h,BlockPos p) {
        h=mix(h^(long)p.getX()*0x9e3779b97f4a7c15L);
        h=mix(h^(long)p.getY()*0xc2b2ae3d27d4eb4fL);
        return mix(h^(long)p.getZ()*0x165667b19e3779f9L);
    }
    public static long seed(long worldSeed, BlockPos root, BlockPos cell, long salt) {
        return position(position(mix(worldSeed^salt),root),cell);
    }
    public static RandomSource at(WorldGenLevel level, BlockPos root, BlockPos cell, long salt, RandomSource fallback) {
        if (!(level instanceof NeverNetherPlanningViewR9)) return fallback;
        return RandomSource.create(seed(level.getSeed(),root,cell,salt));
    }
}
