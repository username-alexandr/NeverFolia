package net.minecraft.world.level.chunk;

/** Small pure decisions shared by the native FIELD-R12 adapters and tests. */
public final class NeverOverworldFieldPolicyR12 {
    public static final int OCEAN_Y = 128;
    public static final int MAX_STANDING_TREE_DEPTH = 2;
    public static final int MIN_STANDING_TREE_ORIGIN_Y = OCEAN_Y - MAX_STANDING_TREE_DEPTH;
    public static final int ORE_KEEP_PERCENT = 25;
    private NeverOverworldFieldPolicyR12() {}

    /** Height of TreeFeature's placement origin, not the supporting soil,
     * lowest root/leaf or the number of submerged blocks. At ocean Y=128,
     * origins Y=126 and higher pass this rule; Y=125 and lower do not.
     * Vanilla space, substrate and build-height rules still apply separately.
     * FallenTreeFeature is intentionally not subject to this standing-tree rule.
     */
    public static boolean acceptStandingTree(int originY) {
        return originY >= MIN_STANDING_TREE_ORIGIN_Y;
    }
}
