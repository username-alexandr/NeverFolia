package net.minecraft.world.level.chunk;

import java.util.Map;
import java.util.Set;
import net.minecraft.core.Holder;
import net.minecraft.core.HolderSet;
import net.minecraft.resources.ResourceKey;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.level.ChunkPos;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.levelgen.DensityFunction;
import net.minecraft.world.level.levelgen.structure.Structure;
import net.minecraft.world.level.levelgen.structure.structures.JigsawStructure;

/**
 * R39.38 prefilter for the existing NeverOverworldFastLocate engine.
 *
 * <p>It performs only sparse direct final-density sampling. A candidate that
 * survives this filter is then checked by the exact normal structure
 * generation predicate before /locate returns it. Normal chunk generation is
 * untouched.</p>
 */
final class NeverNetherFastLocatePolicy {
    private static final int MIN_SAFE_Y = -123;
    private static final int MAX_SAFE_Y = 378;
    private static final int LAVA_SURFACE_Y = 32;
    private static final int CLEARANCE = 8;
    private static final int VERTICAL_STEP = 4;

    private enum Mode { CAVERN, LAVA_BASIN }

    private record Profile(int minY, int maxY, Mode mode, boolean largeLava) {}

    private static final Map<String, Profile> PROFILES = Map.ofEntries(
        Map.entry("nova_structures:nether_keep", new Profile(16, 300, Mode.CAVERN, false)),
        Map.entry("nova_structures:piglin_donjon", new Profile(-80, 192, Mode.CAVERN, false)),
        Map.entry("nova_structures:sealing_halls", new Profile(-112, 120, Mode.CAVERN, false)),
        Map.entry("nova_structures:nether_port", new Profile(-32, 260, Mode.CAVERN, false)),
        Map.entry("nova_structures:hamlet", new Profile(16, 300, Mode.CAVERN, false)),
        Map.entry("nova_structures:piglin_outstation", new Profile(64, 360, Mode.CAVERN, false)),
        Map.entry("explorify:black_spiral", new Profile(16, 300, Mode.CAVERN, false)),
        Map.entry("hearths:crimson_tower", new Profile(64, 360, Mode.CAVERN, false)),
        Map.entry("hearths:warped_tower", new Profile(64, 360, Mode.CAVERN, false)),
        Map.entry("structory_towers:nether/fortress_tower", new Profile(64, 360, Mode.CAVERN, false)),
        Map.entry("structory_towers:nether/strange_outpost", new Profile(64, 360, Mode.CAVERN, false)),
        Map.entry("structory_towers:nether/warped_outpost", new Profile(64, 360, Mode.CAVERN, false)),
        Map.entry("hearths:netherrack_spiral", new Profile(16, 300, Mode.CAVERN, false)),
        Map.entry("nova_structures:nether_skeleton_tower_fort", new Profile(16, 300, Mode.CAVERN, false)),
        Map.entry("nova_structures:nether_skeleton_tower_warped", new Profile(16, 300, Mode.CAVERN, false)),
        Map.entry("nova_structures:nether_skeleton_tower_crimson", new Profile(16, 300, Mode.CAVERN, false)),
        Map.entry("nova_structures:nether_skeleton_tower_soul", new Profile(16, 300, Mode.CAVERN, false)),
        Map.entry("nova_structures:piglin_camp", new Profile(-32, 260, Mode.CAVERN, false)),
        Map.entry("nova_structures:piglin_camp_collony", new Profile(-32, 260, Mode.CAVERN, false)),
        Map.entry("repurposed_structures:monument_nether", new Profile(-32, 64, Mode.LAVA_BASIN, true))
    );

    private NeverNetherFastLocatePolicy() {}

    static boolean handles(HolderSet<Structure> holders) {
        boolean any = false;
        for (Holder<Structure> holder : holders) {
            final String id = structureId(holder);
            if (id == null) {
                return false;
            }
            if (!id.startsWith("neverfolia:") && !PROFILES.containsKey(id)) {
                return false;
            }
            any = true;
        }
        return any;
    }

    static boolean isCustomNether(Holder<Structure> holder) {
        final String id = structureId(holder);
        return id != null && PROFILES.containsKey(id);
    }

