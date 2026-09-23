package net.minecraft.world.level.chunk;

import net.minecraft.core.BlockPos;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.WorldGenLevel;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.chunk.status.ChunkStatus;

/**
 * FIELD-R18 final generated-lava cleanup for the extended NeverOverworld.
 *
 * The native fluid picker already disables vanilla lava aquifers below Y=-54,
 * and generated lava lake/spring features are filtered. Any remaining lava
 * below that cutoff is therefore carver-origin residue from vanilla-height
 * assumptions and is removed before the chunk reaches FULL.
 */
public final class NeverOverworldLavaCleanupR18 {
    static final int DEEP_LAVA_CUTOFF = -54;

    private NeverOverworldLavaCleanupR18() {}

    public static int cleanup(final WorldGenLevel level, final ChunkAccess chunk) {
        if (!level.getLevel().dimension().equals(Level.OVERWORLD)
            || level.getMinY() != -512 || level.getHeight() != 1024
            || chunk.getPersistedStatus().isOrAfter(ChunkStatus.FULL)) {
            return 0;
        }

        int changed = 0;
        final int baseX = chunk.getPos().getMinBlockX();
        final int baseZ = chunk.getPos().getMinBlockZ();
        final BlockPos.MutableBlockPos pos = new BlockPos.MutableBlockPos();

        for (int sectionY = chunk.getMinSectionY(); sectionY <= chunk.getMaxSectionY(); ++sectionY) {
            final int baseY = sectionY << 4;
            if (baseY >= DEEP_LAVA_CUTOFF) break;
            final int index = chunk.getSectionIndexFromSectionY(sectionY);
            if (index < 0 || index >= chunk.getSections().length) continue;
            final LevelChunkSection section = chunk.getSections()[index];
            if (!section.maybeHas(state -> state.is(Blocks.LAVA))) continue;

            for (int ly = 0; ly < 16; ++ly) {
                final int y = baseY + ly;
                if (y >= DEEP_LAVA_CUTOFF) break;
                for (int z = 0; z < 16; ++z) for (int x = 0; x < 16; ++x) {
                    if (!section.getBlockState(x, ly, z).is(Blocks.LAVA)) continue;
                    pos.set(baseX + x, y, baseZ + z);
                    chunk.setBlockState(pos, Blocks.AIR.defaultBlockState(), 0);
                    ++changed;
                }
            }
        }
        return changed;
    }
}
