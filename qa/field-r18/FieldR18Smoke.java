package net.minecraft.world.level.chunk;

import net.minecraft.SharedConstants;
import net.minecraft.server.Bootstrap;
import net.minecraft.world.level.block.Blocks;

public final class FieldR18Smoke {
    private static int checks;

    private static void check(boolean ok, String why) {
        if (!ok) throw new AssertionError(why);
        checks++;
    }

    public static void main(String[] args) {
        var out = System.out;
        SharedConstants.tryDetectVersion();
        Bootstrap.bootStrap();

        check(NeverOverworldLavaCleanupR18.DEEP_LAVA_CUTOFF == -54,
            "deep lava cutoff must remain at vanilla boundary -54");
        check(NeverOverworldLavaCleanupR18.shouldRemoveGeneratedLava(
                Blocks.LAVA.defaultBlockState(), -55),
            "deep lava below -54 must be removed");
        check(NeverOverworldLavaCleanupR18.shouldRemoveGeneratedLava(
                Blocks.LAVA.defaultBlockState(), -512),
            "bottom-world deep lava must be removed");
        check(!NeverOverworldLavaCleanupR18.shouldRemoveGeneratedLava(
                Blocks.LAVA.defaultBlockState(), -54),
            "lava at cutoff -54 must remain");
        check(!NeverOverworldLavaCleanupR18.shouldRemoveGeneratedLava(
                Blocks.LAVA.defaultBlockState(), 0),
            "upper lava must remain");
        check(!NeverOverworldLavaCleanupR18.shouldRemoveGeneratedLava(
                Blocks.WATER.defaultBlockState(), -200),
            "water must not be touched by deep lava cleanup");
        check(!NeverOverworldLavaCleanupR18.shouldRemoveGeneratedLava(
                Blocks.STONE.defaultBlockState(), -200),
            "solid terrain must not be touched by deep lava cleanup");

        out.println("PASS FieldR18Smoke checks=" + checks);
    }
}
