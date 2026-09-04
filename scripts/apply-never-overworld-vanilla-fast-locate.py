#!/usr/bin/env python3
from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

CHUNK_REL = Path('folia-server/src/minecraft/java/net/minecraft/world/level/chunk/ChunkGenerator.java')
FAST_REL = Path('folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldVanillaFastLocate.java')

# The native NeverFolia fast-locate transformer runs first and leaves this exact
# marker in ChunkGenerator. Insert the vanilla flooded-world path immediately
# before it so Paper's StructuresLocateEvent semantics remain untouched.
MARKER = '''        // NeverFolia start - NR-DEV-1 no-generation fast locate
        // Keep Paper's StructuresLocateEvent semantics first, then intercept only
        // pure NeverFolia structure requests. createReference=true still uses the
        // vanilla path until reference-aware predictive lookup is implemented.
        if (!createReference && NeverOverworldFastLocate.handles(wantedStructures)) {'''

INJECTED = '''        // NeverFolia start - flooded vanilla no-generation fast locate
        // Vanilla surface Jigsaw locate on the 1024-block NeverOverworld height
        // can spend minutes validating unsuitable candidates. Predict only the
        // structures whose generation policy NeverFolia itself changes.
        if (!createReference && NeverOverworldVanillaFastLocate.handles(wantedStructures)) {
            return NeverOverworldVanillaFastLocate.find(this, level, wantedStructures, pos, maxSearchRadius);
        }
        // NeverFolia end - flooded vanilla no-generation fast locate

''' + MARKER

