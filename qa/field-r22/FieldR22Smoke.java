package net.minecraft.world.level.chunk;

import net.minecraft.SharedConstants;
import net.minecraft.server.Bootstrap;
import net.minecraft.world.level.block.Blocks;

public final class FieldR22Smoke {
    private static int checks;

    private static void check(boolean ok, String why) {
        if (!ok) throw new AssertionError(why);
        checks++;
    }

    public static void main(String[] args) {
        var out = System.out;
        SharedConstants.tryDetectVersion();
        Bootstrap.bootStrap();

        check(NeverOverworldFloodConnectivityR15.prospectiveOceanSurfaceSeed(
                127, Blocks.AIR.defaultBlockState()),
            "FEATURES air at Y128 above submerged terrain must be a prospective ocean seed");
        check(NeverOverworldFloodConnectivityR15.prospectiveOceanSurfaceSeed(
                127, Blocks.WATER.defaultBlockState()),
            "already-flooded Y128 water must remain a prospective ocean seed");
        check(!NeverOverworldFloodConnectivityR15.prospectiveOceanSurfaceSeed(
                128, Blocks.AIR.defaultBlockState()),
            "terrain exactly at flood plane is not an ocean column");
        check(!NeverOverworldFloodConnectivityR15.prospectiveOceanSurfaceSeed(
                200, Blocks.AIR.defaultBlockState()),
            "dry highland air must not seed ocean flooding");
        check(!NeverOverworldFloodConnectivityR15.prospectiveOceanSurfaceSeed(
                80, Blocks.STONE.defaultBlockState()),
            "solid Y128 structure/terrain must not be flooded");
        check(NeverOverworldFloodConnectivityR15.horizontalSeamBelowOcean(0, 100, 8),
            "horizontal seam classification retained below Y128");
        check(!NeverOverworldFloodConnectivityR15.horizontalSeamBelowOcean(0, 128, 8),
            "Y128 itself is not the below-ocean seam band");

        out.println("PASS FieldR22Smoke checks=" + checks);
    }
}
