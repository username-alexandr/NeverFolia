package net.minecraft.world.level.chunk;

import net.minecraft.SharedConstants;
import net.minecraft.server.Bootstrap;

/** FIELD-R19 regression checks for imported-structure island admission. */
public final class ExternalStructurePolicyR19Smoke {
    private static int checks;

    private ExternalStructurePolicyR19Smoke() {}

    private static void check(final boolean condition, final String message) {
        ++checks;
        if (!condition) throw new AssertionError(message);
    }

    public static void main(final String[] args) {
        final java.io.PrintStream out = System.out;
        SharedConstants.tryDetectVersion();
        Bootstrap.bootStrap();

        check(NeverOverworldExternalStructurePolicyR19.MIN_DRY_SURFACE_Y == 129,
            "R19 surface floor must remain Y129");

        check(NeverOverworldExternalStructurePolicyR19.radiusForId("nova_structures:tavern_oak") == 64,
            "Dungeons & Taverns surface structure must be island-adapted");
        check(NeverOverworldExternalStructurePolicyR19.radiusForId("explorify:tavern") == 72,
            "Explorify tavern must be island-adapted");
        check(NeverOverworldExternalStructurePolicyR19.radiusForId("structory_towers:wizard_tower") == 32,
            "Structory wizard tower must be island-adapted");
        check(NeverOverworldExternalStructurePolicyR19.radiusForId("repurposed_structures:witch_hut_oak") == 24,
            "Better Witch Hut must be island-adapted");
        check(NeverOverworldExternalStructurePolicyR19.radiusForId("repurposed_structures:monument_jungle") == 96,
            "Better Monument jungle variant must be island-adapted");

        check(NeverOverworldExternalStructurePolicyR19.radiusForId("explorify:ruins") == 48,
            "Explorify jungle ruins must be island-adapted despite OCEAN_FLOOR_WG projection");
        check(NeverOverworldExternalStructurePolicyR19.radiusForId("nova_structures:stray_outlook") == 72,
            "D&T snowy stray outlook must be island-adapted");
        check(NeverOverworldExternalStructurePolicyR19.radiusForId("nova_structures:witch_villa") == 72,
            "D&T swamp witch villa must be island-adapted");
        check(NeverOverworldExternalStructurePolicyR19.radiusForId("structory_towers:ocean_pillar") == 0,
            "Structory ocean pillar must preserve original placement");
        check(NeverOverworldExternalStructurePolicyR19.radiusForId("nova_structures:catacomb") == 0,
            "underground catacomb must preserve original placement");
        check(NeverOverworldExternalStructurePolicyR19.radiusForId("nova_structures:conduit_ruin") == 0,
            "ocean conduit ruin must preserve original placement");
        check(NeverOverworldExternalStructurePolicyR19.radiusForId("minecraft:village_plains") == 0,
            "R19 must not replace vanilla NeverOverworld structure policy");

        check(NeverOverworldExternalStructurePolicyR19.isIslandSurfaceId("explorify:farmstead"),
            "surface farmstead classified");
        check(NeverOverworldExternalStructurePolicyR19.isIslandSurfaceId("explorify:ruins"),
            "jungle ruins classified as island surface");
        check(!NeverOverworldExternalStructurePolicyR19.isIslandSurfaceId("nova_structures:conduit_ruin"),
            "ocean conduit ruin not classified as island surface");

        out.println("PASS ExternalStructurePolicyR19Smoke checks=" + checks);
    }
}
