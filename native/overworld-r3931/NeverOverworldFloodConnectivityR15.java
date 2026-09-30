package net.minecraft.world.level.chunk;

import net.minecraft.server.level.GenerationChunkHolder;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.util.StaticCache2D;
import net.minecraft.world.level.WorldGenLevel;

/**
 * R39.31 native-sea compatibility shim.
 *
 * The previous class existed solely to propagate/fill the synthetic Y=128
 * ocean after FEATURES/LIGHT. With sea_level=128 in NoiseGeneratorSettings,
 * every mutating entry point must be inert; signatures remain so already
 * patched Moonrise/Folia call sites continue to link.
 */
public final class NeverOverworldFloodConnectivityR15 {
    public static final String REVISION = "R3931-native-sea-no-late-connectivity";

    private NeverOverworldFloodConnectivityR15() {}

    public static int apply(final WorldGenLevel level, final ChunkAccess chunk) {
        return 0;
    }

    public static int reconcileSeams(
        final WorldGenLevel level,
        final StaticCache2D<GenerationChunkHolder> neighbours,
        final ChunkAccess chunk
    ) {
        return 0;
    }

    public static void publishFeatureBoundarySeeds(final ServerLevel level, final ChunkAccess chunk) {
        // No synthetic flood boundary state in native-sea mode.
    }

    public static void onFullChunk(final ServerLevel level, final LevelChunk chunk) {
        // No late correction scheduling in native-sea mode.
    }
}
