import java.nio.file.Files;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import org.bukkit.Bukkit;
import org.bukkit.GameMode;
import org.bukkit.Location;
import org.bukkit.craftbukkit.CraftWorld;
import org.bukkit.event.EventHandler;
import org.bukkit.event.Listener;
import org.bukkit.event.server.ServerLoadEvent;
import org.bukkit.event.entity.CreatureSpawnEvent;
import org.bukkit.event.player.PlayerJoinEvent;
import org.bukkit.plugin.java.JavaPlugin;
import net.minecraft.core.BlockPos;
import net.minecraft.core.registries.Registries;
import net.minecraft.resources.Identifier;
import net.minecraft.resources.ResourceKey;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.entity.TrialSpawnerBlockEntity;
import net.minecraft.world.level.block.entity.trialspawner.TrialSpawner;
import net.minecraft.world.entity.Mob;
import net.minecraft.world.phys.AABB;

/** Isolated loopback CI fixture. Uses the normal survival-player detector. */
public final class R38TrialQaPlugin extends JavaPlugin implements Listener {
 private ServerLevel level;
 private org.bukkit.World world;
 private int phase=-1,ticks;
 private boolean finished;
 private UUID playerId;
 private final List<String> checks=new ArrayList<>(),spawns=new ArrayList<>();
 private final List<String> states=new ArrayList<>();
 private static final BlockPos POS=new BlockPos(8,400,8);
 private static final String[] CONFIGS={"shrine/cave_spider","trident_trials_monument/boss"};
 private static final String[] EXPECTED={"trial_normal","elder_guardian_boss_normal"};
 private void check(boolean ok,String label){if(!ok)throw new AssertionError(label);checks.add(label);}
 @Override public void onEnable(){Bukkit.getPluginManager().registerEvents(this,this);}
 @EventHandler public void loaded(ServerLoadEvent event){
  world=Bukkit.getWorlds().stream().filter(w->w.getEnvironment()==org.bukkit.World.Environment.NORMAL).findFirst().orElseThrow();
  level=((CraftWorld)world).getHandle();
  Bukkit.getGlobalRegionScheduler().execute(this,()->{
   try{world.setChunkForceLoaded(0,0,true);
    world.getChunkAtAsync(0,0,true).whenComplete((chunk,error)->{
     if(error!=null){report(error);return;}
     Bukkit.getRegionScheduler().execute(this,world,0,0,()->{
      try{prepare(0);getLogger().info("R38 TRIAL FIXTURE READY");}catch(Throwable e){report(e);}
     });
    });
   }catch(Throwable e){report(e);}
  });
 }
 @EventHandler public void joined(PlayerJoinEvent event){
  var player=event.getPlayer();if(!player.getName().equals("NLWaterQA"))return;
  playerId=player.getUniqueId();player.setGameMode(GameMode.SURVIVAL);
  player.setInvulnerable(true);player.setGravity(false);
  player.teleportAsync(new Location(world,8.5,400,12.5)).whenComplete((ok,error)->{
   if(error!=null){report(error);return;}
   Bukkit.getRegionScheduler().execute(this,world,0,0,()->{
    try{
     check(Boolean.TRUE.equals(ok),"real connected player reached fixture");
     check(player.getGameMode()==GameMode.SURVIVAL,"ordinary survival player, not creative or spectator");
     check(!player.isOp(),"player has no operator permission");
     poll();
    }catch(Throwable e){report(e);}
   });
  });
 }
 private void prepare(int next){
  phase=next;ticks=0;
  for(var e:level.getEntitiesOfClass(Mob.class,new AABB(1,396,1,16,410,16),e->true))e.discard();
  level.setBlock(POS,Blocks.AIR.defaultBlockState(),3);
  BlockPos.MutableBlockPos p=new BlockPos.MutableBlockPos();
  for(int y=399;y<=406;y++)for(int z=1;z<=15;z++)for(int x=1;x<=15;x++){
   boolean shell=y==399||y==406||x==1||x==15||z==1||z==15;
   var block=shell?Blocks.STONE:(next==1?Blocks.WATER:Blocks.AIR);
   level.setBlock(p.set(x,y,z),block.defaultBlockState(),3);
  }
  level.setBlock(POS,Blocks.TRIAL_SPAWNER.defaultBlockState(),3);
  var spawner=(TrialSpawnerBlockEntity)level.getBlockEntity(POS);
  var registry=level.registryAccess().lookupOrThrow(Registries.TRIAL_SPAWNER_CONFIG);
  var normal=registry.getOrThrow(ResourceKey.create(Registries.TRIAL_SPAWNER_CONFIG,Identifier.fromNamespaceAndPath("nova_structures",CONFIGS[next]+"/normal")));
  var ominous=registry.getOrThrow(ResourceKey.create(Registries.TRIAL_SPAWNER_CONFIG,Identifier.fromNamespaceAndPath("nova_structures",CONFIGS[next]+"/ominous")));
  spawner.getTrialSpawner().config=new TrialSpawner.FullConfig(normal,ominous,36000,14);
  spawner.markUpdated();
  checks.add("unmodified registry configuration: nova_structures:"+CONFIGS[next]+"/normal");
  // We do not inject registered players, replace the detector or tick manually.
 }
 @EventHandler public void spawned(CreatureSpawnEvent event){
  if(finished||level==null||event.getSpawnReason()!=CreatureSpawnEvent.SpawnReason.TRIAL_SPAWNER)return;
  var e=((org.bukkit.craftbukkit.entity.CraftEntity)event.getEntity()).getHandle();
  if(!ca.spottedleaf.moonrise.common.util.TickThread.isTickThreadFor(e))return;
  if(e.level()!=level||e.getY()<399||e.getY()>408||e.getX()<1||e.getX()>16||e.getZ()<1||e.getZ()>16)return;
  spawns.add("phase="+phase+" type="+event.getEntityType()+" tags="+e.entityTags()+" reason="+event.getSpawnReason()+" cancelled="+event.isCancelled());
 }
 private void poll(){
  if(finished)return;
  try{
   var spawner=(TrialSpawnerBlockEntity)level.getBlockEntity(POS);
   var data=spawner.getTrialSpawner().getStateData();
   states.add("phase="+phase+" ticks="+ticks+" state="+spawner.getState()+" registered="+data.detectedPlayers);
   boolean spawned=spawns.stream().anyMatch(s->s.startsWith("phase="+phase+" ")&&s.contains(EXPECTED[phase])&&s.contains("cancelled=false"));
   if(spawned){
    check(data.detectedPlayers.contains(playerId),"native detector registered actual player for "+CONFIGS[phase]);
    check(true,"actual TRIAL_SPAWNER event with expected custom tags: "+CONFIGS[phase]);
    if(phase==0){prepare(1);}else{report(null);return;}
   }
   ticks+=10;
   if(ticks>600)throw new AssertionError("no natural trial mob within 30 seconds: "+CONFIGS[phase]);
   Bukkit.getRegionScheduler().runDelayed(this,world,0,0,task->poll(),10);
  }catch(Throwable e){report(e);}
 }
 private synchronized void report(Throwable error){
  if(finished)return;finished=true;
  if(error!=null)error.printStackTrace();
  try{
   getDataFolder().mkdirs();var result=new com.google.gson.JsonObject();result.addProperty("pass",error==null);
   result.addProperty("scope","real loopback survival client; unmodified normal cave-spider and trident-monument elder-guardian configs; not all bosses/abilities/ominous encounters");
   result.add("checks",new com.google.gson.Gson().toJsonTree(checks));result.add("observed_spawns",new com.google.gson.Gson().toJsonTree(spawns));result.add("states",new com.google.gson.Gson().toJsonTree(states));
   if(error!=null)result.addProperty("error",error.toString());
   Files.writeString(getDataFolder().toPath().resolve("result.json"),new com.google.gson.GsonBuilder().setPrettyPrinting().create().toJson(result));
  }catch(Exception e){e.printStackTrace();}
  Bukkit.getGlobalRegionScheduler().execute(this,()->world.setChunkForceLoaded(0,0,false));
  getLogger().info("R38 NATURAL TRIAL QA "+(error==null?"PASS":"FAIL")+" checks="+checks.size());
 }
}
