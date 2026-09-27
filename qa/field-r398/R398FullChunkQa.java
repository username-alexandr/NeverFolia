import com.google.gson.*;
import java.nio.file.Files;
import java.util.EnumSet;
import org.bukkit.Bukkit;
import org.bukkit.World;
import org.bukkit.craftbukkit.CraftWorld;
import org.bukkit.event.EventHandler;
import org.bukkit.event.Listener;
import org.bukkit.event.server.ServerLoadEvent;
import org.bukkit.plugin.java.JavaPlugin;
import net.minecraft.core.BlockPos;
import net.minecraft.server.level.GenerationChunkHolder;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.util.StaticCache2D;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.LiquidBlock;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.chunk.*;
import net.minecraft.world.level.chunk.status.ChunkStatus;
import net.minecraft.world.level.levelgen.Heightmap;

/** Synthetic regression in a NEW CI world only. Never included in a user kit.
 * Direct public cleanup calls exercise the FULL guard, not a real relight request.
 * Every cell of the tested 1024-high chunk is compared, including fluid properties.
 */
public final class R398FullChunkQa extends JavaPlugin implements Listener {
 private boolean started,finished;
 private final JsonArray cases=new JsonArray();
 private final boolean fixed=Boolean.getBoolean("neverfolia.qaFullGuard");
 @Override public void onEnable(){Bukkit.getPluginManager().registerEvents(this,this);}
 @EventHandler public void loaded(ServerLoadEvent event){
  if(started)return;started=true;
  try{
   World world=Bukkit.getWorlds().stream().filter(w->w.getEnvironment()==World.Environment.NORMAL).findFirst().orElseThrow();
   if(world.getSeed()!=-4651369264513492755L)throw new AssertionError("Wrong seed");
   world.getChunkAtAsync(0,0,true).whenComplete((loaded,error)->{
    if(error!=null){finish(error);return;}
    Bukkit.getRegionScheduler().execute(this,world,0,0,()->{
     try{
      ServerLevel level=((CraftWorld)world).getHandle();ChunkAccess chunk=level.getChunkAt(new BlockPos(8,120,8));
      if(!(chunk instanceof LevelChunk)||chunk.getPersistedStatus()!=ChunkStatus.FULL)throw new AssertionError("Not a real FULL chunk");
      if(chunk.getMinY()!=-512||chunk.getHeight()!=1024)throw new AssertionError("Wrong envelope");
      test(chunk,"reweather_full",true,()->NeverOverworldFlood.reweatherSubmergedSurface(level,chunk));
      test(chunk,"submerged_remnants_full",true,()->NeverOverworldSubmergedRemnants.apply(level,chunk));
      test(chunk,"local_connectivity_full",false,()->{NeverOverworldFloodConnectivityR15.apply(level,chunk);});
      StaticCache2D<GenerationChunkHolder> cache=StaticCache2D.create(0,0,1,(x,z)->null);
      test(chunk,"cached_connectivity_full",false,()->{NeverOverworldFloodConnectivityR15.reconcileSeams(level,cache,chunk);});
      if(cases.size()!=4)throw new AssertionError("Incomplete direct-call coverage");
      finish(null);
     }catch(Throwable failure){finish(failure);}
    });
   });
  }catch(Throwable failure){finish(failure);}
 }
 private static void put(ChunkAccess c,int x,int y,int z,BlockState s){c.setBlockState(new BlockPos(x,y,z),s,0);}
 private void fixture(ChunkAccess chunk){
  for(int y=119;y<chunk.getMaxY();y++){
   put(chunk,8,y,8,Blocks.AIR.defaultBlockState());
   put(chunk,9,y,8,Blocks.AIR.defaultBlockState());
  }
  put(chunk,8,119,8,Blocks.STONE.defaultBlockState());
  put(chunk,8,120,8,Blocks.GRASS_BLOCK.defaultBlockState());
  put(chunk,8,121,8,Blocks.SNOW_BLOCK.defaultBlockState());
  for(int y=122;y<=128;y++)put(chunk,8,y,8,Blocks.WATER.defaultBlockState());
  put(chunk,8,125,8,Blocks.AIR.defaultBlockState());
  put(chunk,9,121,8,Blocks.WATER.defaultBlockState().setValue(LiquidBlock.LEVEL,5));
  Heightmap.primeHeightmaps(chunk,EnumSet.of(Heightmap.Types.OCEAN_FLOOR_WG));
 }
 private void test(ChunkAccess chunk,String name,boolean baselineMustChange,Runnable action){
  fixture(chunk);
  int length=chunk.getHeight()*256;BlockState[] before=new BlockState[length];
  BlockPos.MutableBlockPos p=new BlockPos.MutableBlockPos();
  for(int y=chunk.getMinY();y<chunk.getMaxY();y++)for(int z=0;z<16;z++)for(int x=0;x<16;x++)before[((y-chunk.getMinY())<<8)|(z<<4)|x]=chunk.getBlockState(p.set(x,y,z));
  action.run();int changed=0;JsonArray examples=new JsonArray();
  for(int y=chunk.getMinY();y<chunk.getMaxY();y++)for(int z=0;z<16;z++)for(int x=0;x<16;x++){
   BlockState old=before[((y-chunk.getMinY())<<8)|(z<<4)|x],now=chunk.getBlockState(p.set(x,y,z));
   if(!old.equals(now)){
    changed++;if(examples.size()<12){JsonObject e=new JsonObject();e.addProperty("x",x);e.addProperty("y",y);e.addProperty("z",z);e.addProperty("before",old.toString());e.addProperty("after",now.toString());examples.add(e);}
   }
  }
  boolean pass=fixed?changed==0:(!baselineMustChange||changed>0);
  JsonObject r=new JsonObject();r.addProperty("name",name);r.addProperty("checked_cells",length);r.addProperty("changed_cells",changed);r.addProperty("baseline_mutation_required",baselineMustChange);r.addProperty("pass",pass);r.add("examples",examples);cases.add(r);
  if(!pass)throw new AssertionError(name+": changed="+changed+", fixed="+fixed);
 }
 private synchronized void finish(Throwable error){
  if(finished)return;finished=true;
  JsonObject r=new JsonObject();r.addProperty("pass",error==null);r.addProperty("expect_full_guard",fixed);r.addProperty("scope","Four direct cleanup entry points in a real region-owned FULL chunk. Synthetic fixture; no actual light-engine rescheduling or natural generation acceptance.");r.add("cases",cases);
  if(error!=null){r.addProperty("error",error.toString());error.printStackTrace();}
  try{getDataFolder().mkdirs();Files.writeString(getDataFolder().toPath().resolve("result.json"),new GsonBuilder().setPrettyPrinting().create().toJson(r));}
  catch(Exception e){e.printStackTrace();error=e;}
  getLogger().info("R398 FULL QA "+(error==null?"PASS":"FAIL"));
 }
}
