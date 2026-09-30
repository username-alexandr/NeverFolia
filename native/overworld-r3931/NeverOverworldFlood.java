package net.minecraft.world.level.chunk;

import net.minecraft.core.BlockPos;
import net.minecraft.core.SectionPos;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.WorldGenLevel;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.chunk.status.ChunkStatus;

/**
 * R39.31 native-sea transition.
 *
 * The ocean itself is now generated natively with sea_level=128. This class
 * therefore keeps only LIGHT-stage work that is independent from the old
 * post-generation flood. All code that deleted fluids, reconstructed water,
 * re-weathered the seabed or repaired artifacts created by that reconstruction
 * is intentionally retired.
 *
 * Public entry points are retained because already-patched Folia classes link
 * to them directly.
 */
public final class NeverOverworldFlood {
    public static final String REVISION = "R3931-native-sea-128-abi-safe";

    private NeverOverworldFlood() {}

    public static void apply(final WorldGenLevel level, final ChunkAccess chunk) {
        if (!level.getLevel().dimension().equals(Level.OVERWORLD)
            || level.getMinY() != -512
            || level.getHeight() != 1024
            || chunk.getPersistedStatus().isOrAfter(ChunkStatus.FULL)) {
            return;
        }

        traceNativeWaterR37("PRE_LIGHT", chunk);

        NeverOverworldOreExposurePruner.applyAtLight(level, chunk);
        removeUpperLapisDiamondAfterNeighbourFeatures(chunk);
        NeverOverworldOreScarcityFieldR10.apply(level, chunk);
        NeverOverworldDryMinesR12.prepare(chunk);
        NeverOverworldLavaCleanupR18.cleanup(level, chunk);
        NeverOverworldDryMinesR12.prepare(chunk);
        NeverOverworldDesertR1.generate(level, chunk);

        traceNativeWaterR37("POST_LIGHT", chunk);
        chunk.neverOverworldDryMineMaskR12 = null;
    }

    /**
     * Kept for ChunkLightTask ABI compatibility. Native surface rules now see
     * sea_level=128 before SURFACE/FEATURES, so a second submerged-surface pass
     * would corrupt the authoritative terrain instead of repairing it.
     */
    public static void reweatherSubmergedSurface(final WorldGenLevel level, final ChunkAccess chunk) {
        // Intentionally empty.
    }

    /**
     * Kept for NoiseBasedChunkGenerator ABI compatibility. The old method was
     * diagnostic-only and must never mutate terrain.
     */
    public static void traceNativeWaterR37(final String stage, final ChunkAccess chunk) {
        // Intentionally empty unless a future native-sea diagnostic is added.
    }

    private static void removeUpperLapisDiamondAfterNeighbourFeatures(final ChunkAccess chunk) {
        final int minY = -64;
        final int maxY = 319;
        final int minSectionY = SectionPos.blockToSectionCoord(minY);
        final int maxSectionY = SectionPos.blockToSectionCoord(maxY);
        final LevelChunkSection[] sections = chunk.getSections();
        final int minX = chunk.getPos().getMinBlockX();
        final int minZ = chunk.getPos().getMinBlockZ();
        final BlockPos.MutableBlockPos cursor = new BlockPos.MutableBlockPos();

        for (int sectionY = minSectionY; sectionY <= maxSectionY; ++sectionY) {
            final int sectionIndex = chunk.getSectionIndexFromSectionY(sectionY);
            if (sectionIndex < 0 || sectionIndex >= sections.length) continue;

            final LevelChunkSection section = sections[sectionIndex];
            if (!section.maybeHas(NeverOverworldFlood::isUpperForbiddenOre)) continue;

            final int baseY = SectionPos.sectionToBlockCoord(sectionY);
            final int fromY = Math.max(minY, baseY);
            final int toY = Math.min(maxY, baseY + 15);

            for (int y = fromY; y <= toY; ++y) {
                final int localY = SectionPos.sectionRelative(y);
                for (int z = 0; z < 16; ++z) {
                    for (int x = 0; x < 16; ++x) {
                        final BlockState state = section.getBlockState(x, localY, z);
                        if (!isUpperForbiddenOre(state)) continue;

                        final BlockState replacement =
                            state.is(Blocks.DEEPSLATE_LAPIS_ORE) || state.is(Blocks.DEEPSLATE_DIAMOND_ORE)
                                ? Blocks.DEEPSLATE.defaultBlockState()
                                : Blocks.STONE.defaultBlockState();
                        cursor.set(minX + x, y, minZ + z);
                        chunk.setBlockState(cursor, replacement, 0);
                    }
                }
            }
        }
    }

    private static boolean isUpperForbiddenOre(final BlockState state) {
        return state.is(Blocks.LAPIS_ORE)
            || state.is(Blocks.DEEPSLATE_LAPIS_ORE)
            || state.is(Blocks.DIAMOND_ORE)
            || state.is(Blocks.DEEPSLATE_DIAMOND_ORE);
    }
}
