package net.minecraft.world.level.chunk;

/** Small pure decisions shared by the native FIELD-R12 adapters and tests. */
public final class NeverOverworldFieldPolicyR12 {
    public static final int OCEAN_Y = 128;
    public static final int MAX_SUBMERGED_STANDING_BLOCKS = 3;
    public static final int ORE_KEEP_PERCENT = 25;
    private NeverOverworldFieldPolicyR12() {}

    /** Counts are candidate log/leaf blocks, not vertical depth or roots.
     * No existing tree is deleted: this decision precedes feature publication.
     * FallenTreeFeature has a separate adapter and is never classified from
     * incidental horizontal branches on an ordinary standing tree.
     */
    public static boolean acceptStandingTree(int woodLeafCount, int atRiskCount, int aboveOceanCount) {
        if (woodLeafCount < 0 || atRiskCount < 0 || aboveOceanCount < 0
            || atRiskCount > woodLeafCount || aboveOceanCount > woodLeafCount
            || (long)atRiskCount + aboveOceanCount > woodLeafCount) {
            throw new IllegalArgumentException("Invalid candidate-tree census");
        }
        if (atRiskCount == 0) return true;
        return aboveOceanCount > 0 && atRiskCount <= MAX_SUBMERGED_STANDING_BLOCKS;
    }
}
