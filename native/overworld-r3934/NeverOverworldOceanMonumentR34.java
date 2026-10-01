package net.minecraft.world.level.levelgen.structure.structures;

import java.util.Arrays;
import net.minecraft.world.level.ChunkPos;
import net.minecraft.world.level.levelgen.Heightmap;
import net.minecraft.world.level.levelgen.structure.Structure;

/**
 * R39.34: place vanilla ocean monuments against the real NeverOverworld seabed.
 *
 * <p>The historical NeverOverworld patch fixed the base at Y=104. Vanilla
 * MonumentBuilding then used fillColumnDown() from that elevated foundation,
 * producing the giant prismarine stilts visible in the reported world.</p>
 *
 * <p>R39.34 first rejects monument candidates whose 58x58 footprint crosses
 * strongly uneven seabed. Accepted candidates are then based near the sampled
 * OCEAN_FLOOR_WG surface. No synthetic terrain platform is created.</p>
 */
public final class NeverOverworldOceanMonumentR34 {
    private static final int EXPECTED_MIN_Y = -512;
    private static final int EXPECTED_HEIGHT = 1024;
    private static final int LEGACY_FLOOD_BASE_Y = 104;
    private static final int MAX_SUPPORT_BUDGET = 6;
    private static final int MAX_SEABED_RELIEF = 12;

    // Two-block spacing across the complete vanilla Monument footprint.
    // MonumentBuilding spans chunkMin-29 .. chunkMin+28.
    private static final int[] OFFSETS = {
        -28,-26,-24,-22,-20,-18,-16,-14,-12,-10,-8,-6,-4,-2,0,
        2,4,6,8,10,12,14,16,18,20,22,24,26,28
    };

    private NeverOverworldOceanMonumentR34() {}

    public static boolean allowsGeneration(final Structure.GenerationContext context) {
        if (!inScope(context)) return true;
        final int[] floors = sampleFloors(context);
        Arrays.sort(floors);
        return floors[floors.length - 1] - floors[0] <= MAX_SEABED_RELIEF;
    }

    public static int resolveBaseY(final Structure.GenerationContext context) {
        if (!inScope(context)) {
            return context.chunkGenerator().getSeaLevel() - 24;
        }

        final int[] floors = sampleFloors(context);
        Arrays.sort(floors);
        final int minFloor = floors[0];
        final int medianFloor = floors[floors.length / 2];

        // On admitted terrain the relief is already bounded. Keep the base
        // near the median, but never leave more than six sampled blocks
        // unsupported below it.
        int baseY = Math.min(medianFloor, minFloor + MAX_SUPPORT_BUDGET);

        // Preserve the old guarantee that the top stays submerged in shallow
        // ocean candidates.
        baseY = Math.min(baseY, LEGACY_FLOOD_BASE_Y);
        return Math.max(context.heightAccessor().getMinY() + 1, baseY);
    }

    private static boolean inScope(final Structure.GenerationContext context) {
        return context.heightAccessor().getMinY() == EXPECTED_MIN_Y
            && context.heightAccessor().getHeight() == EXPECTED_HEIGHT;
    }

    private static int[] sampleFloors(final Structure.GenerationContext context) {
        final ChunkPos chunkPos = context.chunkPos();
        final int anchorX = chunkPos.getMinBlockX();
        final int anchorZ = chunkPos.getMinBlockZ();
        final int[] floors = new int[OFFSETS.length * OFFSETS.length];
        int index = 0;

        for (final int dz : OFFSETS) {
            for (final int dx : OFFSETS) {
                floors[index++] = context.chunkGenerator().getBaseHeight(
                    anchorX + dx,
                    anchorZ + dz,
                    Heightmap.Types.OCEAN_FLOOR_WG,
                    context.heightAccessor(),
                    context.randomState()
                ) - 1;
            }
        }
        return floors;
    }
}
