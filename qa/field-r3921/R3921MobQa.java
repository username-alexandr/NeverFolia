import com.google.gson.*;
import java.nio.file.Files;
import java.util.*;
import org.bukkit.Bukkit;
import org.bukkit.craftbukkit.CraftWorld;
import org.bukkit.event.*;
import org.bukkit.event.server.ServerLoadEvent;
import org.bukkit.plugin.java.JavaPlugin;
import net.minecraft.commands.CommandSourceStack;
import net.minecraft.core.registries.*;
import net.minecraft.resources.*;
import net.minecraft.server.level.*;
import net.minecraft.server.permissions.PermissionSet;
import net.minecraft.world.entity.*;
import net.minecraft.world.entity.monster.zombie.Drowned;
import net.minecraft.world.item.*;
import net.minecraft.world.item.enchantment.EnchantmentHelper;
import net.minecraft.world.phys.AABB;

public final class R3921MobQa extends JavaPlugin implements Listener {
    private final JsonArray checks=new JsonArray(), cases=new JsonArray();
    private ServerLevel level; private org.bukkit.World world; private boolean finished;
    private static final AABB BOX=new AABB(1,396,1,15,406,15);
    private static Identifier id(String path){return Identifier.fromNamespaceAndPath("nova_structures",path);}
    private void check(boolean ok,String name){JsonObject o=new JsonObject();o.addProperty("name",name);o.addProperty("pass",ok);checks.add(o);if(!ok)throw new AssertionError(name);}
    @Override public void onEnable(){Bukkit.getPluginManager().registerEvents(this,this);}
    @EventHandler public void loaded(ServerLoadEvent ignored){
        try{
            world=Bukkit.getWorlds().stream().filter(w->w.getEnvironment()==org.bukkit.World.Environment.NORMAL).findFirst().orElseThrow();
            level=((CraftWorld)world).getHandle();
            Bukkit.getGlobalRegionScheduler().execute(this,()->{
                try{
                    world.setChunkForceLoaded(0,0,true);
                    world.getChunkAtAsync(0,0,true).whenComplete((chunk,error)->{
                        if(error!=null){finish(error);return;}
                        Bukkit.getRegionScheduler().runDelayed(this,world,0,0,t->runAll(),2);
                    });
                }catch(Throwable e){finish(e);}
            });
        }catch(Throwable e){finish(e);}
    }
    private String type(Entity e){return BuiltInRegistries.ENTITY_TYPE.getKey(e.getType()).toString();}
    private Entity create(String name,double x){
        var t=BuiltInRegistries.ENTITY_TYPE.getOptional(Identifier.fromNamespaceAndPath("minecraft",name)).orElseThrow();
        Entity e=t.create(level,EntitySpawnReason.COMMAND);if(e==null)throw new AssertionError("create "+name);
        e.setPos(x,400,8);e.setNoGravity(true);if(e instanceof Mob m)m.setNoAi(true);
        check(level.addFreshEntity(e),"add source "+name);return e;
    }
    private CommandSourceStack source(Entity e){
        return level.getServer().createCommandSourceStack().withEntity(e).withLevel(level).withPosition(e.position())
            .withRotation(e.getRotationVector()).withPermission(PermissionSet.ALL_PERMISSIONS);
    }
    private void function(Entity e,String name){
        var f=level.getServer().getFunctions().get(id(name)).orElseThrow(()->new AssertionError("function missing "+name));
        level.getServer().getFunctions().execute(f,source(e).withSuppressedOutput());
    }
    private void enchant(LivingEntity e,EquipmentSlot slot,String name){
        var holder=level.registryAccess().lookupOrThrow(Registries.ENCHANTMENT)
            .getOrThrow(ResourceKey.create(Registries.ENCHANTMENT,id(name)));
        ItemStack item=new ItemStack(Items.STICK);item.enchant(holder,1);e.setItemSlot(slot,item);
        check(!e.getItemBySlot(slot).isEmpty(),"controller equipped "+name);
    }
    private void collectPassengers(Entity root,List<String> out){
        for(Entity p:root.getPassengers()){out.add(type(p));collectPassengers(p,out);}
    }
    private List<Entity> entities(){return level.getEntitiesOfClass(Entity.class,BOX,e->true);}
    private Entity uniqueRoot(String expected){
        var found=entities().stream().filter(e->type(e).equals("minecraft:"+expected)&&!e.isPassenger()).toList();
        check(found.size()==1,"exact root "+expected);return found.getFirst();
    }
    private void discardTree(Entity e){for(Entity p:new ArrayList<>(e.getPassengers()))discardTree(p);e.discard();}
    private void clean(){for(Entity e:new ArrayList<>(entities()))if(!e.isRemoved())e.discard();}
    private void jockey(String enchant,String root,List<String> passengers){
        clean();var source=(LivingEntity)create("armor_stand",8);enchant(source,EquipmentSlot.HEAD,enchant);
        EnchantmentHelper.tickEffects(level,source);
        check(source.isRemoved(),"tick controller consumed "+enchant);
        Entity made=uniqueRoot(root);List<String> observed=new ArrayList<>();collectPassengers(made,observed);
        Collections.sort(observed);var want=new ArrayList<>(passengers);Collections.sort(want);
        check(observed.equals(want),"passenger graph "+enchant+" "+observed);
        JsonObject row=new JsonObject();row.addProperty("enchantment",enchant);row.addProperty("root",type(made));
        row.add("passengers",new Gson().toJsonTree(observed));cases.add(row);discardTree(made);
    }
    private void drowned(){
        clean();var e=(Drowned)create("drowned",8);enchant(e,EquipmentSlot.SADDLE,"jockey/make_drowned_into_jockey");
        EnchantmentHelper.tickEffects(level,e);
        check(!e.isRemoved(),"drowned controller keeps rider");check(e.isPassenger(),"drowned mounted by enchantment tick");
        check(type(e.getVehicle()).equals("minecraft:zombie_nautilus"),"drowned exact zombie_nautilus mount");
        check(e.getItemBySlot(EquipmentSlot.SADDLE).isEmpty(),"drowned controller consumed after mount");
        JsonObject row=new JsonObject();row.addProperty("enchantment","jockey/make_drowned_into_jockey");row.addProperty("root",type(e.getVehicle()));
        row.addProperty("rider",type(e));cases.add(row);discardTree(e.getVehicle());
    }
    private void minion(String function,String tag,String expected){
        clean();Entity src=create("armor_stand",8);function(src,function);
        var rows=entities().stream().filter(e->type(e).equals("minecraft:"+expected)&&e.entityTags().contains(tag)).toList();
        check(rows.size()==1,"function spawned "+tag);JsonObject row=new JsonObject();row.addProperty("function",function);
        row.addProperty("entity",type(rows.getFirst()));cases.add(row);
    }
    private void ghastChild(){
        clean();Entity src=create("ghast",8);src.addTag("dnt_ghast_boss");function(src,"ghast_boss_summon_child");
        var rows=entities().stream().filter(e->type(e).equals("minecraft:ghast")&&e.entityTags().contains("dnt_ghast_boss_child")).toList();
        check(rows.size()==1,"ghast boss child spawned");check(src.entityTags().stream().anyMatch(x->x.startsWith("neverfolia.dnt_minions_")),"ghast native minion counter advanced");
    }
    private void runAll(){
        try{
            check(ca.spottedleaf.moonrise.common.util.TickThread.isTickThreadFor(level,0,0),"owned region thread");
            for(String name:new String[]{"data","tag","scoreboard","function","item","loot"})
                check(level.getServer().getCommands().getDispatcher().getRoot().getChild(name)==null,"generic command disabled "+name);
            jockey("jockey/spawn_bogged_horseman","zombie_horse",List.of("minecraft:bogged"));
            jockey("jockey/spawn_camel_husk_jockey","camel_husk",List.of("minecraft:husk","minecraft:parched"));
            jockey("jockey/spawn_chicken_jockey","chicken",List.of("minecraft:zombie"));
            jockey("jockey/spawn_hoglin_jockey","hoglin",List.of("minecraft:piglin"));
            jockey("jockey/spawn_ravager_jockey","ravager",List.of("minecraft:pillager"));
            jockey("jockey/spawn_skeleton_horseman","skeleton_horse",List.of("minecraft:skeleton"));
            jockey("jockey/spawn_stray_horseman","skeleton_horse",List.of("minecraft:stray"));
            jockey("jockey/spawn_zautilus_jockey","zombie_nautilus",List.of("minecraft:drowned"));
            jockey("jockey/spawn_zombie_horseman","zombie_horse",List.of("minecraft:zombie"));
            drowned();
            minion("spawn_cave_spider_minion","dnt_cave_spider_minion","cave_spider");
            minion("spawn_guardian_minion","dnt_guardian_minion","guardian");
            minion("spawn_spider_minion","dnt_spider_minion","spider");
            ghastChild();
            finish(null);
        }catch(Throwable e){finish(e);}
    }
    private synchronized void finish(Throwable error){
        if(finished)return;finished=true;
        JsonObject r=new JsonObject();r.addProperty("pass",error==null);r.addProperty("seed",level==null?0:level.getSeed());
        r.addProperty("scope","Nine jockey technical enchantments through real EnchantmentHelper tick effects, drowned native mount path, three minion functions and ghast-child spawn on one owned Folia region; startup/restart workflow repeats the suite.");
        r.add("checks",checks);r.add("cases",cases);if(error!=null){r.addProperty("error",error.toString());error.printStackTrace();}
        try{getDataFolder().mkdirs();Files.writeString(getDataFolder().toPath().resolve("result.json"),new GsonBuilder().setPrettyPrinting().create().toJson(r));}catch(Exception e){e.printStackTrace();}
        getLogger().info("R3921 MOB QA "+(error==null?"PASS":"FAIL"));
        Bukkit.getGlobalRegionScheduler().execute(this,()->{try{world.setChunkForceLoaded(0,0,false);}finally{Bukkit.shutdown();}});
    }
}