FAST_HELPER = r'''package net.minecraft.world.level.chunk;

import com.mojang.datafixers.util.Pair;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Optional;
import java.util.Set;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Holder;
import net.minecraft.core.HolderSet;
import net.minecraft.core.QuartPos;
import net.minecraft.core.SectionPos;
import net.minecraft.resources.ResourceKey;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.level.ChunkPos;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.biome.Biome;
import net.minecraft.world.level.levelgen.Heightmap;
import net.minecraft.world.level.levelgen.LegacyRandomSource;
import net.minecraft.world.level.levelgen.WorldgenRandom;
import net.minecraft.world.level.levelgen.structure.Structure;
import net.minecraft.world.level.levelgen.structure.StructureSet;
import net.minecraft.world.level.levelgen.structure.placement.RandomSpreadStructurePlacement;

/**
 * Predictive locate path for vanilla structures whose placement is deliberately
 * changed by NeverOverworld.
 *
 * <p>The vanilla locate implementation calls Structure#findValidGenerationPoint
 * while scanning candidates. Surface Jigsaw structures then resolve terrain
 * through getBaseHeight across the 1024-block NeverOverworld density router.
 * A village search can therefore monopolise Folia's global region thread for
 * minutes. This helper reproduces the structure-set candidate grid and weighted
 * choice without loading/generating chunks. It then applies the same cheap
 * biome + dry-footprint rules used by NeverFolia's real generation policy.</p>
 *
 * <p>Only explicitly controlled structure IDs are intercepted. Mixed tags or
 * unrelated vanilla structures retain the vanilla/Paper locate path.</p>
 */
final class NeverOverworldVanillaFastLocate {
    private static final int EXPECTED_MIN_Y = -512;
    private static final int EXPECTED_HEIGHT = 1024;
    private static final int FLOOD_LEVEL = 128;
    private static final int MIN_DRY_BASE_HEIGHT = FLOOD_LEVEL + 1;
    private static final int MAX_CANDIDATE_RINGS = 256;

    private static final String STRONGHOLD = "minecraft:stronghold";
    private static final String SWAMP_HUT = "minecraft:swamp_hut";

    private static final Set<String> DRY_LAND_ONLY = Set.of(
        "minecraft:village_plains",
        "minecraft:village_desert",
        "minecraft:village_savanna",
        "minecraft:village_snowy",
        "minecraft:village_taiga",
        "minecraft:woodland_mansion",
        "minecraft:pillager_outpost",
        "minecraft:desert_pyramid",
        "minecraft:jungle_pyramid",
        "minecraft:igloo"
    );

    private static final Set<String> CONTROLLED = Set.of(
        "minecraft:stronghold",
        "minecraft:village_plains",
        "minecraft:village_desert",
        "minecraft:village_savanna",
        "minecraft:village_snowy",
        "minecraft:village_taiga",
        "minecraft:woodland_mansion",
        "minecraft:pillager_outpost",
        "minecraft:desert_pyramid",
        "minecraft:jungle_pyramid",
        "minecraft:igloo",
        "minecraft:swamp_hut"
    );

    private NeverOverworldVanillaFastLocate() {}

    static boolean handles(final HolderSet<Structure> wantedStructures) {
        boolean any = false;
        for (final Holder<Structure> holder : wantedStructures) {
            final String id = structureId(holder);
            if (id == null || !CONTROLLED.contains(id)) {
                return false;
            }
            any = true;
        }
        return any;
    }

    static Pair<BlockPos, Holder<Structure>> find(
        final ChunkGenerator generator,
        final ServerLevel level,
        final HolderSet<Structure> wantedStructures,
        final BlockPos origin,
        final int requestedRings
    ) {
        if (!Level.OVERWORLD.equals(level.dimension())
            || level.getMinY() != EXPECTED_MIN_Y
            || level.getHeight() != EXPECTED_HEIGHT) {
            return null;
        }

        final Set<String> wantedIds = new HashSet<>();
        for (final Holder<Structure> holder : wantedStructures) {
            final String id = structureId(holder);
            if (id != null && !STRONGHOLD.equals(id)) {
                wantedIds.add(id);
            }
        }

        // Strongholds/End Portals are intentionally disabled in NeverOverworld.
        if (wantedIds.isEmpty()) {
            return null;
        }

        final ChunkGeneratorStructureState state = level.getChunkSource().getGeneratorState();
        final List<SetRef> sets = collectRelevantSets(state, wantedIds);
        if (sets.isEmpty()) {
            return null;
        }

        final int originChunkX = SectionPos.blockToSectionCoord(origin.getX());
        final int originChunkZ = SectionPos.blockToSectionCoord(origin.getZ());
        final int maxRings = Math.max(0, Math.min(requestedRings, MAX_CANDIDATE_RINGS));

        for (int radius = 0; radius <= maxRings; ++radius) {
            final List<Candidate> candidates = new ArrayList<>();
            for (final SetRef setRef : sets) {
                appendRingCandidates(state, setRef, origin, originChunkX, originChunkZ, radius, candidates);
            }
            candidates.sort(CANDIDATE_ORDER);

            for (final Candidate candidate : candidates) {
                final Holder<Structure> generated = predictGeneratedStructure(generator, level, state, candidate);
                final String generatedId = generated == null ? null : structureId(generated);
                if (generatedId != null && wantedIds.contains(generatedId)) {
                    return Pair.of(candidate.placement().getLocatePos(candidate.chunkPos()), generated);
                }
            }
        }
        return null;
    }

    private static List<SetRef> collectRelevantSets(
        final ChunkGeneratorStructureState state,
        final Set<String> wantedIds
    ) {
        final List<SetRef> result = new ArrayList<>();
        for (final Holder<StructureSet> setHolder : state.possibleStructureSets()) {
            final StructureSet set = setHolder.value();
            if (!(set.placement() instanceof RandomSpreadStructurePlacement placement)) {
                continue;
            }
            boolean relevant = false;
            for (final StructureSet.StructureSelectionEntry entry : set.structures()) {
                final String id = structureId(entry.structure());
                if (id != null && wantedIds.contains(id)) {
                    relevant = true;
                    break;
                }
            }
            if (relevant) {
                result.add(new SetRef(setHolder, set, placement));
            }
        }
        return result;
    }

    private static void appendRingCandidates(
        final ChunkGeneratorStructureState state,
        final SetRef setRef,
        final BlockPos origin,
        final int originChunkX,
        final int originChunkZ,
        final int radius,
        final List<Candidate> output
    ) {
        final RandomSpreadStructurePlacement placement = setRef.placement();
        final int spacing = placement.spacing();
        final ResourceKey<StructureSet> setKey = setRef.holder().unwrapKey().orElse(null);

        for (int x = -radius; x <= radius; ++x) {
            final boolean xEdge = x == -radius || x == radius;
            final int zStep = xEdge ? 1 : Math.max(1, radius * 2);
            for (int z = -radius; z <= radius; z += zStep) {
                final int sectorX = originChunkX + spacing * x;
                final int sectorZ = originChunkZ + spacing * z;
                final ChunkPos chunk = placement.getPotentialStructureChunk(state.getLevelSeed(), sectorX, sectorZ);
                if (!placement.isStructureChunk(state, chunk.x(), chunk.z(), setKey)) {
                    continue;
                }
                final BlockPos locatePos = placement.getLocatePos(chunk);
                output.add(new Candidate(setRef, placement, chunk, locatePos.distSqr(origin)));
            }
        }
    }

    /** Reproduces ChunkGenerator#createStructures weighted retry ordering. */
    private static Holder<Structure> predictGeneratedStructure(
        final ChunkGenerator generator,
        final ServerLevel level,
        final ChunkGeneratorStructureState state,
        final Candidate candidate
    ) {
        final ArrayList<StructureSet.StructureSelectionEntry> entries = new ArrayList<>(candidate.setRef().set().structures());
        final WorldgenRandom random = new WorldgenRandom(new LegacyRandomSource(0L));
        random.setLargeFeatureSeed(state.getLevelSeed(), candidate.chunkPos().x(), candidate.chunkPos().z());

        int totalWeight = 0;
        for (final StructureSet.StructureSelectionEntry entry : entries) {
            totalWeight += entry.weight();
        }

        while (!entries.isEmpty() && totalWeight > 0) {
            int draw = random.nextInt(totalWeight);
            int selectedIndex = 0;
            for (int i = 0; i < entries.size(); ++i) {
                draw -= entries.get(i).weight();
                if (draw < 0) {
                    selectedIndex = i;
                    break;
                }
            }

            final StructureSet.StructureSelectionEntry selected = entries.get(selectedIndex);
            final String id = structureId(selected.structure());
            if (id != null
                && CONTROLLED.contains(id)
                && !STRONGHOLD.equals(id)
                && passesNeverOverworldPolicy(generator, level, state, candidate.chunkPos(), selected.structure(), id)) {
                return selected.structure();
            }
            entries.remove(selectedIndex);
            totalWeight -= selected.weight();
        }
        return null;
    }

    private static boolean passesNeverOverworldPolicy(
        final ChunkGenerator generator,
        final ServerLevel level,
        final ChunkGeneratorStructureState state,
        final ChunkPos chunkPos,
        final Holder<Structure> structureHolder,
        final String id
    ) {
        if (!passesBiome(generator, state, chunkPos, structureHolder)) {
            return false;
        }
        if (SWAMP_HUT.equals(id)) {
            // Actual generation re-anchors swamp huts to Y=129. No expensive
            // surface Jigsaw validation is required for locate.
            return true;
        }
        if (!DRY_LAND_ONLY.contains(id)) {
            return false;
        }

        final int radius = sampleRadius(id);
        final int halfRadius = Math.max(1, radius / 2);
        final int centerX = chunkPos.getMiddleBlockX();
        final int centerZ = chunkPos.getMiddleBlockZ();
        final int[] offsets = {-radius, -halfRadius, 0, halfRadius, radius};
        for (final int dx : offsets) {
            for (final int dz : offsets) {
                final int base = generator.getBaseHeight(
                    centerX + dx,
                    centerZ + dz,
                    Heightmap.Types.WORLD_SURFACE_WG,
                    level,
                    state.randomState()
                );
                if (base < MIN_DRY_BASE_HEIGHT) {
                    return false;
                }
            }
        }
        return true;
    }

    private static boolean passesBiome(
        final ChunkGenerator generator,
        final ChunkGeneratorStructureState state,
        final ChunkPos chunkPos,
        final Holder<Structure> structureHolder
    ) {
        final int blockX = chunkPos.getMiddleBlockX();
        final int blockZ = chunkPos.getMiddleBlockZ();
        final Holder<Biome> biome = generator.getBiomeSource().getNoiseBiome(
            QuartPos.fromBlock(blockX),
            QuartPos.fromBlock(FLOOD_LEVEL),
            QuartPos.fromBlock(blockZ),
            state.randomState().sampler()
        );
        return structureHolder.value().biomes().contains(biome);
    }

    private static int sampleRadius(final String id) {
        if ("minecraft:woodland_mansion".equals(id)) {
            return 80;
        }
        if (id.startsWith("minecraft:village_")) {
            return 96;
        }
        if ("minecraft:pillager_outpost".equals(id)) {
            return 64;
        }
        if ("minecraft:desert_pyramid".equals(id) || "minecraft:jungle_pyramid".equals(id)) {
            return 32;
        }
        if ("minecraft:igloo".equals(id)) {
            return 24;
        }
        return 32;
    }

    private static String structureId(final Holder<Structure> holder) {
        final Optional<ResourceKey<Structure>> key = holder.unwrapKey();
        return key.map(resourceKey -> resourceKey.identifier().toString()).orElse(null);
    }

    private static String setId(final SetRef setRef) {
        return setRef.holder().unwrapKey().map(key -> key.identifier().toString()).orElse("");
    }

    private static final Comparator<Candidate> CANDIDATE_ORDER = Comparator
        .comparingDouble(Candidate::distanceSq)
        .thenComparingInt(candidate -> candidate.chunkPos().x())
        .thenComparingInt(candidate -> candidate.chunkPos().z())
        .thenComparing(candidate -> setId(candidate.setRef()));

    private record SetRef(Holder<StructureSet> holder, StructureSet set, RandomSpreadStructurePlacement placement) {}

    private record Candidate(
        SetRef setRef,
        RandomSpreadStructurePlacement placement,
        ChunkPos chunkPos,
        double distanceSq
    ) {}
}
'''


