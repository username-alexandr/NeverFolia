package net.minecraft.server.commands;

import ca.spottedleaf.moonrise.common.util.TickThread;
import com.mojang.brigadier.CommandDispatcher;
import com.mojang.brigadier.exceptions.CommandSyntaxException;
import com.mojang.brigadier.exceptions.SimpleCommandExceptionType;
import java.util.Comparator;
import java.util.List;
import net.minecraft.commands.Commands;
import net.minecraft.commands.CommandSourceStack;
import net.minecraft.commands.arguments.NbtPathArgument.NbtPath;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.nbt.TagParser;
import net.minecraft.network.chat.Component;
import net.minecraft.resources.Identifier;
import net.minecraft.server.commands.data.EntityDataAccessor;
import net.minecraft.world.effect.MobEffectInstance;
import net.minecraft.world.effect.MobEffects;
import net.minecraft.world.entity.Entity;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.world.entity.EntitySpawnReason;
import net.minecraft.world.entity.EquipmentSlot;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.entity.monster.Ghast;
import net.minecraft.world.entity.npc.villager.AbstractVillager;
import net.minecraft.world.entity.projectile.Projectile;
import net.minecraft.world.entity.projectile.hurtingprojectile.LargeFireball;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.phys.AABB;

/** A finite compatibility surface, NOT Folia's disabled generic commands.
 * Every action requires an entity on its owning tick thread. No arbitrary NBT
 * path, selector, scoreboard, function identifier or raw command is accepted.
 */
