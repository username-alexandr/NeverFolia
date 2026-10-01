package net.minecraft.world.level.levelgen.structure.structures;

import java.util.Arrays;
import net.minecraft.world.level.ChunkPos;
import net.minecraft.world.level.levelgen.Heightmap;
import net.minecraft.world.level.levelgen.structure.Structure;

/**
 * R39.34: anchor vanilla ocean monuments to the real seabed in NeverOverworld.
 *
 * <p>The old NeverOverworld monument patch fixed the base at Y=104
 * (flood surface 128 - vanilla 24). Vanilla MonumentBuilding then called
 * fillColumnDown() from that elevated base, creating extremely long prismarine
 * support columns over deep ocean terrain. This resolver samples the native
 * OCEAN_FLOOR_WG footprint before structure placement and moves the base close
 * to the seabed instead.</p>
 */
public final class NeverOverworldOceanMonumentR34 {
    private static final int EXPECTED_MIN_Y = -512;
    private static final int EXPECTED_HEIGHT = 1024;
    private static final int LEGACY_FLOOD_BASE_Y = 104;
    private static final int MAX_SUPPORT_BUDGET = 8;
    private static final int[] OFFSETS = {-28, -20, -12, -4, 4, 12, 20, 28};

    private NeverOverworldOceanMonumentR34() {}

    public static int resolveBaseY(final Structure.GenerationContext context) {
        if (context.heightAccessor().getMinY() != EXPECTED_MIN_Y
            || context.heightAccessor().getHeight() != EXPECTED_HEIGHT) {
            return context.chunkGenerator().getSeaLevel() - 24;
        }

        final ChunkPos chunkPos = context.chunkPos();
        final int anchorX = chunkPos.getMinBlockX();
        final int anchorZ = chunkPos.getMinBlockZ();
        final int[] floors = new int[OFFSETS.length * OFFSETS.length];
        int index = 0;
        int minFloor = Integer.MAX_VALUE;

        for (final int dz : OFFSETS) {
            for (final int dx : OFFSETS) {
                // getBaseHeight returns the first block above the heightmap
                // surface, so subtract one to obtain the actual floor block Y.
                final int floor = context.chunkGenerator().getBaseHeight(
                    anchorX + dx,
                    anchorZ + dz,
                    Heightmap.Types.OCEAN_FLOOR_WG,
                    context.heightAccessor(),
                    context.randomState()
                ) - 1;
                floors[index++] = floor;
                minFloor = Math.min(minFloor, floor);
            }
        }

        Arrays.sort(floors);
        final int medianFloor = floors[floors.length / 2];

        // Prefer the median seabed so the monument is not buried by one isolated
        // low point, but never allow more than 8 sampled blocks of unsupported
        // depth beneath the base. This keeps the natural terrain intact while
        // eliminating the old 40-80 block prismarine stilts.
        int baseY = Math.min(medianFloor, minFloor + MAX_SUPPORT_BUDGET);

        // Keep the monument submerged if an unusually shallow ocean candidate
        // reaches above the historical flood-adapted placement.
        baseY = Math.min(baseY, LEGACY_FLOOD_BASE_Y);
        return Math.max(context.heightAccessor().getMinY() + 1, baseY);
    }
}
