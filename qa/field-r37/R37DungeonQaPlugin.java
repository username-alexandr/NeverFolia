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
 private boolean denyMount,denySpawn;
 private final List<Entity> observedEntities=new ArrayList<>();
 private void check(boolean ok,String label){if(!ok)throw new AssertionError(label);checks.add(label);}
 @Override public void onEnable(){Bukkit.getPluginManager().registerEvents(this,this);}
 @EventHandler public void loaded(ServerLoadEvent ignored){
  var world=Bukkit.getWorlds().stream().filter(w->w.getEnvironment()==org.bukkit.World.Environment.NORMAL).findFirst().orElseThrow();
  testLevel=((CraftWorld)world).getHandle();
  // Force-loaded chunk state is global on Folia; entity creation stays local.
  Bukkit.getGlobalRegionScheduler().execute(this,()->{
   try {
    world.setChunkForceLoaded(0,0,true);
    world.getChunkAtAsync(0,0,true).whenComplete((chunk,error)->{
     if(error!=null){report(error);return;}
     Bukkit.getRegionScheduler().runDelayed(this,world,0,0,task->start(testLevel),20);
    });
   } catch(Throwable error){report(error);}
  });
 }
 @EventHandler public void spawned(CreatureSpawnEvent event){
  var e=((org.bukkit.craftbukkit.entity.CraftEntity)event.getEntity()).getHandle();
  if(!ca.spottedleaf.moonrise.common.util.TickThread.isTickThreadFor(e))return;
  if(e.level()!=testLevel||e.getY()<395||e.getY()>405||e.getX()<2||e.getX()>14||e.getZ()<2||e.getZ()>14)return;
  if(denySpawn && event.getEntityType()==org.bukkit.entity.EntityType.ZOMBIE_NAUTILUS)event.setCancelled(true);
  // Freeze only entities inside the isolated test fixture, regardless of the
  // Bukkit spawn-reason adapter. Keep their original equipment and tags.
  observedEntities.add(e);
  observedSpawns.add(BuiltInRegistries.ENTITY_TYPE.getKey(e.getType())+" tags="+e.entityTags()+" reason="+event.getSpawnReason());
  e.setNoGravity(true);if(e instanceof Mob m)m.setNoAi(true);
 }
 @EventHandler public void mounting(org.bukkit.event.entity.EntityMountEvent event){
  if(denyMount && event.getEntityType()==org.bukkit.entity.EntityType.DROWNED)event.setCancelled(true);
 }
 private Entity spawn(ServerLevel level,String id){
  var type=BuiltInRegistries.ENTITY_TYPE.getOptional(Identifier.fromNamespaceAndPath("minecraft",id)).orElseThrow();
  Entity e=type.create(level,EntitySpawnReason.COMMAND);if(e==null)throw new AssertionError("create "+id);
  e.setPos(8,400,8);e.setNoGravity(true);if(e instanceof Mob m)m.setNoAi(true);
  if(!level.addFreshEntity(e))throw new AssertionError("spawn "+id);return e;
 }
 private CommandSourceStack source(ServerLevel level,Entity e){
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
  try{
   check(ca.spottedleaf.moonrise.common.util.TickThread.isTickThreadFor(level,0,0),"actual owning region thread");
   for(String name:new String[]{"data","tag","scoreboard","function","item","loot"})
    check(level.getServer().getCommands().getDispatcher().getRoot().getChild(name)==null,"generic command remains disabled: "+name);
   var executor=spawn(level,"armor_stand");
   for(String name:new String[]{"spawn_cave_spider_minion","spawn_guardian_minion","spawn_spider_minion"})function(level,executor,name);
   function(level,spawn(level,"armor_stand"),"jockey/spawn_zautilus_jockey");
   testAtomicMount(level);
   testWaterPolicy();
   var living=(LivingEntity)spawn(level,"witch");
   NeverNetherDntCommands.run(source(level,living),"regenerate");
   var effect=living.getEffect(MobEffects.REGENERATION);
   check(effect!=null&&effect.getDuration()==1&&effect.getAmplifier()==6,"native one-tick regeneration contract");
   for(String name:new String[]{"ghast_boss_fireball_possess","ghast_boss_summon_child","ghasted_fireball_1","ghasted_fireball_2","ghasted_fireball_3"})
    check(level.getServer().getFunctions().get(Identifier.fromNamespaceAndPath("nova_structures",name)).isPresent(),"restored compiled function: "+name);
   Bukkit.getRegionScheduler().runDelayed(this,level.getWorld(),0,0,task->finishWithGlobalCheck(level),20);
  }catch(Throwable e){report(e);}
 }
 private void testAtomicMount(ServerLevel level) throws Exception {
  var unrelated=spawn(level,"zombie_nautilus");
  var first=(LivingEntity)spawn(level,"drowned");var second=(LivingEntity)spawn(level,"drowned");
  first.setItemSlot(EquipmentSlot.SADDLE,new net.minecraft.world.item.ItemStack(net.minecraft.world.item.Items.SADDLE));
  second.setItemSlot(EquipmentSlot.SADDLE,new net.minecraft.world.item.ItemStack(net.minecraft.world.item.Items.SADDLE));
  function(level,first,"jockey/make_drowned_into_jockey");
  function(level,second,"jockey/make_drowned_into_jockey");
  check(first.isPassenger()&&second.isPassenger(),"actual datapack function mounted both drowned");
  check(first.getVehicle()!=second.getVehicle()&&first.getVehicle()!=unrelated&&second.getVehicle()!=unrelated,"two colocated drowned each use their exact new mount");
  check(first.getItemBySlot(EquipmentSlot.SADDLE).isEmpty()&&second.getItemBySlot(EquipmentSlot.SADDLE).isEmpty(),"controllers consumed only after successful attachment");
  var vehicle=first.getVehicle();
  check(NeverNetherDntCommands.run(source(level,first),"drowned_mount")==0&&first.getVehicle()==vehicle,"repeat invocation leaves existing mount unchanged");
  var cancelled=(LivingEntity)spawn(level,"drowned");
  cancelled.setItemSlot(EquipmentSlot.SADDLE,new net.minecraft.world.item.ItemStack(net.minecraft.world.item.Items.SADDLE));
  int before=liveMounts(level);
  denySpawn=true;
  try{check(NeverNetherDntCommands.run(source(level,cancelled),"drowned_mount")==0,"spawn cancellation reported as no-op");}finally{denySpawn=false;}
  check(!cancelled.isPassenger()&&!cancelled.getItemBySlot(EquipmentSlot.SADDLE).isEmpty()&&liveMounts(level)==before,"spawn cancellation preserves controller and creates no orphan");
  denyMount=true;
  try{check(NeverNetherDntCommands.run(source(level,cancelled),"drowned_mount")==0,"mount cancellation reported as no-op");}finally{denyMount=false;}
  check(!cancelled.isPassenger()&&!cancelled.getItemBySlot(EquipmentSlot.SADDLE).isEmpty()&&liveMounts(level)==before,"mount cancellation removes only newly created mount and preserves controller");
  boolean rejected=false;
  try{NeverNetherDntCommands.run(source(level,unrelated),"drowned_mount");}catch(com.mojang.brigadier.exceptions.CommandSyntaxException expected){rejected=true;}
  check(rejected,"wrong entity type rejected without a world scan");
 }
 private int liveMounts(ServerLevel level){
  return level.getEntitiesOfClass(Mob.class,new AABB(2,395,2,14,405,14),e->!e.isRemoved()&&BuiltInRegistries.ENTITY_TYPE.getKey(e.getType()).toString().equals("minecraft:zombie_nautilus")).size();
 }
 private void testWaterPolicy(){
  for(int floor:new int[]{23,63,96,127,128,173}){
   check(!net.minecraft.world.level.chunk.NeverOverworldWaterPolicyR38.allowsNewWater(floor,floor,true),"cleanup cannot create source at occupied floor "+floor);
   check(!net.minecraft.world.level.chunk.NeverOverworldWaterPolicyR38.allowsNewWater(floor-1,floor,true),"cleanup cannot create source below floor "+floor);
   check(!net.minecraft.world.level.chunk.NeverOverworldWaterPolicyR38.allowsNewWater(128,floor,false),"no water contact means no source "+floor);
   check(net.minecraft.world.level.chunk.NeverOverworldWaterPolicyR38.allowsNewWater(floor+1,floor,true)==(floor<128),"open column above floor contract "+floor);
  }
  var flow=net.minecraft.world.level.block.Blocks.WATER.defaultBlockState().setValue(net.minecraft.world.level.block.LiquidBlock.LEVEL,5);
  var result=net.minecraft.world.level.chunk.NeverOverworldWaterPolicyR38.afterPlantRemoval(null,net.minecraft.core.BlockPos.ZERO,flow,true);
  check(result.getFluidState()==flow.getFluidState(),"cleanup preserves exact flowing-water state");
 }
 private void finishWithGlobalCheck(ServerLevel level){
  Bukkit.getGlobalRegionScheduler().execute(this,()->{
   try {
    boolean forced=level.getWorld().isChunkForceLoaded(0,0);
    Bukkit.getRegionScheduler().execute(this,level.getWorld(),0,0,()->finish(level,forced));
   } catch(Throwable error){report(error);}
  });
 }
 private void finish(ServerLevel level,boolean forced){
  try{
   check(forced,"fixture force-loaded state verified on global region");
   for(Entity entity:observedEntities){
    if(!ca.spottedleaf.moonrise.common.util.TickThread.isTickThreadFor(entity)){
     functionResults.add("entity migrated: "+entity.getUUID());continue;
    }
    functionResults.add("lifecycle="+BuiltInRegistries.ENTITY_TYPE.getKey(entity.getType())+" removed="+entity.isRemoved()+" reason="+entity.getRemovalReason()+" pos="+entity.position());
   }
   var mobs=level.getEntitiesOfClass(Mob.class,new AABB(2,395,2,14,405,14),e->true);
   functionResults.add("live query="+mobs.stream().map(e->BuiltInRegistries.ENTITY_TYPE.getKey(e.getType())+" "+e.entityTags()).toList());
   for(String tag:new String[]{"dnt_cave_spider_minion","dnt_guardian_minion","dnt_spider_minion"})
    check(mobs.stream().anyMatch(e->e.entityTags().contains(tag)),"function really spawned "+tag);
   check(mobs.stream().anyMatch(e->BuiltInRegistries.ENTITY_TYPE.getKey(e.getType()).toString().equals("minecraft:zombie_nautilus")),"jockey function really spawned zombie_nautilus");
   report(null);
  }catch(Throwable e){report(e);}
 }
 private synchronized void report(Throwable error){
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
  if(testLevel!=null){
   Bukkit.getGlobalRegionScheduler().execute(this,()->testLevel.getWorld().setChunkForceLoaded(0,0,false));
  }
  getLogger().info("R37 DUNGEON QA "+(error==null?"PASS":"FAIL")+" checks="+checks.size());
 }
}
