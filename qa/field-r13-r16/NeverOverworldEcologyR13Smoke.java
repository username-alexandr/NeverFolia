package net.minecraft.world.level.chunk;

import net.minecraft.world.level.block.Blocks;

/** Regression checks for FIELD-R13 flora classification. */
public final class NeverOverworldEcologyR13Smoke {
    private static int checks;

    private NeverOverworldEcologyR13Smoke() {}

    private static void check(final boolean condition, final String message) {
        ++checks;
        if (!condition) throw new AssertionError(message);
    }

    public static void main(final String[] args) {
        check(NeverOverworldEcologyR13.isHeightGated(Blocks.MOSS_CARPET.defaultBlockState()),
            "vanilla moss carpet must be height-gated");
        check(NeverOverworldEcologyR13.isHeightGated(Blocks.PALE_MOSS_CARPET.defaultBlockState()),
            "pale moss carpet must be height-gated");
        check(NeverOverworldEcologyR13.isHeightGated(Blocks.PUMPKIN.defaultBlockState()),
            "pumpkin must be height-gated");
        check(NeverOverworldEcologyR13.isHeightGated(Blocks.BAMBOO.defaultBlockState()),
            "bamboo must be height-gated");
        check(NeverOverworldEcologyR13.isHeightGated(Blocks.BROWN_MUSHROOM.defaultBlockState()),
            "mushroom must be height-gated");
        check(!NeverOverworldEcologyR13.isHeightGated(Blocks.STONE.defaultBlockState()),
            "stone must not be height-gated");
        check(NeverOverworldEcologyR13.aquaticSensitive(Blocks.DANDELION.defaultBlockState()),
            "flowers must remain water-sensitive");
        check(!NeverOverworldEcologyR13.aquaticSensitive(Blocks.LILY_PAD.defaultBlockState()),
            "lily pads are intentionally outside shoreline bush cleanup");
        System.out.println("PASS NeverOverworldEcologyR13Smoke checks=" + checks);
    }
}
