import com.google.gson.*;
import java.lang.reflect.Constructor;
import java.lang.reflect.Method;
import java.nio.file.Files;
import java.util.*;
import net.minecraft.core.BlockPos;
import net.minecraft.server.level.GenerationChunkHolder;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.util.StaticCache2D;
import net.minecraft.world.level.ChunkPos;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.chunk.*;
import net.minecraft.world.level.chunk.status.ChunkStatus;
import org.bukkit.Bukkit;
import org.bukkit.NamespacedKey;
import org.bukkit.World;
import org.bukkit.craftbukkit.CraftWorld;
import org.bukkit.event.*;
import org.bukkit.event.server.ServerLoadEvent;
import org.bukkit.persistence.PersistentDataType;
import org.bukkit.plugin.java.JavaPlugin;

public final class R3926ClassifierQa extends JavaPlugin implements Listener {
    private final JsonArray cases=new JsonArray();
    private boolean started,finished;
    private final String nonce=System.getProperty("neverfolia.qaNonce","");
    private static final NamespacedKey KEY=new NamespacedKey("neverfolia","dry_mines_r12");

    @Override public void onEnable(){Bukkit.getPluginManager().registerEvents(this,this);}
    @EventHandler public void loaded(ServerLoadEvent e){
        if(started)return;started=true;
        try{
            World world=Bukkit.getWorlds().stream().filter(w->w.getEnvironment()==World.Environment.NORMAL).findFirst().orElseThrow();
            need(world.getSeed()==-4651369264513492755L,"Wrong seed");
            world.getChunkAtAsync(0,0,true).whenComplete((chunk,error)->{
                if(error!=null){finish(error);return;}
                Bukkit.getRegionScheduler().execute(this,world,0,0,()->{
                    try{runAll(((CraftWorld)world).getHandle());finish(null);}
                    catch(Throwable t){finish(t);}
                });
            });
        }catch(Throwable t){finish(t);}
    }
    static void need(boolean v,String m){if(!v)throw new AssertionError(m);}

    static final class Holder extends GenerationChunkHolder {
        final ProtoChunk chunk;
        Holder(ProtoChunk c){super(c.getPos());chunk=c;}
        @Override public int getQueueLevel(){return 0;}
        @Override public int getTicketLevel(){return 0;}
        @Override protected void addSaveDependency(java.util.concurrent.CompletableFuture<?> f){throw new UnsupportedOperationException();}
        @Override public ChunkAccess getChunkIfPresent(ChunkStatus s){return chunk.getPersistedStatus().isOrAfter(s)?chunk:null;}
    }

    static final class Scene {
        final ServerLevel level;final ProtoChunk[] chunks=new ProtoChunk[9];final int cx,cz;
        Scene(ServerLevel level,int cx,int cz)throws Exception{
            this.level=level;this.cx=cx;this.cz=cz;
            List<Method> factories=Arrays.stream(level.getClass().getMethods()).filter(m->m.getParameterCount()==0&&m.getReturnType().getSimpleName().equals("PalettedContainerFactory")).toList();
            need(factories.size()==1,"palette factory");
            Object factory=factories.getFirst().invoke(level);
            List<Constructor<?>> constructors=Arrays.stream(ProtoChunk.class.getConstructors()).filter(c->c.getParameterCount()==5&&c.getParameterTypes()[0]==ChunkPos.class&&c.getParameterTypes()[3].isInstance(factory)).toList();
            need(constructors.size()==1,"ProtoChunk ctor");
            for(int dz=-1;dz<=1;dz++)for(int dx=-1;dx<=1;dx++){
                ProtoChunk p=(ProtoChunk)constructors.getFirst().newInstance(new ChunkPos(cx+dx,cz+dz),UpgradeData.EMPTY,level,factory,null);
                chunks[(dz+1)*3+dx+1]=p;
                BlockPos.MutableBlockPos pos=new BlockPos.MutableBlockPos();
                for(int y=-16;y<=140;y++)for(int z=0;z<16;z++)for(int x=0;x<16;x++){
                    pos.set(p.getPos().getMinBlockX()+x,y,p.getPos().getMinBlockZ()+z);
                    p.setBlockState(pos,Blocks.STONE.defaultBlockState(),0);
                }
                p.setPersistedStatus(ChunkStatus.FEATURES);
            }
        }
        ProtoChunk owner(){return chunks[4];}
        BlockPos pos(int x,int y,int z){return new BlockPos(cx*16+x,y,cz*16+z);}
        void put(int x,int y,int z,BlockState s){int tile=((z>>4)+1)*3+(x>>4)+1;chunks[tile].setBlockState(pos(x,y,z),s,0);}
        BlockState at(int x,int y,int z){int tile=((z>>4)+1)*3+(x>>4)+1;return chunks[tile].getBlockState(pos(x,y,z));}
        void tunnel(boolean roofAboveSea){
            for(int x=8;x<=31;x++)put(x,64,8,Blocks.AIR.defaultBlockState());
            for(int y=64;y<=128;y++)put(31,y,8,Blocks.AIR.defaultBlockState());
            if(roofAboveSea)for(int x=8;x<=31;x++)put(x,129,8,Blocks.STONE.defaultBlockState());
            else for(int x=8;x<=31;x++)put(x,129,8,Blocks.AIR.defaultBlockState());
        }
        StaticCache2D<GenerationChunkHolder> cache(boolean missEast){
            return StaticCache2D.create(cx,cz,1,(x,z)->{
                if(missEast&&x==cx+1&&z==cz)return null;
                return new Holder(chunks[(z-cz+1)*3+x-cx+1]);
            });
        }
    }

