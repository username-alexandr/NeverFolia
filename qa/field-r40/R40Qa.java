import com.google.gson.*;
import java.nio.file.Files;
import java.security.MessageDigest;
import java.util.*;
import org.bukkit.*;
import org.bukkit.block.data.Levelled;
import org.bukkit.event.*;
import org.bukkit.event.server.ServerLoadEvent;
import org.bukkit.plugin.java.JavaPlugin;

/** Read-only observations in newly created CI worlds, never a repair plugin. */
public final class R40Qa extends JavaPlugin implements Listener {
 private World world;
 private final List<int[]> targets=new ArrayList<>();
 private final JsonArray rows=new JsonArray();
 private int index;private boolean started,finished;
 private final String nonce=System.getProperty("neverfolia.qaNonce","");
 private final boolean reverse=Boolean.getBoolean("neverfolia.qaReverse");
 private static final int LOW=-511,HIGH=128;
 @Override public void onEnable(){Bukkit.getPluginManager().registerEvents(this,this);}
 @EventHandler public void loaded(ServerLoadEvent event){
  if(started)return;started=true;
  try{
   if(nonce.isBlank())throw new AssertionError("Missing fresh process nonce");
   world=Bukkit.getWorlds().stream().filter(w->w.getEnvironment()==World.Environment.NORMAL).findFirst().orElseThrow();
   if(world.getSeed()!=-4651369264513492755L)throw new AssertionError("Wrong seed");
   int[][] centers={{7,1},{1,-4},{-197,-217},{-169,-250},{-189,-223},{-1699,-769},{-202,-213}};
   TreeMap<String,int[]> selected=new TreeMap<>();
   for(int[] c:centers)for(int dz=-1;dz<=1;dz++)for(int dx=-1;dx<=1;dx++)selected.put((c[0]+dx)+","+(c[1]+dz),new int[]{c[0]+dx,c[1]+dz});
   targets.addAll(selected.values());if(reverse)Collections.reverse(targets);
   if(targets.size()!=63)throw new AssertionError("Invalid sample size");
   Bukkit.getGlobalRegionScheduler().execute(this,()->next());
  }catch(Throwable error){finish(error);}
 }
 private void next(){
  if(finished)return;if(index==targets.size()){finish(null);return;}
  int[] t=targets.get(index);int cx=t[0],cz=t[1];
  world.getChunkAtAsync(cx,cz,true).whenComplete((chunk,error)->{
   if(error!=null){finish(error);return;}
   Bukkit.getRegionScheduler().execute(this,world,cx,cz,()->{
    try{rows.add(sample(chunk.getChunkSnapshot(false,true,false),cx,cz));index++;getLogger().info("R40 SAMPLE "+index+"/"+targets.size()+" "+cx+","+cz);Bukkit.getGlobalRegionScheduler().execute(this,()->next());}
    catch(Throwable e){finish(e);}
   });
  });
 }
 private JsonObject sample(ChunkSnapshot s,int cx,int cz)throws Exception{
  JsonObject row=new JsonObject(),counts=new JsonObject();Map<String,Integer> types=new TreeMap<>();
  byte[] water=new byte[(HIGH-LOW+1)*256];JsonArray airExamples=new JsonArray(),iceExamples=new JsonArray();
  int singles=0,ice=0,iceSingles=0;
  for(int y=LOW;y<=HIGH;y++)for(int z=0;z<16;z++)for(int x=0;x<16;x++){
   Material m=s.getBlockType(x,y,z);types.merge(m.getKey().toString(),1,Integer::sum);int k=((y-LOW)<<8)|(z<<4)|x;
   if(m==Material.WATER)water[k]=(byte)(1+((Levelled)s.getBlockData(x,y,z)).getLevel());else if(aquatic(m))water[k]=1;
   boolean frozen=m==Material.ICE||m==Material.PACKED_ICE||m==Material.BLUE_ICE||m==Material.FROSTED_ICE;
   if(frozen){ice++;if(iceExamples.size()<40){JsonObject p=point(s,cx,cz,x,y,z,m);p.addProperty("state",s.getBlockData(x,y,z).getAsString());iceExamples.add(p);}}
   if((m.isAir()||frozen)&&x>0&&x<15&&z>0&&z<15&&y>LOW&&y<HIGH){
    boolean around=aquatic(s.getBlockType(x-1,y,z))&&aquatic(s.getBlockType(x+1,y,z))&&aquatic(s.getBlockType(x,y-1,z))&&aquatic(s.getBlockType(x,y+1,z))&&aquatic(s.getBlockType(x,y,z-1))&&aquatic(s.getBlockType(x,y,z+1));
    if(around){if(m.isAir()){singles++;if(airExamples.size()<30)airExamples.add(point(s,cx,cz,x,y,z,m));}else iceSingles++;}
   }
  }
  types.forEach(counts::addProperty);row.addProperty("chunk_x",cx);row.addProperty("chunk_z",cz);row.add("block_counts",counts);
  row.addProperty("water_sha256",HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(water)));
  row.addProperty("isolated_air",singles);row.addProperty("ice_blocks",ice);row.addProperty("isolated_ice",iceSingles);row.add("air_examples",airExamples);row.add("ice_examples",iceExamples);return row;
 }
 private JsonObject point(ChunkSnapshot s,int cx,int cz,int x,int y,int z,Material m){JsonObject p=new JsonObject();p.addProperty("x",cx*16+x);p.addProperty("y",y);p.addProperty("z",cz*16+z);p.addProperty("block",m.getKey().toString());p.addProperty("biome",s.getBiome(x,y,z).getKey().toString());return p;}
 private static boolean aquatic(Material t){return t==Material.WATER||t==Material.BUBBLE_COLUMN||t==Material.KELP||t==Material.KELP_PLANT||t==Material.SEAGRASS||t==Material.TALL_SEAGRASS;}
 private synchronized void finish(Throwable e){
  if(finished)return;finished=true;JsonObject r=new JsonObject();r.addProperty("pass",e==null);r.addProperty("nonce",nonce);r.addProperty("seed",world==null?0:world.getSeed());r.addProperty("reverse",reverse);r.addProperty("completed",rows.size());r.add("chunks",rows);
  if(e!=null){r.addProperty("error",e.toString());e.printStackTrace();}
  try{getDataFolder().mkdirs();Files.writeString(getDataFolder().toPath().resolve("result.json"),new GsonBuilder().setPrettyPrinting().create().toJson(r));}catch(Exception ex){ex.printStackTrace();e=ex;}
  getLogger().info("R40 NATURAL QA "+(e==null?"PASS ":"FAIL ")+nonce);
 }
}
