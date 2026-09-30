import com.google.gson.*;
import java.lang.reflect.*;import java.nio.file.Files;import java.util.*;
import net.minecraft.core.BlockPos;import net.minecraft.server.level.*;import net.minecraft.util.StaticCache2D;
import net.minecraft.world.level.ChunkPos;import net.minecraft.world.level.block.Blocks;import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.chunk.*;import net.minecraft.world.level.chunk.status.ChunkStatus;
import org.bukkit.*;import org.bukkit.craftbukkit.CraftWorld;import org.bukkit.event.*;import org.bukkit.event.server.ServerLoadEvent;import org.bukkit.plugin.java.JavaPlugin;

public final class R3927ClassifierQa extends JavaPlugin implements Listener {
 private final JsonArray cases=new JsonArray();private boolean started,finished;private final String nonce=System.getProperty("neverfolia.qaNonce","");
 @Override public void onEnable(){Bukkit.getPluginManager().registerEvents(this,this);}
 @EventHandler public void load(ServerLoadEvent e){if(started)return;started=true;try{World w=Bukkit.getWorlds().stream().filter(x->x.getEnvironment()==World.Environment.NORMAL).findFirst().orElseThrow();w.getChunkAtAsync(0,0,true).whenComplete((c,err)->{if(err!=null){finish(err);return;}Bukkit.getRegionScheduler().execute(this,w,0,0,()->{try{runAll(((CraftWorld)w).getHandle());finish(null);}catch(Throwable t){finish(t);}});});}catch(Throwable t){finish(t);}}
 static void need(boolean v,String m){if(!v)throw new AssertionError(m);}
 static final class Holder extends GenerationChunkHolder{final ProtoChunk c;Holder(ProtoChunk c){super(c.getPos());this.c=c;}@Override public int getQueueLevel(){return 0;}@Override public int getTicketLevel(){return 0;}@Override protected void addSaveDependency(java.util.concurrent.CompletableFuture<?> f){throw new UnsupportedOperationException();}@Override public ChunkAccess getChunkIfPresent(ChunkStatus s){return c.getPersistedStatus().isOrAfter(s)?c:null;}}
 static final class Scene{
  final ServerLevel level;final ProtoChunk[] cs=new ProtoChunk[9];final int cx,cz;
  Scene(ServerLevel l,int cx,int cz)throws Exception{level=l;this.cx=cx;this.cz=cz;var fs=Arrays.stream(l.getClass().getMethods()).filter(m->m.getParameterCount()==0&&m.getReturnType().getSimpleName().equals("PalettedContainerFactory")).toList();need(fs.size()==1,"palette");Object factory=fs.getFirst().invoke(l);var ct=Arrays.stream(ProtoChunk.class.getConstructors()).filter(c->c.getParameterCount()==5&&c.getParameterTypes()[0]==ChunkPos.class&&c.getParameterTypes()[3].isInstance(factory)).toList();need(ct.size()==1,"ctor");for(int dz=-1;dz<=1;dz++)for(int dx=-1;dx<=1;dx++){ProtoChunk p=(ProtoChunk)ct.getFirst().newInstance(new ChunkPos(cx+dx,cz+dz),UpgradeData.EMPTY,l,factory,null);cs[(dz+1)*3+dx+1]=p;BlockPos.MutableBlockPos q=new BlockPos.MutableBlockPos();for(int y=0;y<=140;y++)for(int z=0;z<16;z++)for(int x=0;x<16;x++){q.set(p.getPos().getMinBlockX()+x,y,p.getPos().getMinBlockZ()+z);p.setBlockState(q,Blocks.STONE.defaultBlockState(),0);}p.setPersistedStatus(ChunkStatus.FEATURES);}}
  ProtoChunk owner(){return cs[4];}BlockPos p(int x,int y,int z){return new BlockPos(cx*16+x,y,cz*16+z);}void put(int x,int y,int z,BlockState s){int tile=((z>>4)+1)*3+(x>>4)+1;cs[tile].setBlockState(p(x,y,z),s,0);}StaticCache2D<GenerationChunkHolder> cache(){return StaticCache2D.create(cx,cz,1,(x,z)->new Holder(cs[(z-cz+1)*3+x-cx+1]));}
  void shallowBox(BlockState s){for(int x=4;x<12;x++)for(int z=4;z<12;z++)for(int y=108;y<110;y++)put(x,y,z,s);}
  void openTunnel(){for(int x=8;x<=31;x++)put(x,64,8,Blocks.AIR.defaultBlockState());for(int y=64;y<=128;y++)put(31,y,8,Blocks.AIR.defaultBlockState());}
 }
 void verify(String name,Scene s,int expected)throws Exception{BlockState[] before=capture(s.owner());int n=NeverOverworldOceanClassifierR3927.apply(s.level,s.cache(),s.owner());need(n==expected,name+" "+n+" != "+expected);BlockState[] after=capture(s.owner());int seen=0;for(int i=0;i<before.length;i++)if(before[i]!=after[i]){need(before[i].isAir()&&after[i]==Blocks.WATER.defaultBlockState(),name+" bad delta");int y=(i>>>8)-512;need(y<=128,name+" above sea");seen++;}need(seen==n,name+" count");JsonObject r=new JsonObject();r.addProperty("name",name);r.addProperty("changed",n);r.addProperty("pass",true);cases.add(r);}
 static BlockState[] capture(ChunkAccess c){BlockState[] a=new BlockState[1024*256];BlockPos.MutableBlockPos p=new BlockPos.MutableBlockPos();for(int y=-512;y<=511;y++)for(int z=0;z<16;z++)for(int x=0;x<16;x++){p.set(c.getPos().getMinBlockX()+x,y,c.getPos().getMinBlockZ()+z);a[((y+512)<<8)|(z<<4)|x]=c.getBlockState(p);}return a;}
 void runAll(ServerLevel level)throws Exception{
  need(Boolean.getBoolean("neverfolia.r3927OceanClassifier"),"flag");
  Scene a=new Scene(level,0,0);a.shallowBox(Blocks.AIR.defaultBlockState());verify("large_shallow_plain_air_is_ocean_void",a,128);
  Scene b=new Scene(level,0,0);b.shallowBox(Blocks.AIR.defaultBlockState());b.owner().getOrCreateCarvingMask().set(b.cx*16+4,108,b.cz*16+4);verify("one_carving_bit_protects_component",b,0);
  Scene c=new Scene(level,0,0);c.shallowBox(Blocks.CAVE_AIR.defaultBlockState());verify("cave_air_protects_component",c,0);
  Scene d=new Scene(level,0,0);for(int x=4;x<12;x++)for(int z=4;z<12;z++)for(int y=40;y<42;y++)d.put(x,y,z,Blocks.AIR.defaultBlockState());verify("deep_unknown_air_stays_dry",d,0);
  Scene e=new Scene(level,0,0);e.openTunnel();e.owner().getOrCreateCarvingMask().set(e.cx*16+8,64,e.cz*16+8);verify("carved_but_ocean_connected_floods",e,8);
  Scene f=new Scene(level,0,0);f.shallowBox(Blocks.AIR.defaultBlockState());for(int x=4;x<12;x++)f.put(x,129,4,Blocks.STONE.defaultBlockState());verify("y129_irrelevant",f,128);
  need(cases.size()==6,"cases");
 }
 synchronized void finish(Throwable e){if(finished)return;finished=true;JsonObject r=new JsonObject();r.addProperty("pass",e==null);r.addProperty("nonce",nonce);r.add("cases",cases);r.addProperty("scope","Real ProtoChunk + vanilla CarvingMask provenance; no user world.");if(e!=null){r.addProperty("error",e.toString());e.printStackTrace();}try{getDataFolder().mkdirs();Files.writeString(getDataFolder().toPath().resolve("result.json"),new GsonBuilder().setPrettyPrinting().create().toJson(r));}catch(Exception x){x.printStackTrace();e=x;}getLogger().info("R3927 FIXTURE "+(e==null?"PASS ":"FAIL ")+nonce);}
}
