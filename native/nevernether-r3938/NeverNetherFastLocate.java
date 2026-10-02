package net.minecraft.world.level.chunk;

import com.mojang.datafixers.util.Pair;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Holder;
import net.minecraft.core.HolderSet;
import net.minecraft.core.SectionPos;
import net.minecraft.resources.ResourceKey;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.level.ChunkPos;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.levelgen.LegacyRandomSource;
import net.minecraft.world.level.levelgen.WorldgenRandom;
import net.minecraft.world.level.levelgen.structure.Structure;
import net.minecraft.world.level.levelgen.structure.StructureSet;
import net.minecraft.world.level.levelgen.structure.placement.RandomSpreadStructurePlacement;
import net.minecraft.world.level.levelgen.structure.placement.StructurePlacement;
import net.minecraft.world.level.levelgen.structure.structures.JigsawStructure;
import net.minecraft.world.level.levelgen.structure.structures.NeverNetherStructurePlacement;

/**
 * R39.38 locate path for NeverNether custom structures.
 *
 * <p>Vanilla /locate normally asks StructureCheck to execute the complete
 * JigsawStructure generation predicate for every searched candidate. For
 * NeverNether that included full 656-block getBaseColumn scans and could pin a
 * Folia region thread for tens of seconds. This helper enumerates the exact
 * RandomSpread candidates and weighted structure selection, then uses the
 * bounded NeverNether fast terrain predictor first, followed by the exact\n * generation predicate only for the rare candidates that survive the prefilter.</p>
 */
final class NeverNetherFastLocate {
    private static final int MAX_CANDIDATE_RINGS = 100;

    private static final Set<String> CUSTOM_IDS = Set.of(
        "nova_structures:nether_keep",
        "nova_structures:piglin_donjon",
        "nova_structures:sealing_halls",
        "nova_structures:nether_port",
        "nova_structures:hamlet",
        "nova_structures:piglin_outstation",
        "explorify:black_spiral",
        "hearths:crimson_tower",
        "hearths:warped_tower",
        "structory_towers:nether/fortress_tower",
        "structory_towers:nether/strange_outpost",
        "structory_towers:nether/warped_outpost",
        "hearths:netherrack_spiral",
        "nova_structures:nether_skeleton_tower_fort",
        "nova_structures:nether_skeleton_tower_warped",
        "nova_structures:nether_skeleton_tower_crimson",
        "nova_structures:nether_skeleton_tower_soul",
        "nova_structures:piglin_camp",
        "nova_structures:piglin_camp_collony",
        "repurposed_structures:monument_nether"
    );

    private static final Comparator<Candidate> CANDIDATE_ORDER =
        Comparator.comparingDouble(Candidate::distanceSqr)
            .thenComparingInt(c -> c.chunkPos().x())
            .thenComparingInt(c -> c.chunkPos().z());

    private NeverNetherFastLocate() {}

    static boolean handles(HolderSet<Structure> holders) {
        boolean any = false;
        for (Holder<Structure> holder : holders) {
            final String id = structureId(holder);
            if (id == null || !CUSTOM_IDS.contains(id)) {
                return false;
            }
            any = true;
        }
        return any;
    }

    static boolean handles(ServerLevel level, HolderSet<Structure> holders) {
        return Level.NETHER.equals(level.dimension()) && handles(holders);
    }

    static Pair<BlockPos, Holder<Structure>> find(
        ChunkGenerator generator,
        ServerLevel level,
        HolderSet<Structure> holders,
        BlockPos origin,
        int radius
    ) {
        if (!handles(level, holders)) {
            return null;
        }

        final ChunkGeneratorStructureState state = level.getChunkSource().getGeneratorState();
        final Set<String> requested = new HashSet<>();
        for (Holder<Structure> holder : holders) {
            final String id = structureId(holder);
            if (id != null) {
                requested.add(id);
            }
        }

        final List<SetRef> sets = collectRelevantSets(state, requested);
        if (sets.isEmpty()) {
            return null;
        }

        final int centerChunkX = SectionPos.blockToSectionCoord(origin.getX());
        final int centerChunkZ = SectionPos.blockToSectionCoord(origin.getZ());
        final int maxRing = Math.max(0, Math.min(radius, MAX_CANDIDATE_RINGS));

        for (int ring = 0; ring <= maxRing; ++ring) {
            final List<Candidate> candidates = new ArrayList<>();
            for (SetRef set : sets) {
                appendRingCandidates(state, set, origin, centerChunkX, centerChunkZ, ring, candidates);
            }
            candidates.sort(CANDIDATE_ORDER);

            for (Candidate candidate : candidates) {
                final Holder<Structure> generated =
                    predictGeneratedStructure(generator, level, state, candidate);
                final String id = generated == null ? null : structureId(generated);
                if (id != null && requested.contains(id)) {
                    return Pair.of(
                        candidate.placement().getLocatePos(candidate.chunkPos()),
                        generated
                    );
                }
            }
        }
        return null;
    }

