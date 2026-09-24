package net.minecraft.world.level.chunk;

import java.util.Set;
import net.minecraft.core.Holder;
import net.minecraft.resources.ResourceKey;
import net.minecraft.world.level.ChunkPos;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.levelgen.Heightmap;
import net.minecraft.world.level.levelgen.RandomState;
import net.minecraft.world.level.levelgen.structure.Structure;

/**
 * FIELD-R19 placement adapter for external Overworld structure datapacks.
 *
 * <p>Only structures that were surface/land structures in the supplied packs
 * are intercepted. Ocean-floor and underground structures keep their native
 * placement. Nether and End structure sets are disabled by the companion
 * compatibility datapack, not by this runtime policy.</p>
 */
final class NeverOverworldExternalStructurePolicyR19 {
    private static final int EXPECTED_MIN_Y = -512;
    private static final int EXPECTED_HEIGHT = 1024;
    private static final int MIN_DRY_BASE_HEIGHT = 129;

    private static final Set<String> LAND_SURFACE = Set.of(
        "explorify:badlands_pyramid",
        "explorify:campsite",
        "explorify:dark_forest_settlement",
        "explorify:desert_shrine",
        "explorify:farmstead",
        "explorify:guide_post_cold",
        "explorify:guide_post_warm",
        "explorify:mangrove_hut",
        "explorify:mausoleum",
        "explorify:supply_cache/birch",
        "explorify:supply_cache/dark",
        "explorify:supply_cache/desert",
        "explorify:supply_cache/forest",
        "explorify:supply_cache/jungle",
        "explorify:supply_cache/mangrove",
        "explorify:supply_cache/taiga",
        "explorify:tavern",
        "explorify:watchtower/plains",
        "explorify:watchtower/savanna",
        "explorify:watchtower/taiga",
        "nova_structures:badlands_miner_outpost",
        "nova_structures:bogged_camp",
        "nova_structures:bunker",
        "nova_structures:creeping_crypt",
        "nova_structures:desert_ruins",
        "nova_structures:firewatch_tower_birch",
        "nova_structures:firewatch_tower_cherry",
        "nova_structures:firewatch_tower_dark_oak",
        "nova_structures:firewatch_tower_forest",
        "nova_structures:firewatch_tower_jungle",
        "nova_structures:firewatch_tower_mangrove",
        "nova_structures:firewatch_tower_pale",
        "nova_structures:firewatch_tower_savanna",
        "nova_structures:firewatch_tower_swamp",
        "nova_structures:firewatch_tower_taiga",
        "nova_structures:illager_barracks",
        "nova_structures:illager_camp",
        "nova_structures:illager_manor",
        "nova_structures:jungle_ruins",
        "nova_structures:mangrove_witch_hut",
        "nova_structures:pale_residence",
        "nova_structures:parched_camp",
        "nova_structures:remnant_bee_keeper",
        "nova_structures:remnant_big_remnant",
        "nova_structures:remnant_big_remnant_2",
        "nova_structures:remnant_big_remnant_3",
        "nova_structures:remnant_birch_graveyard",
        "nova_structures:remnant_bridge_remnant",
        "nova_structures:remnant_bundle_tent",
        "nova_structures:remnant_bunny_base",
        "nova_structures:remnant_classic_village",
        "nova_structures:remnant_creeper_homestead",
        "nova_structures:remnant_desert_remnant",
        "nova_structures:remnant_forest_smith",
        "nova_structures:remnant_frog_ranch",
        "nova_structures:remnant_graveyard",
        "nova_structures:remnant_lava_chicken",
        "nova_structures:remnant_medium_remnant",
        "nova_structures:remnant_medium_remnant_2",
        "nova_structures:remnant_miner_hut",
        "nova_structures:remnant_mud_brick_constructor",
        "nova_structures:remnant_ominous_shop",
        "nova_structures:remnant_ruin_farmer",
        "nova_structures:remnant_ruin_smith",
        "nova_structures:remnant_sawmill",
        "nova_structures:remnant_school_remnant",
        "nova_structures:remnant_taiga_castle",
        "nova_structures:remnant_woodland_hud",
        "nova_structures:remnant_zombie_horse_ranch",
        "nova_structures:ruin_town",
        "nova_structures:shrine_biome_tier_1",
        "nova_structures:shrine_biome_tier_2",
        "nova_structures:shrine_biome_tier_3",
        "nova_structures:shrine_biome_tier_4",
        "nova_structures:shrine_biome_tier_5",
        "nova_structures:shrine_combat_tier_1",
        "nova_structures:shrine_combat_tier_2",
        "nova_structures:shrine_combat_tier_3",
        "nova_structures:shrine_combat_tier_4",
        "nova_structures:shrine_combat_tier_5",
        "nova_structures:shrine_combat_tier_6",
        "nova_structures:shrine_tower",
        "nova_structures:stray_camp",
        "nova_structures:stray_fort",
        "nova_structures:tavern_acacia",
        "nova_structures:tavern_birch",
        "nova_structures:tavern_cherry",
        "nova_structures:tavern_dark_oak",
        "nova_structures:tavern_desert",
        "nova_structures:tavern_jungle",
        "nova_structures:tavern_mangrove",
        "nova_structures:tavern_oak",
        "nova_structures:tavern_pale",
        "nova_structures:tavern_snowy",
        "nova_structures:tavern_spruce",
        "nova_structures:tavern_swamp",
        "nova_structures:village_birch",
        "nova_structures:village_jungle",
        "nova_structures:village_swamp",
        "nova_structures:well_birch",
        "nova_structures:well_dark_oak",
        "nova_structures:well_jungle",
        "nova_structures:well_oak",
        "nova_structures:well_savana",
        "nova_structures:well_spruce",
        "nova_structures:wild_ruin",
        "nova_structures:witch_villa",
        "structory_towers:ancient_temple",
        "structory_towers:engineer_tower",
        "structory_towers:farmer_outpost",
        "structory_towers:foraging_outpost",
        "structory_towers:great_toadstool",
        "structory_towers:lighthouse",
        "structory_towers:mirage_outpost",
        "structory_towers:nomad_outpost",
        "structory_towers:overgrown_mangrove",
        "structory_towers:pillager_lookout",
        "structory_towers:quarter_outpost",
        "structory_towers:sacred_relic_temple",
        "structory_towers:small_firetower",
        "structory_towers:taiga_outpost",
        "structory_towers:warped_greatsword",
        "structory_towers:wizard_tower"
    );

