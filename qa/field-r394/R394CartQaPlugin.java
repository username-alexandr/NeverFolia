import java.nio.file.Files;
import java.util.ArrayList;
import java.util.List;
import org.bukkit.Bukkit;
import org.bukkit.craftbukkit.CraftWorld;
import org.bukkit.entity.Villager;
import org.bukkit.event.EventHandler;
import org.bukkit.event.Listener;
import org.bukkit.event.server.ServerLoadEvent;
import org.bukkit.plugin.java.JavaPlugin;
import net.minecraft.core.BlockPos;
import net.minecraft.core.registries.Registries;
import net.minecraft.resources.Identifier;
import net.minecraft.resources.ResourceKey;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.levelgen.structure.pools.JigsawPlacement;
import net.minecraft.world.phys.AABB;

/** Isolated CI ONLY. Never install on a player's existing world. */
public final class R394CartQaPlugin extends JavaPlugin implements Listener {
 private static final String[] BIOMES={"acacia","birch","cherry","desert","jungle","mangrove","oak","pale","snowy","spruce","swamp"};
 private static final String[] ROLES={"cartographer","cleric"};
 private final List<com.google.gson.JsonObject> checks=new ArrayList<>();
 private org.bukkit.World world;private ServerLevel level;private boolean finished;
 @Override public void onEnable(){Bukkit.getPluginManager().registerEvents(this,this);}
 @EventHandler public void loaded(ServerLoadEvent event){
  world=Bukkit.getWorlds().stream().filter(w->w.getEnvironment()==org.bukkit.World.Environment.NORMAL).findFirst().orElseThrow();level=((CraftWorld)world).getHandle();next(0);
 }
 private void require(boolean ok,String message){if(!ok)throw new AssertionError(message);}
 private void next(int index){
  if(finished)return;if(index==22){finish(null);return;}
  int cx=300+index*3;
  Bukkit.getGlobalRegionScheduler().execute(this,()->{
   try{world.setChunkForceLoaded(cx,300,true);world.getChunkAtAsync(cx,300,true).whenComplete((chunk,error)->{
    if(error!=null){finish(error);return;}
    Bukkit.getRegionScheduler().execute(this,world,cx,300,()->place(index,cx));
   });}catch(Throwable error){finish(error);}
  });
 }
 private void place(int index,int cx){
  String role=ROLES[index%2],biome=BIOMES[index/2];int x=cx*16+8,z=300*16+8;BlockPos pos=new BlockPos(x,400,z);
  try{
   require(ca.spottedleaf.moonrise.common.util.TickThread.isTickThreadFor(level,pos),"placement must own fixture region");
   var template=level.getStructureManager().get(Identifier.parse("nova_structures:tavern/tavern_event_trader_car_"+role+"_"+biome)).orElseThrow();
   require(template.getSize().getX()==1&&template.getSize().getY()==1&&template.getSize().getZ()==1,"real template manager must load router");
   BlockPos.MutableBlockPos block=new BlockPos.MutableBlockPos();
   for(int dx=-7;dx<=7;dx++)for(int dz=-7;dz<=7;dz++)for(int y=399;y<=408;y++)level.setBlock(block.set(x+dx,y,z+dz),(y==399?Blocks.STONE:Blocks.AIR).defaultBlockState(),3);
   var registry=level.registryAccess().lookupOrThrow(Registries.TEMPLATE_POOL);
   var pool=registry.getOrThrow(ResourceKey.create(Registries.TEMPLATE_POOL,Identifier.parse("neverfolia_qa:cart/"+role+"_"+biome)));
   require(JigsawPlacement.generateJigsaw(level,pool,Identifier.parse("minecraft:event/trader/"+role+"_"+biome),2,pos,false),"real jigsaw generation failed");
   Bukkit.getRegionScheduler().runDelayed(this,world,cx,300,task->{
    try{
     require(ca.spottedleaf.moonrise.common.util.TickThread.isTickThreadFor(level,pos),"observation must own fixture region");
     var entities=level.getEntitiesOfClass(net.minecraft.world.entity.npc.villager.Villager.class,new AABB(x-7,399,z-7,x+8,409,z+8),e->true);
     List<String> professions=new ArrayList<>();for(var entity:entities)professions.add(((Villager)entity.getBukkitEntity()).getProfession().name());
     require(professions.size()==1&&professions.get(0).equals(role.toUpperCase(java.util.Locale.ROOT)),"expected one "+role+", got "+professions);
     int jigsaws=0,placed=0;
     for(int dx=-6;dx<=6;dx++)for(int dz=-6;dz<=6;dz++)for(int y=400;y<=405;y++){
      var state=level.getBlockState(new BlockPos(x+dx,y,z+dz));if(state.is(Blocks.JIGSAW))jigsaws++;if(!state.isAir())placed++;
     }
     require(jigsaws==0,"unfinished jigsaws remain");require(placed>8,"cart geometry missing");
     var row=new com.google.gson.JsonObject();row.addProperty("role",role);row.addProperty("biome_router",biome);row.addProperty("real_jigsaw_placement",true);row.addProperty("villager_profession",professions.get(0));row.addProperty("remaining_jigsaws",jigsaws);row.addProperty("nonair_blocks",placed);row.addProperty("pass",true);checks.add(row);persist(null,false);
     getLogger().info("R394 CART "+index+" "+role+" "+biome+" PASS");
     Bukkit.getGlobalRegionScheduler().execute(this,()->world.setChunkForceLoaded(cx,300,false));next(index+1);
    }catch(Throwable error){finish(error);}
   },5);
  }catch(Throwable error){finish(error);}
 }
 private synchronized void persist(Throwable error,boolean complete){
  try{getDataFolder().mkdirs();var report=new com.google.gson.JsonObject();report.addProperty("pass",complete&&error==null&&checks.size()==22);report.addProperty("completed",checks.size());report.addProperty("scope","22 actual jigsaw assemblies using isolated single-router QA root pools, original profession child pools and original cart entities. Not random natural tavern selection, all biomes' terrain, or player trade interaction.");report.add("checks",new com.google.gson.Gson().toJsonTree(checks));if(error!=null)report.addProperty("error",error.toString());Files.writeString(getDataFolder().toPath().resolve("result.json"),new com.google.gson.GsonBuilder().setPrettyPrinting().create().toJson(report));}catch(Exception e){e.printStackTrace();}
 }
 private synchronized void finish(Throwable error){if(finished)return;finished=true;if(error!=null)error.printStackTrace();persist(error,true);getLogger().info("R394 CART QA "+(error==null?"PASS":"FAIL")+" checks="+checks.size());}
}