def apply(root: Path) -> None:
    chunk = root / CHUNK_REL
    helper = root / FAST_REL
    if not chunk.is_file():
        raise SystemExit(f'ChunkGenerator not found: {chunk}')

    text = chunk.read_text(encoding='utf-8')
    if 'NeverOverworldVanillaFastLocate.handles(wantedStructures)' not in text:
        if MARKER not in text:
            raise SystemExit('[NeverFolia][vanilla fast locate] native fast-locate marker not found')
        text = text.replace(MARKER, INJECTED, 1)
        chunk.write_text(text, encoding='utf-8')

    helper.write_text(FAST_HELPER, encoding='utf-8')
    for forbidden in ('moonrise$syncLoadNonFull', 'getChunk('):
        if forbidden in FAST_HELPER:
            raise SystemExit(f'[NeverFolia][vanilla fast locate] chunk-loading primitive leaked into helper: {forbidden}')
    print('[NeverFolia][NeverOverworld vanilla fast locate] predictive flooded-structure hook applied')
    print(f'  generator: {chunk}')
    print(f'  helper: {helper}')


def self_test() -> None:
    with tempfile.TemporaryDirectory(prefix='nr-vanilla-fast-locate-') as tmp:
        root = Path(tmp)
        chunk = root / CHUNK_REL
        chunk.parent.mkdir(parents=True, exist_ok=True)
        chunk.write_text('''class ChunkGenerator {\n    void x() {\n        // NeverFolia start - NR-DEV-1 no-generation fast locate\n        // Keep Paper's StructuresLocateEvent semantics first, then intercept only\n        // pure NeverFolia structure requests. createReference=true still uses the\n        // vanilla path until reference-aware predictive lookup is implemented.\n        if (!createReference && NeverOverworldFastLocate.handles(wantedStructures)) {\n            return NeverOverworldFastLocate.find(this, level, wantedStructures, pos, maxSearchRadius);\n        }\n    }\n}\n''', encoding='utf-8')
        apply(root)
        patched = chunk.read_text(encoding='utf-8')
        helper = (root / FAST_REL).read_text(encoding='utf-8')
        required = [
            'NeverOverworldVanillaFastLocate.handles(wantedStructures)',
            '!createReference',
            'minecraft:village_plains',
            'minecraft:woodland_mansion',
            'minecraft:swamp_hut',
            'minecraft:stronghold',
            'getPotentialStructureChunk',
            'isStructureChunk',
            'getNoiseBiome',
            'WORLD_SURFACE_WG',
            'return 96;',
            'return 80;',
            'MAX_CANDIDATE_RINGS = 256',
        ]
        corpus = patched + helper
        missing = [marker for marker in required if marker not in corpus]
        if missing:
            raise SystemExit(f'[NeverFolia][vanilla fast locate self-test] missing markers: {missing}')
        for forbidden in ('moonrise$syncLoadNonFull', 'getChunk('):
            if forbidden in helper:
                raise SystemExit(f'[NeverFolia][vanilla fast locate self-test] forbidden primitive: {forbidden}')
        if patched.index('NeverOverworldVanillaFastLocate.handles') > patched.index('NeverOverworldFastLocate.handles'):
            raise SystemExit('[NeverFolia][vanilla fast locate self-test] flooded vanilla hook must precede native hook')
    print('[NeverFolia][NeverOverworld vanilla fast locate] SELF-TEST OK')


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('folia_root', nargs='?', type=Path)
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if args.folia_root is None:
        parser.error('folia_root is required unless --self-test is used')
    apply(args.folia_root.resolve())


if __name__ == '__main__':
    main()