    void verify(String name,Scene s,boolean missing,int expected)throws Exception{
        BlockState[] before=capture(s.owner());
        int changed=NeverOverworldOceanClassifierR3926.apply(s.level,s.cache(missing),s.owner());
        need(changed==expected,name+" changed="+changed+" expected="+expected);
        BlockState[] after=capture(s.owner());int observed=0;
        for(int i=0;i<before.length;i++)if(before[i]!=after[i]){
            int y=(i>>>8)-512;
            need(before[i].isAir()&&after[i]==Blocks.WATER.defaultBlockState(),name+" non AIR->WATER");
            need(y<=128,name+" write above sea");
            observed++;
        }
        need(observed==changed,name+" counter mismatch");
        JsonObject row=new JsonObject();row.addProperty("name",name);row.addProperty("changed",changed);row.addProperty("pass",true);cases.add(row);
    }

    static BlockState[] capture(ChunkAccess c){
        BlockState[] out=new BlockState[1024*256];BlockPos.MutableBlockPos p=new BlockPos.MutableBlockPos();
        for(int y=-512;y<=511;y++)for(int z=0;z<16;z++)for(int x=0;x<16;x++){
            p.set(c.getPos().getMinBlockX()+x,y,c.getPos().getMinBlockZ()+z);
            out[((y+512)<<8)|(z<<4)|x]=c.getBlockState(p);
        }
        return out;
    }

    void runAll(ServerLevel level)throws Exception{
        need(Boolean.getBoolean("neverfolia.r3926OceanClassifier"),"R3926 flag disabled");

        Scene a=new Scene(level,0,0);a.tunnel(false);verify("open_above_129",a,false,8);
        Scene b=new Scene(level,0,0);b.tunnel(true);verify("solid_branch_at_129_ignored",b,false,8);

        Scene c=new Scene(level,0,0);c.put(8,64,8,Blocks.AIR.defaultBlockState());verify("closed_cave_stays_dry",c,false,0);

        Scene d=new Scene(level,0,0);d.tunnel(true);verify("missing_east_neighbour_not_proof",d,true,0);

        Scene e=new Scene(level,0,0);e.tunnel(true);e.put(12,64,8,Blocks.BLUE_ICE.defaultBlockState());verify("ice_is_barrier_not_target",e,false,3);

        Scene f=new Scene(level,0,0);f.tunnel(true);e=null;
        f.put(12,64,7,Blocks.LAVA.defaultBlockState());verify("lava_halo_blocks_path",f,false,3);

        Scene g=new Scene(level,0,0);g.tunnel(true);
        int[] boxes={1,1,8,64,8,10,64,8};g.owner().persistentDataContainer.set(KEY,PersistentDataType.INTEGER_ARRAY,boxes);
        need(NeverOverworldDryMinesR12.protectedCell(g.owner(),g.pos(8,64,8)),"R39.9 persisted mine guard lost");
        verify("persisted_mine_stays_dry",g,false,4);

        Scene h=new Scene(level,0,0);h.tunnel(true);h.owner().setPersistedStatus(ChunkStatus.FULL);verify("full_chunk_not_rewritten",h,false,0);

        need(NeverOverworldWaterPolicyR38.allowsNewWater(64,64,true),"R396 water equality fix lost");
        need(cases.size()==8,"Incomplete R3926 fixtures");
    }

    synchronized void finish(Throwable error){
        if(finished)return;finished=true;
        JsonObject r=new JsonObject();r.addProperty("pass",error==null);r.addProperty("nonce",nonce);r.addProperty("seed",-4651369264513492755L);r.add("cases",cases);
        r.addProperty("scope","Real ProtoChunk fixture with compiled R3926 adapter; validates Y129 irrelevance and protected dry caves. Not full natural-world acceptance.");
        if(error!=null){r.addProperty("error",error.toString());error.printStackTrace();}
        try{getDataFolder().mkdirs();Files.writeString(getDataFolder().toPath().resolve("result.json"),new GsonBuilder().setPrettyPrinting().create().toJson(r));}
        catch(Exception x){x.printStackTrace();error=x;}
        getLogger().info("R3926 FIXTURE "+(error==null?"PASS ":"FAIL ")+nonce);
    }
}
