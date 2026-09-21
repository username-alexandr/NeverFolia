package net.minecraft.world.level.chunk;

public final class FieldPolicyR12Test {
    public static void main(String[] args) {
        int checks = 0;
        if (NeverOverworldFieldPolicyR12.OCEAN_Y != 128
            || NeverOverworldFieldPolicyR12.MAX_STANDING_TREE_DEPTH != 2
            || NeverOverworldFieldPolicyR12.MIN_STANDING_TREE_ORIGIN_Y != 126) {
            throw new AssertionError("ocean-relative standing-tree height profile");
        }
        for (int y = -2048; y <= 2048; y++) {
            boolean expected = y >= 126;
            if (NeverOverworldFieldPolicyR12.acceptStandingTree(y) != expected) {
                throw new AssertionError("tree origin height " + y);
            }
            checks++;
        }
        for (int y : new int[]{Integer.MIN_VALUE, 125, 126, 127, 128, 129, Integer.MAX_VALUE}) {
            if (NeverOverworldFieldPolicyR12.acceptStandingTree(y) != (y >= 126)) {
                throw new AssertionError("boundary/overflow " + y);
            }
            checks++;
        }
        if (NeverOverworldFieldPolicyR12.ORE_KEEP_PERCENT != 25) throw new AssertionError("ore profile changed");
        System.out.println("PASS FieldPolicyR12Test checks=" + checks + " height-only origin>=126 (pure policy, NOT gameplay)");
    }
}