public final class NeverNetherDntCommands {
    private NeverNetherDntCommands() { }
    private static final SimpleCommandExceptionType UNSAFE = new SimpleCommandExceptionType(
        Component.literal("NeverNether D&T action requires a compatible entity on its owning region thread"));
    private static final SimpleCommandExceptionType MISSING = new SimpleCommandExceptionType(
        Component.literal("NeverNether D&T action could not resolve its exact entity data or function"));
    public static final List<String> ACTIONS = List.of(
        "clear_fireball_owner", "minion_increment", "fireball_1", "fireball_2", "fireball_3", "regenerate",
        "clear_saddle", "sprint_on", "sprint_off", "offer_prepend", "offer_buy", "offer_sell",
        "trade_2_added", "trade_3_added", "trade_4_added", "trade_5_added",
        "call_trade_2", "call_trade_3", "call_trade_4", "call_trade_5",
        "loot_emeralds", "loot_chart_2", "loot_chart_3", "loot_chart_4", "loot_chart_5");
    private static final String COUNTER_PREFIX = "neverfolia.dnt_minions_";
    public static final String LIMIT_TAG = "neverfolia.dnt_minions_limit";
    public static void register(CommandDispatcher<CommandSourceStack> dispatcher) {
        var root = Commands.literal("neverfolia:dnt").requires(Commands.hasPermission(Commands.LEVEL_GAMEMASTERS));
        for (String action : ACTIONS) root.then(Commands.literal(action).executes(c -> run(c.getSource(), action)));
        dispatcher.register(root);
    }
    public static Entity ownedEntity(CommandSourceStack source) throws CommandSyntaxException {
        Entity entity = source.getEntityOrException();
        // Do not inspect any mutable entity state before verifying ownership.
        if (!TickThread.isTickThreadFor(entity)) throw UNSAFE.create();
        if (entity.isRemoved() || entity.level() != source.getLevel()) throw UNSAFE.create();
        return entity;
    }
    public static int run(CommandSourceStack source, String action) throws CommandSyntaxException {
        if (!ACTIONS.contains(action)) throw MISSING.create();
        Entity self = ownedEntity(source);
        return switch (action) {
            case "sprint_on" -> self.addTag("sprinting") ? 1 : 0;
            case "sprint_off" -> self.removeTag("sprinting") ? 1 : 0;
            case "trade_2_added", "trade_3_added", "trade_4_added", "trade_5_added" -> {
                requireTrader(self); yield self.addTag("trade" + action.charAt(6) + "added") ? 1 : 0;
            }
            case "clear_saddle" -> {
                if (!(self instanceof LivingEntity living)) throw UNSAFE.create();
                living.setItemSlot(EquipmentSlot.SADDLE, ItemStack.EMPTY); yield 1;
            }
            case "regenerate" -> {
                if (!(self instanceof LivingEntity living)) throw UNSAFE.create();
                // Original source requested duration=1 tick, not one second.
                yield living.addEffect(new MobEffectInstance(MobEffects.REGENERATION, 1, 6, false, false)) ? 1 : 0;
            }
            case "clear_fireball_owner" -> clearOwner(source, self);
            case "fireball_1", "fireball_2", "fireball_3" -> convertProjectile(source, self, action.charAt(9) - '0');
            case "minion_increment" -> incrementMinions(self);
            case "offer_prepend", "offer_buy", "offer_sell" -> modifyOffer(self, action);
            case "loot_emeralds", "loot_chart_2", "loot_chart_3", "loot_chart_4", "loot_chart_5" -> fillHand(source, self, action);
            case "call_trade_2", "call_trade_3", "call_trade_4", "call_trade_5" -> {
                requireTrader(self);
                var id = Identifier.fromNamespaceAndPath("nova_structures", "quest/add_trade_lv" + action.charAt(11));
                var manager = source.getServer().getFunctions();
                var function = manager.get(id).orElseThrow(MISSING::create);
                // The function manager joins the current command execution context;
                // the target is a fixed known function, never an arbitrary user id.
                manager.execute(function, source.withSuppressedOutput()); yield 1;
            }
            default -> throw MISSING.create();
        };
    }
    private static void requireTrader(Entity entity) throws CommandSyntaxException {
        if (!(entity instanceof AbstractVillager)) throw UNSAFE.create();
    }
    private static int incrementMinions(Entity self) throws CommandSyntaxException {
        if (!(self instanceof Ghast) || !self.entityTags().contains("dnt_ghast_boss")) throw UNSAFE.create();
        int count = 0;
        for (int n = 1; n <= 7; n++) if (self.entityTags().contains(COUNTER_PREFIX + n)) count = n;
        int next = Math.min(7, count + 1);
        // Add before removing the old marker so a full vanilla tag set cannot
        // lose a previously valid counter. No shared scoreboard is touched.
        if (next != count && !self.addTag(COUNTER_PREFIX + next)) throw MISSING.create();
        if (next == 7 && !self.entityTags().contains(LIMIT_TAG) && !self.addTag(LIMIT_TAG)) throw MISSING.create();
        for (int n = 1; n <= 7; n++) if (n != next) self.removeTag(COUNTER_PREFIX + n);
        return next;
    }
    private static int clearOwner(CommandSourceStack source, Entity self) throws CommandSyntaxException {
        if (!(self instanceof Ghast)) throw UNSAFE.create();
        var pos = source.getPosition();
        var box = new AABB(pos.x - 45, pos.y - 45, pos.z - 45, pos.x + 45, pos.y + 45, pos.z + 45);
        // Never perform a world-wide/unowned entity scan. Near a region boundary
        // this operation is conservatively rejected; it is not rescheduled with
        // stale entity references. In-world edge behavior remains a QA gate.
        if (!TickThread.isTickThreadFor(source.getLevel(), box)) throw UNSAFE.create();
        var candidates = source.getLevel().getEntitiesOfClass(LargeFireball.class, box,
            e -> TickThread.isTickThreadFor(e) && e.distanceToSqr(pos) <= 45 * 45);
        var nearest = candidates.stream().min(Comparator.comparingDouble(e -> e.distanceToSqr(pos)));
        if (nearest.isEmpty()) return 0;
        nearest.get().setOwner((Entity) null); return 1;
    }
    private static int convertProjectile(CommandSourceStack source, Entity self, int power) throws CommandSyntaxException {
        if (!(self instanceof Projectile previous) || power < 1 || power > 3) throw UNSAFE.create();
        if (!TickThread.isTickThreadFor(source.getLevel(), source.getPosition())) throw UNSAFE.create();
        var type = BuiltInRegistries.ENTITY_TYPE.getOptional(Identifier.fromNamespaceAndPath("minecraft", "fireball")).orElseThrow(MISSING::create);
        if (!(type.create(source.getLevel(), EntitySpawnReason.COMMAND) instanceof LargeFireball next)) throw MISSING.create();
        next.setPos(source.getPosition());
        next.explosionPower = power;
        next.addTag("dnt_ghasted_fireball");
        next.setDeltaMovement(previous.getDeltaMovement());
        next.owner = previous.owner; // immutable entity reference; no owner lookup
        if (!source.getLevel().addFreshEntity(next)) return 0;
        // No @n query that might accidentally select a pre-existing fireball.
        self.discard(org.bukkit.event.entity.EntityRemoveEvent.Cause.TRANSFORMATION);
        return 1;
    }
    private static int fillHand(CommandSourceStack source, Entity self, String action) throws CommandSyntaxException {
        requireTrader(self);
        String tableName = switch (action) {
            case "loot_emeralds" -> "villager_emerald_counts";
            case "loot_chart_2" -> "tavern_quest";
            case "loot_chart_3" -> "tavern_quest_uncommon";
            case "loot_chart_4" -> "tavern_quest_rare";
            case "loot_chart_5" -> "tavern_quest_epic";
            default -> throw MISSING.create();
        };
        var key = net.minecraft.resources.ResourceKey.create(net.minecraft.core.registries.Registries.LOOT_TABLE,
            Identifier.fromNamespaceAndPath("nova_structures", "villagers/" + tableName));
        var registries = source.getServer().reloadableRegistries();
        var table = registries.lookup().lookupOrThrow(net.minecraft.core.registries.Registries.LOOT_TABLE).get(key).orElseThrow(MISSING::create).value();
        var params = new net.minecraft.world.level.storage.loot.LootParams.Builder(source.getLevel())
            .withParameter(net.minecraft.world.level.storage.loot.parameters.LootContextParams.ORIGIN, source.getPosition())
            .withParameter(net.minecraft.world.level.storage.loot.parameters.LootContextParams.THIS_ENTITY, self)
            .create(net.minecraft.world.level.storage.loot.parameters.LootContextParamSets.COMMAND);
        // Only five pinned tables and their validated component/count-only closure.
        // Use an invocation-local random source; no mutable world random sequence.
        var generated = table.getRandomItems(params, net.minecraft.util.RandomSource.create());
        if (generated.size() != 1) throw MISSING.create();
        ((LivingEntity) self).setItemSlot(EquipmentSlot.MAINHAND, generated.getFirst());
        return 1;
    }
    private static int modifyOffer(Entity self, String action) throws CommandSyntaxException {
        requireTrader(self);
        var accessor = new EntityDataAccessor(self);
        CompoundTag data = accessor.getData();
        if (action.equals("offer_prepend")) {
            var offer = TagParser.parseCompoundFully("{buyB:{id:\"minecraft:compass\",count:1},buy:{id:\"minecraft:emerald\",count:14},sell:{id:\"minecraft:paper\",count:1},maxUses:1}");
            NbtPath.of("Offers.Recipes").insert(0, data, List.of(offer));
        } else {
            var from = NbtPath.of("equipment.mainhand").get(data);
            var into = NbtPath.of("Offers.Recipes[0]." + (action.equals("offer_buy") ? "buy" : "sell")).get(data);
            if (from.size() != 1 || into.size() != 1 || !(from.getFirst() instanceof CompoundTag source) || !(into.getFirst() instanceof CompoundTag target)) throw MISSING.create();
            target.merge(source.copy());
        }
        // Identical vanilla data-accessor semantics, but only these three fixed
        // offer mutations, only a trader, and only on its owning tick thread.
        accessor.setData(data); return 1;
    }
}
