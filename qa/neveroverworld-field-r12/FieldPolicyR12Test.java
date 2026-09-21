package net.minecraft.world.level.chunk;

public final class FieldPolicyR12Test {
    public static void main(String[] args) {
        int checks = 0;
        for (int total = 1; total <= 256; total++) {
            for (int wet = 0; wet <= total; wet++) {
                for (int above = 0; above <= total-wet; above++) {
                    boolean expected = wet==0 || (wet<=3 && above>0);
                    if (NeverOverworldFieldPolicyR12.acceptStandingTree(total,wet,above) != expected) {
                        throw new AssertionError("candidate census " + total + "/" + wet + "/" + above);
                    }
                    checks++;
                }
            }
        }
        for (int[] bad : new int[][]{{-1,0,0},{1,-1,0},{1,0,-1},{1,2,0},{1,0,2},{2,2,1}}) {
            try { NeverOverworldFieldPolicyR12.acceptStandingTree(bad[0],bad[1],bad[2]);
                throw new AssertionError("invalid census accepted");
            } catch (IllegalArgumentException expected) { checks++; }
        }
        if(NeverOverworldFieldPolicyR12.ORE_KEEP_PERCENT!=25) throw new AssertionError("ore profile");
        System.out.println("PASS FieldPolicyR12Test checks=" + checks + " (pure policy, NOT gameplay)");
    }
}
