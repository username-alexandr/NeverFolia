package net.minecraft.world.level.chunk;

import java.util.Set;
import net.minecraft.core.Holder;
import net.minecraft.core.HolderSet;
import net.minecraft.core.QuartPos;
import net.minecraft.resources.ResourceKey;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.level.ChunkPos;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.levelgen.structure.Structure;
import net.minecraft.world.level.levelgen.structure.structures.JigsawStructure;
import net.minecraft.world.level.levelgen.structure.structures.NeverNetherStructurePlacement;

/**
 * R39.38 bridge from the existing NeverOverworld fast-locate engine to the
 * NeverNether placement resolver.
 *
 * <p>Locate and normal generation intentionally share the same bounded
 * coarse-to-fine resolver. Locate additionally validates the root GenerationStub
 * so it cannot return a candidate whose selected start piece/jigsaw/padding is
 * invalid. Recursive Jigsaw expansion is not executed while locating.</p>
 */
final class NeverNetherFastLocatePolicy {
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

    private NeverNetherFastLocatePolicy() {}

    static boolean handles(HolderSet<Structure> holders) {
        boolean any = false;
        for (Holder<Structure> holder : holders) {
            final String id = structureId(holder);
            if (id == null) {
                return false;
            }
            if (!id.startsWith("neverfolia:") && !CUSTOM_IDS.contains(id)) {
                return false;
            }
            any = true;
        }
        return any;
    }

    static int clampLocateRadius(HolderSet<Structure> holders, int requestedRadius) {
        boolean any = false;
        for (Holder<Structure> holder : holders) {
            final String id = structureId(holder);
            if (id == null || !CUSTOM_IDS.contains(id)) {
                return requestedRadius;
            }
            any = true;
        }
        if (!any) {
            return requestedRadius;
        }
        // NeverNether custom sets are intentionally sparse (20/44/80/192 chunk
        // spacing). Searching hundreds of rings on a Folia tick thread is not a
        // valid fallback. Six rings already covers ~7680 blocks for custom_major,
        // well beyond the 1000-1600 block target-success distance in the spec.
        return Math.min(requestedRadius, 6);
    }

    static boolean isCustomNether(Holder<Structure> holder) {
        final String id = structureId(holder);
        return id != null && CUSTOM_IDS.contains(id);
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

        final int startY = NeverNetherStructurePlacement.resolveStartY(
            context,
            jigsaw.getStartPool(),
            0
        );
        if (startY == NeverNetherStructurePlacement.REJECT_Y) {
            return false;
        }

        // Mirror Structure.isValidBiome() before touching the root pool.
        if (!structure.biomes().contains(
            generator.getBiomeSource().getNoiseBiome(
                QuartPos.fromBlock(chunkPos.getMinBlockX()),
                QuartPos.fromBlock(startY),
                QuartPos.fromBlock(chunkPos.getMinBlockZ()),
                state.randomState().sampler()
            )
        )) {
            return false;
        }

        // R39.38 root confirmation. With the old getBaseColumn resolver this
        // call was too expensive; with the shared coarse-to-fine resolver it is
        // bounded. findValidGenerationPoint creates only the GenerationStub:
        // it validates the selected root pool element, start_jigsaw_name,
        // rotation/bounding box, dimension padding and biome. The size=11
        // recursive Jigsaw expansion is stored in the stub's consumer and is
        // NOT executed by /locate.
        return structure.findValidGenerationPoint(context).isPresent();
    }

    private static String structureId(Holder<Structure> holder) {
        return holder.unwrapKey()
            .map(ResourceKey::identifier)
            .map(Object::toString)
            .orElse(null);
    }
}
