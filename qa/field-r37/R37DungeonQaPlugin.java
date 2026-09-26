import java.nio.file.Files;
import java.util.ArrayList;
import java.util.List;
import org.bukkit.Bukkit;
import org.bukkit.craftbukkit.CraftWorld;
import org.bukkit.event.EventHandler;
import org.bukkit.event.Listener;
import org.bukkit.event.server.ServerLoadEvent;
import org.bukkit.event.entity.CreatureSpawnEvent;
import org.bukkit.plugin.java.JavaPlugin;
import net.minecraft.commands.CommandSourceStack;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.resources.Identifier;
import net.minecraft.server.commands.NeverNetherDntCommands;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.permissions.PermissionSet;
import net.minecraft.world.entity.*;
import net.minecraft.world.effect.MobEffects;
import net.minecraft.world.phys.AABB;

/** Isolated QA only. Never bundled as a production plugin. */
public final class R37DungeonQaPlugin extends JavaPlugin implements Listener {
 private final List<String> checks=new ArrayList<>();
 private volatile ServerLevel testLevel;
 private final List<String> observedSpawns=new ArrayList<>();
 private final List<String> functionResults=new ArrayList<>();
 private boolean finished;
 private void check(boolean ok,String label){if(!ok)throw new AssertionError(label);checks.add(label);}
 @Override public void onEnable(){Bukkit.getPluginManager().registerEvents(this,this);}
 @EventHandler public void loaded(ServerLoadEvent ignored){
  var world=Bukkit.getWorlds().stream().filter(w->w.getEnvironment()==org.bukkit.World.Environment.NORMAL).findFirst().orElseThrow();
  world.getChunkAtAsync(0,0,true).thenAccept(chunk->Bukkit.getRegionScheduler().execute(this,world,0,0,()->start(((CraftWorld)world).getHandle())));
 }
 @EventHandler public void spawned(CreatureSpawnEvent event){
  var e=((org.bukkit.craftbukkit.entity.CraftEntity)event.getEntity()).getHandle();
  if(!ca.spottedleaf.moonrise.common.util.TickThread.isTickThreadFor(e))return;
  if(e.level()!=testLevel||e.getY()<395||e.getY()>405||e.getX()<2||e.getX()>14||e.getZ()<2||e.getZ()>14)return;
  // Freeze only entities inside the isolated test fixture, regardless of the
  // Bukkit spawn-reason adapter. Keep their original equipment and tags.
  observedSpawns.add(BuiltInRegistries.ENTITY_TYPE.getKey(e.getType())+" tags="+e.entityTags()+" reason="+event.getSpawnReason());
  e.setNoGravity(true);if(e instanceof Mob m)m.setNoAi(true);
 }
 private Entity spawn(ServerLevel level,String id){
  var type=BuiltInRegistries.ENTITY_TYPE.getOptional(Identifier.fromNamespaceAndPath("minecraft",id)).orElseThrow();
  Entity e=type.create(level,EntitySpawnReason.COMMAND);if(e==null)throw new AssertionError("create "+id);
  e.setPos(8,400,8);e.setNoGravity(true);if(e instanceof Mob m)m.setNoAi(true);
  if(!level.addFreshEntity(e))throw new AssertionError("spawn "+id);return e;
 }
 private CommandSourceStack source(ServerLevel level,Entity e){
  // Follow the actual enchantment RunFunction source path. Keep failures visible.
  return level.getServer().createCommandSourceStack().withEntity(e).withLevel(level)
   .withPosition(e.position()).withRotation(e.getRotationVector())
   .withPermission(PermissionSet.ALL_PERMISSIONS);
 }
 private void function(ServerLevel level,Entity e,String name){
  var manager=level.getServer().getFunctions();
  var id=Identifier.fromNamespaceAndPath("nova_structures",name);
  var f=manager.get(id).orElseThrow(()->new AssertionError("function not loaded: "+id));
  manager.execute(f,source(level,e).withCallback((success,value)->functionResults.add(name+": success="+success+" value="+value)));
 }
 private void start(ServerLevel level){
  testLevel=level;
  try{
   check(ca.spottedleaf.moonrise.common.util.TickThread.isTickThreadFor(level,0,0),"actual owning region thread");
   for(String name:new String[]{"data","tag","scoreboard","function","item","loot"})
    check(level.getServer().getCommands().getDispatcher().getRoot().getChild(name)==null,"generic command remains disabled: "+name);
   var executor=spawn(level,"armor_stand");
   for(String name:new String[]{"spawn_cave_spider_minion","spawn_guardian_minion","spawn_spider_minion"})function(level,executor,name);
   function(level,spawn(level,"armor_stand"),"jockey/spawn_zautilus_jockey");
   var living=(LivingEntity)spawn(level,"witch");
   NeverNetherDntCommands.run(source(level,living),"regenerate");
   var effect=living.getEffect(MobEffects.REGENERATION);
   check(effect!=null&&effect.getDuration()==1&&effect.getAmplifier()==6,"native one-tick regeneration contract");
   for(String name:new String[]{"ghast_boss_fireball_possess","ghast_boss_summon_child","ghasted_fireball_1","ghasted_fireball_2","ghasted_fireball_3"})
    check(level.getServer().getFunctions().get(Identifier.fromNamespaceAndPath("nova_structures",name)).isPresent(),"restored compiled function: "+name);
   Bukkit.getRegionScheduler().runDelayed(this,level.getWorld(),0,0,task->finish(level),20);
  }catch(Throwable e){report(e);}
 }
 private void finish(ServerLevel level){
  try{
   var mobs=level.getEntitiesOfClass(Mob.class,new AABB(2,395,2,14,405,14),e->true);
   functionResults.add("live query="+mobs.stream().map(e->BuiltInRegistries.ENTITY_TYPE.getKey(e.getType())+" "+e.entityTags()).toList());
   for(String tag:new String[]{"dnt_cave_spider_minion","dnt_guardian_minion","dnt_spider_minion"})
    check(mobs.stream().anyMatch(e->e.entityTags().contains(tag)),"function really spawned "+tag);
   check(mobs.stream().anyMatch(e->BuiltInRegistries.ENTITY_TYPE.getKey(e.getType()).toString().equals("minecraft:zombie_nautilus")),"jockey function really spawned zombie_nautilus");
   report(null);
  }catch(Throwable e){report(e);}
 }
 private void report(Throwable error){
  if(finished)return;finished=true;
  if(error!=null)error.printStackTrace();
  try{
   getDataFolder().mkdirs();var result=new com.google.gson.JsonObject();result.addProperty("pass",error==null);
   result.addProperty("scope","owning-region controller spawn test; not natural trial player activation or all dungeon bosses");
   result.add("observed_spawns",new com.google.gson.Gson().toJsonTree(observedSpawns));
   result.add("function_results",new com.google.gson.Gson().toJsonTree(functionResults));
   result.add("checks",new com.google.gson.Gson().toJsonTree(checks));if(error!=null)result.addProperty("error",error.toString());
   Files.writeString(getDataFolder().toPath().resolve("result.json"),new com.google.gson.GsonBuilder().setPrettyPrinting().create().toJson(result));
  }catch(Exception e){e.printStackTrace();}
  getLogger().info("R37 DUNGEON QA "+(error==null?"PASS":"FAIL")+" checks="+checks.size());
 }
}
