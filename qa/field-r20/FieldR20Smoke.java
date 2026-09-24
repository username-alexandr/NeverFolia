package net.minecraft.world.level.chunk;

public final class FieldR20Smoke {
    private static int checks;

    private static void check(boolean ok, String why) {
        if (!ok) throw new AssertionError(why);
        checks++;
    }

    public static void main(String[] args) {
        check(NeverOverworldFloodConnectivityR15.horizontalSeamBelowOcean(0, 64, 8),
            "x-min boundary below Y128 must be seam-sensitive");
        check(NeverOverworldFloodConnectivityR15.horizontalSeamBelowOcean(15, 127, 8),
            "x-max boundary below Y128 must be seam-sensitive");
        check(NeverOverworldFloodConnectivityR15.horizontalSeamBelowOcean(8, 40, 0),
            "z-min boundary below Y128 must be seam-sensitive");
        check(!NeverOverworldFloodConnectivityR15.horizontalSeamBelowOcean(8, 128, 0),
            "surface Y128 itself must remain a valid ocean seed");
        check(!NeverOverworldFloodConnectivityR15.horizontalSeamBelowOcean(8, 64, 8),
            "interior cave cells must not be treated as seams");

        check(NeverOverworldGeneratedVillageSafety.pieceSurfaceSpanAllowed(140, 148),
            "piece surface span of 8 blocks must remain allowed");
        check(!NeverOverworldGeneratedVillageSafety.pieceSurfaceSpanAllowed(140, 149),
            "piece surface span above 8 blocks must be rejected");
        check(!NeverOverworldGeneratedVillageSafety.pieceSurfaceSpanAllowed(
                Integer.MAX_VALUE, Integer.MIN_VALUE),
            "empty/invalid piece surface sample must be rejected");

        System.out.println("PASS FieldR20Smoke checks=" + checks);
    }
}
