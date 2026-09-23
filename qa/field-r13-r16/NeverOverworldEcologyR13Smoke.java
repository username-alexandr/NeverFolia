package net.minecraft.world.level.chunk;

import net.minecraft.SharedConstants;
import net.minecraft.server.Bootstrap;
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
        SharedConstants.tryDetectVersion();
        Bootstrap.bootStrap();

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
        check(NeverOverworldEcologyR13.aquaticSensitive(Blocks.SHORT_GRASS.defaultBlockState()),
            "short grass must remain water-sensitive");
        check(NeverOverworldEcologyR13.aquaticSensitive(Blocks.FERN.defaultBlockState()),
            "fern must remain water-sensitive");
        check(NeverOverworldEcologyR13.aquaticSensitive(Blocks.FIREFLY_BUSH.defaultBlockState()),
            "firefly bush must remain water-sensitive");
        check(NeverOverworldEcologyR13.aquaticSensitive(Blocks.LEAF_LITTER.defaultBlockState()),
            "leaf litter must remain water-sensitive");
        check(NeverOverworldEcologyR13.aquaticSensitive(Blocks.SUNFLOWER.defaultBlockState()),
            "tall flowers must remain water-sensitive");
        check(NeverOverworldEcologyR13.aquaticSensitive(Blocks.CLOSED_EYEBLOSSOM.defaultBlockState()),
            "eyeblossoms must remain water-sensitive");

        check(!NeverOverworldEcologyR13.aquaticSensitive(Blocks.LILY_PAD.defaultBlockState()),
            "lily pads are intentionally outside shoreline cleanup");
        check(!NeverOverworldEcologyR13.aquaticSensitive(Blocks.SEAGRASS.defaultBlockState()),
            "seagrass is aquatic vegetation and must remain outside shoreline cleanup");
        check(!NeverOverworldEcologyR13.aquaticSensitive(Blocks.SUGAR_CANE.defaultBlockState()),
            "shoreline sugar cane is intentionally outside shoreline cleanup");

        System.out.println("PASS NeverOverworldEcologyR13Smoke checks=" + checks);
    }
}
