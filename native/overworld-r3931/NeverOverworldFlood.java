package net.minecraft.world.level.chunk;

import net.minecraft.world.level.WorldGenLevel;

/**
 * R39.31 native-sea transition.
 *
 * NeverOverworld now declares sea_level=128 in its native noise settings.
 * The historical LIGHT flood is therefore intentionally retired: it previously
 * erased generated fluids and reconstructed a second ocean after SURFACE,
 * CARVERS and FEATURES had already made decisions using sea_level=63.
 *
 * Keeping the call as a no-op preserves the existing LIGHT call site while
 * removing all late terrain/fluid mutation from that path.
 */
public final class NeverOverworldFlood {
    public static final String REVISION = "R3931-native-sea-128-no-light-flood";
    private NeverOverworldFlood() {}

    public static void apply(final WorldGenLevel level, final ChunkAccess chunk) {
        // Intentionally empty.
    }
}
