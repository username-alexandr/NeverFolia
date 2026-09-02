#!/usr/bin/env python3
from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

CHUNK_REL = Path('folia-server/src/minecraft/java/net/minecraft/world/level/chunk/ChunkGenerator.java')
PLACEMENT_REL = Path('folia-server/src/minecraft/java/net/minecraft/world/level/levelgen/structure/structures/NeverOverworldStructurePlacement.java')
FAST_REL = Path('folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldFastLocate.java')

MARKER = '        // Paper end\n        ChunkGeneratorStructureState generatorState = level.getChunkSource().getGeneratorState();'
INJECTED = '''        // Paper end
        // NeverFolia start - NR-DEV-1 no-generation fast locate
        // Keep Paper's StructuresLocateEvent semantics first, then intercept only
        // pure NeverFolia structure requests. createReference=true still uses the
        // vanilla path until reference-aware predictive lookup is implemented.
        if (!createReference && NeverOverworldFastLocate.handles(wantedStructures)) {
            return NeverOverworldFastLocate.find(this, level, wantedStructures, pos, maxSearchRadius);
        }
        // NeverFolia end - NR-DEV-1 no-generation fast locate
        ChunkGeneratorStructureState generatorState = level.getChunkSource().getGeneratorState();'''

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
import net.minecraft.core.SectionPos;
import net.minecraft.resources.ResourceKey;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.level.ChunkPos;
import net.minecraft.world.level.levelgen.LegacyRandomSource;
import net.minecraft.world.level.levelgen.WorldgenRandom;
import net.minecraft.world.level.levelgen.structure.Structure;
import net.minecraft.world.level.levelgen.structure.StructureSet;
import net.minecraft.world.level.levelgen.structure.placement.RandomSpreadStructurePlacement;
import net.minecraft.world.level.levelgen.structure.structures.JigsawStructure;
import net.minecraft.world.level.levelgen.structure.structures.NeverOverworldStructurePlacement;

/**
 * Predictive locate path for NR-DEV-1 native structures.
 *
 * <p>This class deliberately never asks Moonrise for STRUCTURE_STARTS and never
 * calls LevelReader#getChunk. Candidate chunks come from the registered
 * RandomSpreadStructurePlacement grid and terrain acceptance uses the exact same
 * NeverOverworld Jigsaw Y resolver as real generation.</p>
 */
final class NeverOverworldFastLocate {
    private static final String NAMESPACE = "neverfolia";
    private static final int MAX_CANDIDATE_RINGS = 256;

    private NeverOverworldFastLocate() {}