    private NeverOverworldExternalStructurePolicyR19() {}

    static boolean handles(final String id) {
        return LAND_SURFACE.contains(id);
    }

    static boolean allows(
        final ChunkGenerator generator,
        final Holder<Structure> structure,
        final RandomState randomState,
        final ChunkAccess heightAccessor,
        final ChunkPos chunkPos,
        final ResourceKey<Level> dimension
    ) {
        if (!Level.OVERWORLD.equals(dimension)
            || heightAccessor.getMinY() != EXPECTED_MIN_Y
            || heightAccessor.getHeight() != EXPECTED_HEIGHT) {
            return true;
        }
        final String id = structure.unwrapKey().map(key -> key.identifier().toString()).orElse("");
        if (!handles(id)) return true;

        final int radius = sampleRadius(id);
        final int centerX = chunkPos.getMiddleBlockX();
        final int centerZ = chunkPos.getMiddleBlockZ();
        final int centerBase = generator.getBaseHeight(
            centerX, centerZ, Heightmap.Types.WORLD_SURFACE_WG, heightAccessor, randomState
        );
        if (centerBase < MIN_DRY_BASE_HEIGHT) return false;

        int drySamples = 1;
        final int[] offsets = {-radius, 0, radius};
        for (final int dx : offsets) {
            for (final int dz : offsets) {
                if (dx == 0 && dz == 0) continue;
                final int base = generator.getBaseHeight(
                    centerX + dx, centerZ + dz,
                    Heightmap.Types.WORLD_SURFACE_WG, heightAccessor, randomState
                );
                if (base >= MIN_DRY_BASE_HEIGHT) ++drySamples;
            }
        }
        return drySamples >= minimumDrySamples(id);
    }

    static int sampleRadius(final String id) {
        if (id.startsWith("nova_structures:village_")
            || id.startsWith("nova_structures:illager_")
            || id.equals("nova_structures:ruin_town")
            || id.equals("nova_structures:stray_fort")) return 40;
        if (id.startsWith("nova_structures:firewatch_tower_")
            || id.startsWith("nova_structures:tavern_")
            || id.startsWith("structory_towers:")) return 24;
        return 20;
    }

    static int minimumDrySamples(final String id) {
        if (id.startsWith("nova_structures:village_")
            || id.startsWith("nova_structures:illager_")
            || id.equals("nova_structures:ruin_town")
            || id.startsWith("nova_structures:tavern_")) {
            return 7;
        }
        return 9;
    }
}