    private static List<SetRef> collectRelevantSets(
        ChunkGeneratorStructureState state,
        Set<String> requested
    ) {
        final List<SetRef> result = new ArrayList<>();
        for (Holder<StructureSet> holder : state.possibleStructureSets()) {
            final StructureSet set = holder.value();
            final StructurePlacement placement = set.placement();
            if (!(placement instanceof RandomSpreadStructurePlacement randomSpread)) {
                continue;
            }

            boolean relevant = false;
            for (StructureSet.StructureSelectionEntry entry : set.structures()) {
                final String id = structureId(entry.structure());
                if (id != null && requested.contains(id)) {
                    relevant = true;
                    break;
                }
            }
            if (relevant) {
                result.add(new SetRef(holder, set, randomSpread));
            }
        }
        return result;
    }

    private static void appendRingCandidates(
        ChunkGeneratorStructureState state,
        SetRef setRef,
        BlockPos origin,
        int centerChunkX,
        int centerChunkZ,
        int ring,
        List<Candidate> out
    ) {
        final RandomSpreadStructurePlacement placement = setRef.placement();
        final int spacing = placement.spacing();
        final ResourceKey<StructureSet> setKey = setRef.holder().unwrapKey().orElse(null);

        for (int dx = -ring; dx <= ring; ++dx) {
            final boolean edgeX = dx == -ring || dx == ring;
            for (int dz = -ring; dz <= ring; dz += edgeX ? 1 : Math.max(1, ring * 2)) {
                final int gridX = centerChunkX + spacing * dx;
                final int gridZ = centerChunkZ + spacing * dz;
                final ChunkPos chunk = placement.getPotentialStructureChunk(
                    state.getLevelSeed(),
                    gridX,
                    gridZ
                );
                if (!placement.isStructureChunk(state, chunk.x(), chunk.z(), setKey)) {
                    continue;
                }
                final BlockPos locate = placement.getLocatePos(chunk);
                out.add(new Candidate(
                    setRef,
                    placement,
                    chunk,
                    origin.distSqr(locate)
                ));
            }
        }
    }

    private static Holder<Structure> predictGeneratedStructure(
        ChunkGenerator generator,
        ServerLevel level,
        ChunkGeneratorStructureState state,
        Candidate candidate
    ) {
        final ArrayList<StructureSet.StructureSelectionEntry> choices =
            new ArrayList<>(candidate.setRef().set().structures());

        final WorldgenRandom random = new WorldgenRandom(new LegacyRandomSource(0L));
        random.setLargeFeatureSeed(
            state.getLevelSeed(),
            candidate.chunkPos().x(),
            candidate.chunkPos().z()
        );

        int totalWeight = 0;
        for (StructureSet.StructureSelectionEntry entry : choices) {
            totalWeight += entry.weight();
        }

        while (!choices.isEmpty() && totalWeight > 0) {
            int roll = random.nextInt(totalWeight);
            int selectedIndex = 0;
            for (int i = 0; i < choices.size(); ++i) {
                roll -= choices.get(i).weight();
                if (roll < 0) {
                    selectedIndex = i;
                    break;
                }
            }

            final StructureSet.StructureSelectionEntry selected = choices.get(selectedIndex);
            if (passesNeverNetherTerrain(
                generator,
                level,
                state,
                candidate.chunkPos(),
                selected.structure()
            )) {
                return selected.structure();
            }

            choices.remove(selectedIndex);
            totalWeight -= selected.weight();
        }
        return null;
    }

    private static boolean passesNeverNetherTerrain(
        ChunkGenerator generator,
        ServerLevel level,
        ChunkGeneratorStructureState state,
        ChunkPos chunkPos,
        Holder<Structure> holder
    ) {
        if (!(holder.value() instanceof JigsawStructure jigsaw)) {
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

        if (!NeverNetherStructurePlacement.fastLocatePasses(
            context,
            jigsaw.getStartPool()
        )) {
            return false;
        }

        // The density scan is intentionally only a prefilter. A Jigsaw can
        // still fail because of its exact start-Y, bounding box, pool expansion,
        // or other normal structure predicates. Confirm the rare surviving
        // candidate with the real generation predicate before /locate returns
        // it. This keeps locate exact without running full Jigsaw assembly for
        // every RandomSpread candidate in the search radius.
        return structure.findValidGenerationPoint(context).isPresent();
    }

    private static String structureId(Holder<Structure> holder) {
        return holder.unwrapKey()
            .map(key -> key.identifier().toString())
            .orElse(null);
    }

    private record SetRef(
        Holder<StructureSet> holder,
        StructureSet set,
        RandomSpreadStructurePlacement placement
    ) {}

    private record Candidate(
        SetRef setRef,
        RandomSpreadStructurePlacement placement,
        ChunkPos chunkPos,
        double distanceSqr
    ) {}
}
