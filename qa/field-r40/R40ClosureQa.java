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
import net.minecraft.world.level.block.LiquidBlock;
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

/** Real Minecraft ProtoChunks, states, PDC and the compiled production adapter.
 * The cache holders are fixture adapters, not the real scheduling system.
 * Fixtures remain in memory and are NOT installed into the server's world.
 */
public final class R40ClosureQa extends JavaPlugin implements Listener {
    private final JsonArray cases=new JsonArray();
    private boolean started,finished;
    private final String nonce=System.getProperty("neverfolia.qaNonce","");
    private static final NamespacedKey KEY=new NamespacedKey("neverfolia","dry_mines_r12");
    @Override public void onEnable(){Bukkit.getPluginManager().registerEvents(this,this);}
    @EventHandler public void loaded(ServerLoadEvent event) {
        if(started)return;started=true;
        try {
            World world=Bukkit.getWorlds().stream().filter(w->w.getEnvironment()==World.Environment.NORMAL).findFirst().orElseThrow();
            need(world.getSeed()==-4651369264513492755L,"Wrong seed");
            world.getChunkAtAsync(0,0,true).whenComplete((chunk,error)->{
                if(error!=null){finish(error);return;}
                Bukkit.getRegionScheduler().execute(this,world,0,0,()->{
                    try {runAll(((CraftWorld)world).getHandle());finish(null);}
                    catch(Throwable failure){finish(failure);}
                });
            });
        }catch(Throwable failure){finish(failure);}
    }
    private static void need(boolean ok,String why){if(!ok)throw new AssertionError(why);}
    private static final class FixtureHolder extends GenerationChunkHolder {
        private final ProtoChunk chunk;
        FixtureHolder(ProtoChunk chunk){super(chunk.getPos());this.chunk=chunk;}
        @Override public ChunkAccess getChunkIfPresent(ChunkStatus status){return chunk.getPersistedStatus().isOrAfter(status)?chunk:null;}
    }
    private static final class Scene {
        final ServerLevel level;final ProtoChunk[] chunks=new ProtoChunk[9];final int cx,cz;
        Scene(ServerLevel level,int cx,int cz)throws Exception {
            this.level=level;this.cx=cx;this.cz=cz;
            List<Method> factories=Arrays.stream(level.getClass().getMethods()).filter(m->m.getParameterCount()==0&&m.getReturnType().getSimpleName().equals("PalettedContainerFactory")).toList();
            need(factories.size()==1,"Expected exact world palette factory: "+factories);
            Object factory=factories.getFirst().invoke(level);
            List<Constructor<?>> constructors=Arrays.stream(ProtoChunk.class.getConstructors()).filter(c->c.getParameterCount()==5&&c.getParameterTypes()[0]==ChunkPos.class&&c.getParameterTypes()[3].isInstance(factory)).toList();
            need(constructors.size()==1,"Unexpected ProtoChunk constructor");
            for(int dz=-1;dz<=1;dz++)for(int dx=-1;dx<=1;dx++) {
                ProtoChunk p=(ProtoChunk)constructors.getFirst().newInstance(new ChunkPos(cx+dx,cz+dz),UpgradeData.EMPTY,level,factory,null);
                need(p.getMinY()==-512&&p.getHeight()==1024,"Wrong fixture envelope");
                chunks[(dz+1)*3+dx+1]=p;
                BlockPos.MutableBlockPos pos=new BlockPos.MutableBlockPos();
                for(int y=0;y<=129;y++)for(int z=0;z<16;z++)for(int x=0;x<16;x++) {
                    pos.set(p.getPos().getMinBlockX()+x,y,p.getPos().getMinBlockZ()+z);
                    p.setBlockState(pos,Blocks.STONE.defaultBlockState(),0);
                }
                p.setPersistedStatus(ChunkStatus.FEATURES);
            }
        }
        ProtoChunk owner(){return chunks[4];}
        // Coordinates below are relative to the owner's minimum block position.
        BlockPos pos(int x,int y,int z){return new BlockPos(cx*16+x,y,cz*16+z);}
        void put(int x,int y,int z,BlockState state){int tile=((z>>4)+1)*3+(x>>4)+1;chunks[tile].setBlockState(pos(x,y,z),state,0);}
        BlockState at(int x,int y,int z){int tile=((z>>4)+1)*3+(x>>4)+1;return chunks[tile].getBlockState(pos(x,y,z));}
        void connected(){
            for(int x=8;x<=30;x++)put(x,64,8,Blocks.AIR.defaultBlockState());
            for(int y=64;y<=128;y++)put(31,y,8,Blocks.WATER.defaultBlockState());
            put(31,129,8,Blocks.AIR.defaultBlockState());
        }
        StaticCache2D<GenerationChunkHolder> cache(boolean missingEast){
            return StaticCache2D.create(cx,cz,1,(x,z)->{
                if(missingEast&&x==cx+1&&z==cz)return null;
                return new FixtureHolder(chunks[(z-cz+1)*3+x-cx+1]);
            });
        }
    }
    private void verify(String name,Scene s,boolean missing,int expected)throws Exception {
        BlockState[][] before=new BlockState[9][];
        for(int tile=0;tile<9;tile++)before[tile]=capture(s.chunks[tile]);
        int[] originalMetadata=s.owner().persistentDataContainer.get(KEY,PersistentDataType.INTEGER_ARRAY);
        int changed=NeverOverworldOceanClosureR395.apply(s.level,s.cache(missing),s.owner());
        need(changed==expected,name+": changed "+changed+" expected "+expected);
        int observed=0;
        for(int tile=0;tile<9;tile++) {
            BlockState[] after=capture(s.chunks[tile]);
            for(int i=0;i<after.length;i++)if(before[tile][i]!=after[i]) {
                need(tile==4,name+": neighbour was written");
                need(before[tile][i].isAir()&&after[i]==Blocks.WATER.defaultBlockState(),name+": non AIR->source WATER delta");
                int y=(i>>>8)-512;need(y>=-511&&y<=128,name+": write outside range");
                need(!NeverOverworldDryMinesR12.protectedCell(s.owner(),s.pos(i&15,y,(i>>>4)&15)),name+": wrote protected interior");
                observed++;
            }
        }
        need(observed==changed,name+": write counter mismatch");
        need(Arrays.equals(originalMetadata,s.owner().persistentDataContainer.get(KEY,PersistentDataType.INTEGER_ARRAY)),name+": changed PDC");
        need(NeverOverworldOceanClosureR395.apply(s.level,s.cache(missing),s.owner())==0,name+": second call not idempotent");
        JsonObject row=new JsonObject();row.addProperty("name",name);row.addProperty("changed",changed);row.addProperty("expected",expected);row.addProperty("pass",true);
        row.addProperty("all_neighbour_blocks_preserved",true);row.addProperty("protected_metadata_preserved",true);row.addProperty("second_call_changes",0);cases.add(row);
    }
    private static BlockState[] capture(ChunkAccess c){
        BlockState[] states=new BlockState[1024*256];BlockPos.MutableBlockPos p=new BlockPos.MutableBlockPos();
        for(int y=-512;y<=511;y++)for(int z=0;z<16;z++)for(int x=0;x<16;x++) {
            p.set(c.getPos().getMinBlockX()+x,y,c.getPos().getMinBlockZ()+z);states[((y+512)<<8)|(z<<4)|x]=c.getBlockState(p);
        }
        return states;
    }
    private void runAll(ServerLevel level)throws Exception {
        need(Boolean.getBoolean("neverfolia.r395OceanClosure"),"Closure not enabled in fixture process");
        Scene s=new Scene(level,0,0);s.connected();verify("side_entry_under_solid_island",s,false,8);
        s=new Scene(level,-1,-1);s.connected();verify("same_side_entry_negative_chunk",s,false,8);
        s=new Scene(level,0,0);s.connected();s.put(15,64,8,Blocks.STONE.defaultBlockState());verify("closed_cave_stays_dry",s,false,0);
        s=new Scene(level,0,0);s.connected();verify("missing_neighbour_is_not_ocean",s,true,0);
        s=new Scene(level,0,0);s.connected();s.put(31,129,8,Blocks.STONE.defaultBlockState());verify("roofed_native_water_is_not_seed",s,false,0);
        s=new Scene(level,0,0);s.connected();s.put(12,64,8,Blocks.BLUE_ICE.defaultBlockState());verify("solid_ice_is_not_erased",s,false,3);
        s=new Scene(level,0,0);s.connected();s.put(12,64,7,Blocks.LAVA.defaultBlockState());verify("lava_neighbour_blocks_flood_path",s,false,3);
        s=new Scene(level,0,0);s.connected();s.put(11,64,8,Blocks.WATER.defaultBlockState().setValue(LiquidBlock.LEVEL,5));verify("native_flowing_water_preserved",s,false,7);
        s=new Scene(level,0,0);s.connected();s.put(8,130,8,Blocks.AIR.defaultBlockState());
        int[] boxes={1,1,8,64,8,10,64,8};s.owner().persistentDataContainer.set(KEY,PersistentDataType.INTEGER_ARRAY,boxes);
        need(s.owner().neverOverworldDryMineMaskR12==null,"Unexpected synthetic cache");
        need(NeverOverworldDryMinesR12.protectedCell(s.owner(),s.pos(8,64,8)),"R399 protection lost");
        verify("persisted_mine_envelope_without_cache",s,false,4);
        s=new Scene(level,0,0);s.connected();s.owner().setPersistedStatus(ChunkStatus.FULL);verify("saved_full_chunk_is_not_rewritten",s,false,0);
        need(NeverOverworldWaterPolicyR38.allowsNewWater(64,64,true),"R396 equality fix lost");
        need(cases.size()==10,"Incomplete fixture matrix");
    }
    private synchronized void finish(Throwable error){
        if(finished)return;finished=true;JsonObject r=new JsonObject();r.addProperty("pass",error==null);r.addProperty("nonce",nonce);r.addProperty("seed",-4651369264513492755L);r.add("cases",cases);
        r.addProperty("scope","In-memory real ProtoChunks; synthetic cache-holder adapters. Calls actual compiled closure and mine guard; not live scheduler or natural cave acceptance.");
        if(error!=null){r.addProperty("error",error.toString());error.printStackTrace();}
        try{getDataFolder().mkdirs();Files.writeString(getDataFolder().toPath().resolve("result.json"),new GsonBuilder().setPrettyPrinting().create().toJson(r));}
        catch(Exception failure){failure.printStackTrace();error=failure;}
        getLogger().info("R40 FIXTURE "+(error==null?"PASS ":"FAIL ")+nonce);
    }
}
