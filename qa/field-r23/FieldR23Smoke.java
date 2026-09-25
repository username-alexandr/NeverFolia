package net.minecraft.world.level.chunk;

import java.lang.reflect.Method;
import java.util.HashSet;
import java.util.Set;
import net.minecraft.SharedConstants;
import net.minecraft.server.Bootstrap;
import net.minecraft.world.level.block.Blocks;

public final class FieldR23Smoke {
    private static int checks;

    private static void check(boolean ok, String why) {
        if (!ok) throw new AssertionError(why);
        checks++;
    }

    public static void main(String[] args) {
        var out = System.out;
        SharedConstants.tryDetectVersion();
        Bootstrap.bootStrap();

        Set<String> methods = new HashSet<>();
        for (Method method : NeverOverworldFloodConnectivityR15.class.getDeclaredMethods()) {
            methods.add(method.getName());
        }

        check(!methods.contains("proximityFallbackAllowed"),
            "R23 must remove geometry/proximity cave flooding");
        check(!methods.contains("seedOceanProximityFallback"),
            "R23 must remove owner near-ocean seed injection");
        check(!methods.contains("proximityConnectedFloodable"),
            "R23 must remove neighbour proximity component acceptance");
        check(!methods.contains("nearOceanColumns"),
            "R23 must not classify cave flood eligibility by distance to ocean");

        check(NeverOverworldFloodConnectivityR15.prospectiveOceanSurfaceSeed(
                127, Blocks.AIR.defaultBlockState()),
            "prospective Y128 ocean seed must remain for scheduling-independent seam reconciliation");
        check(!NeverOverworldFloodConnectivityR15.prospectiveOceanSurfaceSeed(
                128, Blocks.AIR.defaultBlockState()),
            "dry Y128 column must not become an ocean seed");
        check(NeverOverworldFloodConnectivityR15.surfaceOceanSeed(
                128, Blocks.WATER.defaultBlockState()),
            "existing Y128 water remains authoritative");
        check(!NeverOverworldFloodConnectivityR15.surfaceOceanSeed(
                200, Blocks.AIR.defaultBlockState()),
            "highland air must stay dry");

        out.println("PASS FieldR23Smoke checks=" + checks);
    }
}