    static boolean passesNetherTerrain(
        ChunkGenerator generator,
        ServerLevel level,
        ChunkGeneratorStructureState state,
        ChunkPos chunkPos,
        Holder<Structure> holder
    ) {
        if (!Level.NETHER.equals(level.dimension())) {
            return false;
        }

        final String id = structureId(holder);
        final Profile profile = id == null ? null : PROFILES.get(id);
        if (profile == null || !(holder.value() instanceof JigsawStructure)) {
            return false;
        }

        final Structure structure = holder.value();
        final Structure.GenerationContext context = new Structure.GenerationContext(
            level.registryAccess(),
            generator,
            generator.getBiomeSource(),
            state.randomState(),
            level.getStructureManager(),
            state.getLevelSeed(),
            chunkPos,
            level,
            structure.biomes()::contains
        );

        if (!cheapTerrainPasses(context, profile, id)) {
            return false;
        }

        // Only a sparse-filter survivor pays the exact Jigsaw predicate cost.
        // This guarantees that /locate never returns a false coordinate.
        return structure.findValidGenerationPoint(context).isPresent();
    }

    private static boolean cheapTerrainPasses(
        Structure.GenerationContext context,
        Profile profile,
        String id
    ) {
        final int x = context.chunkPos().getMinBlockX();
        final int z = context.chunkPos().getMinBlockZ();
        final long hash = mix64(
            context.seed()
                ^ ((long) context.chunkPos().x() * 0x9E3779B97F4A7C15L)
                ^ ((long) context.chunkPos().z() * 0xC2B2AE3D27D4EB4FL)
                ^ id.hashCode()
        );
        if (profile.mode == Mode.LAVA_BASIN) {
            return cheapLavaBasin(context, profile, x, z, hash);
        }
        return cheapCavern(context, profile, x, z, hash);
    }

    private static boolean cheapCavern(
        Structure.GenerationContext context,
        Profile profile,
        int x,
        int z,
        long hash
    ) {
        final int lo = Math.max(Math.max(MIN_SAFE_Y, profile.minY), LAVA_SURFACE_Y);
        final int hi = Math.min(Math.min(MAX_SAFE_Y - CLEARANCE, profile.maxY), 370);
        if (lo > hi) {
            return false;
        }

        final DensityFunction density = context.randomState().router().finalDensity();
        final int offset = Math.floorMod((int) (hash ^ (hash >>> 32)), VERTICAL_STEP);
        int previousY = lo;
        double previous = sample(density, x, previousY, z);

        for (int y = lo + VERTICAL_STEP + offset; y <= hi; y += VERTICAL_STEP) {
            final double current = sample(density, x, y, z);

            // A solid-to-open transition exists somewhere in the small interval.
            if (previous > 0.0 && current <= 0.0) {
                final int from = Math.max(lo, y - VERTICAL_STEP - 1);
                final int to = Math.min(hi, y);
                for (int exactY = from; exactY <= to; ++exactY) {
                    if (sample(density, x, exactY, z) > 0.0
                        && sample(density, x, exactY + 1, z) <= 0.0
                        && sample(density, x, exactY + 4, z) <= 0.0
                        && sample(density, x, exactY + CLEARANCE, z) <= 0.0) {
                        return true;
                    }
                }
            }
            previousY = y;
            previous = current;
        }
        return false;
    }

    private static boolean cheapLavaBasin(
        Structure.GenerationContext context,
        Profile profile,
        int x,
        int z,
        long hash
    ) {
        final DensityFunction density = context.randomState().router().finalDensity();
        int open = 0;
        for (int dx = -24; dx <= 24; dx += 24) {
            for (int dz = -24; dz <= 24; dz += 24) {
                if (sample(density, x + dx, LAVA_SURFACE_Y - 1, z + dz) <= 0.0) {
                    ++open;
                }
            }
        }
        if (profile.largeLava && open < 7) {
            return false;
        }

        final int lo = Math.max(MIN_SAFE_Y, profile.minY);
        final int hi = Math.min(LAVA_SURFACE_Y - 2, profile.maxY);
        final int offset = Math.floorMod((int) mix64(hash), VERTICAL_STEP);
        for (int y = hi - offset; y >= lo; y -= VERTICAL_STEP) {
            if (sample(density, x, y, z) > 0.0) {
                return true;
            }
        }
        return false;
    }

    private static double sample(DensityFunction density, int x, int y, int z) {
        return density.compute(new DensityFunction.SinglePointContext(x, y, z));
    }

    private static String structureId(Holder<Structure> holder) {
        return holder.unwrapKey()
            .map(ResourceKey::identifier)
            .map(Object::toString)
            .orElse(null);
    }

    private static long mix64(long z) {
        z = (z ^ (z >>> 30)) * 0xBF58476D1CE4E5B9L;
        z = (z ^ (z >>> 27)) * 0x94D049BB133111EBL;
        return z ^ (z >>> 31);
    }
}
