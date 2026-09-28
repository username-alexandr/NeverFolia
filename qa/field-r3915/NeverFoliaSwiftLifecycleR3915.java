package net.minecraft.world.item.enchantment;

import ca.spottedleaf.moonrise.common.util.TickThread;
import net.minecraft.core.registries.Registries;
import net.minecraft.resources.Identifier;
import net.minecraft.resources.ResourceKey;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.EquipmentSlot;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.entity.animal.happyghast.HappyGhast;
import net.minecraft.world.entity.ai.attributes.Attributes;

/** Reconciles only the two reserved Swift Soar modifiers on entity-owned ticks.
 * No global selectors, neighbouring-region access, saved UUID map or per-entity
 * background task. This complements the unchanged source functions: a dismounted
 * rider is no longer a passenger and cannot be cleaned by those functions.
 */
public final class NeverFoliaSwiftLifecycleR3915 {
    public static final String REVISION="R3915-swift-owned-lifecycle-v1";
    private static final Identifier FOV=id("boost_player_fov");
    private static final Identifier FLIGHT=id("sprint_flight_speed");
    private static final ResourceKey<Enchantment> SWIFT=ResourceKey.create(Registries.ENCHANTMENT,id("swift_soar"));
    private NeverFoliaSwiftLifecycleR3915(){}
    private static Identifier id(String p){return Identifier.fromNamespaceAndPath("nova_structures",p);}
    private static boolean hasSwift(HappyGhast mount){
        var entry=mount.level().registryAccess().lookupOrThrow(Registries.ENCHANTMENT).get(SWIFT);
        return entry.isPresent()&&EnchantmentHelper.getItemEnchantmentLevel(entry.get(),mount.getItemBySlot(EquipmentSlot.BODY))>0;
    }
    public static void tick(LivingEntity entity){
        if(!(entity instanceof ServerPlayer)&&!(entity instanceof HappyGhast))return;
        TickThread.ensureTickThread(entity,"Swift Soar lifecycle must run on the entity-owning region");
        if(entity instanceof ServerPlayer player){
            var speed=player.getAttribute(Attributes.MOVEMENT_SPEED);
            if(speed==null||speed.getModifier(FOV)==null)return;
            Entity vehicle=player.getVehicle();
            // Never inspect a mutable entity owned by another region. During a
            // transition leave reconciliation to the next owned tick.
            if(vehicle!=null&&!TickThread.isTickThreadFor(vehicle))return;
            boolean active=player.isAlive()&&vehicle instanceof HappyGhast mount&&mount.isAlive()
                &&hasSwift(mount)&&mount.entityTags().contains("sprinting")&&mount.hasPassenger(player);
            if(!active)speed.removeModifier(FOV);
            return;
        }
        HappyGhast mount=(HappyGhast)entity;
        var flight=mount.getAttribute(Attributes.FLYING_SPEED);
        if((flight==null||flight.getModifier(FLIGHT)==null)&&!mount.entityTags().contains("sprinting"))return;
        boolean rider=false;
        for(Entity passenger:mount.getPassengers())if(passenger instanceof ServerPlayer){rider=true;break;}
        if(!mount.isAlive()||!rider||!hasSwift(mount)){
            if(flight!=null)flight.removeModifier(FLIGHT);
            mount.entityTags().remove("sprinting");
        }
    }
}