    static boolean handles(final HolderSet<Structure> wantedStructures) {
        boolean any = false;
        for (final Holder<Structure> holder : wantedStructures) {
            final String id = structureId(holder);
            if (id == null || !id.startsWith(NAMESPACE + ":")) {
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
        final ChunkGeneratorStructureState state = level.getChunkSource().getGeneratorState();
        final Set<String> wantedIds = new HashSet<>();
        for (final Holder<Structure> holder : wantedStructures) {
            final String id = structureId(holder);
            if (id != null) {
                wantedIds.add(id);
            }
        }

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
            for (int z = -radius; z <= radius; z += xEdge ? 1 : radius * 2) {
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
            if (passesNeverOverworldTerrain(generator, level, state, candidate.chunkPos(), selected.structure())) {
                return selected.structure();
            }
            entries.remove(selectedIndex);
            totalWeight -= selected.weight();
        }
        return null;
    }

    private static boolean passesNeverOverworldTerrain(
        final ChunkGenerator generator,
        final ServerLevel level,
        final ChunkGeneratorStructureState state,
        final ChunkPos chunkPos,
        final Holder<Structure> structureHolder
    ) {
        final String id = structureId(structureHolder);
        if (id == null || !id.startsWith(NAMESPACE + ":")) {
            return false;
        }
        if (!(structureHolder.value() instanceof JigsawStructure jigsaw)) {
            return false;
        }

        final Structure structure = structureHolder.value();
        final Structure.GenerationContext context = new Structure.GenerationContext(
            level.registryAccess(),
            generator,
            generator.getBiomeSource(),
            state.randomState(),
            generator.getStructureManager(),
            state.getLevelSeed(),
            chunkPos,
            level,
            structure.biomes()::contains
        );
        return NeverOverworldStructurePlacement.resolveStartY(context, jigsaw.getStartPool(), 0)
            != NeverOverworldStructurePlacement.REJECT_Y;
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


def make_placement_public(path: Path) -> None:
    text = path.read_text(encoding='utf-8')
    replacements = {
        'final class NeverOverworldStructurePlacement {': 'public final class NeverOverworldStructurePlacement {',
        '    static final int REJECT_Y =': '    public static final int REJECT_Y =',
        '    static int resolveStartY(': '    public static int resolveStartY(',
    }
    for old, new in replacements.items():
        if new in text:
            continue
        if old not in text:
            raise SystemExit(f'[NeverFolia][fast locate] required placement marker not found: {old}')
        text = text.replace(old, new, 1)
    path.write_text(text, encoding='utf-8')


def apply(root: Path) -> None:
    chunk = root / CHUNK_REL
    placement = root / PLACEMENT_REL
    helper = root / FAST_REL
    if not chunk.is_file():
        raise SystemExit(f'ChunkGenerator not found: {chunk}')
    if not placement.is_file():
        raise SystemExit(f'NeverOverworld placement helper not found: {placement}')

    make_placement_public(placement)
    text = chunk.read_text(encoding='utf-8')
    if 'NeverOverworldFastLocate.handles(wantedStructures)' not in text:
        if MARKER not in text:
            raise SystemExit('[NeverFolia][fast locate] Paper post-event locate marker not found')
        text = text.replace(MARKER, INJECTED, 1)
        chunk.write_text(text, encoding='utf-8')

    helper.write_text(FAST_HELPER, encoding='utf-8')
    if 'moonrise$syncLoadNonFull' in FAST_HELPER or 'getChunk(' in FAST_HELPER:
        raise SystemExit('[NeverFolia][fast locate] helper contains a chunk-load primitive')
    print('[NeverFolia][NeverOverworld fast locate] predictive no-generation hook applied')
    print(f'  generator: {chunk}')
    print(f'  helper: {helper}')
    print(f'  placement helper: {placement}')


def self_test() -> None:
    with tempfile.TemporaryDirectory(prefix='nr-fast-locate-') as tmp:
        root = Path(tmp)
        chunk = root / CHUNK_REL
        placement = root / PLACEMENT_REL
        chunk.parent.mkdir(parents=True, exist_ok=True)
        placement.parent.mkdir(parents=True, exist_ok=True)
        chunk.write_text('''class ChunkGenerator {\n    void x() {\n        // Paper end\n        ChunkGeneratorStructureState generatorState = level.getChunkSource().getGeneratorState();\n    }\n}\n''', encoding='utf-8')
        placement.write_text('''final class NeverOverworldStructurePlacement {\n    static final int REJECT_Y = -1;\n    static int resolveStartY(Object a, Object b, int c) { return 0; }\n}\n''', encoding='utf-8')
        apply(root)
        patched = chunk.read_text(encoding='utf-8')
        public_placement = placement.read_text(encoding='utf-8')
        helper = (root / FAST_REL).read_text(encoding='utf-8')
        required = [
            'NeverOverworldFastLocate.handles(wantedStructures)',
            '!createReference',
            'getPotentialStructureChunk',
            'isStructureChunk',
            'setLargeFeatureSeed',
            'resolveStartY',
            'MAX_CANDIDATE_RINGS = 256',
            'structure.biomes()::contains',
        ]
        corpus = patched + helper
        missing = [marker for marker in required if marker not in corpus]
        if missing:
            raise SystemExit(f'[NeverFolia][fast locate self-test] missing markers: {missing}')
        if 'moonrise$syncLoadNonFull' in helper or 'getChunk(' in helper:
            raise SystemExit('[NeverFolia][fast locate self-test] chunk-loading primitive leaked into helper')
        if 'public final class NeverOverworldStructurePlacement' not in public_placement:
            raise SystemExit('[NeverFolia][fast locate self-test] placement class not public')
        if 'public static int resolveStartY' not in public_placement:
            raise SystemExit('[NeverFolia][fast locate self-test] resolver not public')
    print('[NeverFolia][NeverOverworld fast locate] SELF-TEST OK')


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
