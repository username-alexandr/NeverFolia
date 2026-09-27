import com.google.gson.*;
import java.lang.reflect.*;
import java.nio.ByteBuffer;
import java.nio.file.Files;
import java.security.MessageDigest;
import java.util.*;
import net.minecraft.core.BlockPos;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.level.ChunkPos;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.LiquidBlock;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.properties.BlockStateProperties;
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

/** Isolated CI only. Every edited chunk is a detached ProtoChunk, never a live
 * player chunk. Reflection only discovers the actual palette factory constructor
 * input; the production algorithm and block/metadata APIs are not mocked.
 */
public final class R3910CavityQa extends JavaPlugin implements Listener {
    private final JsonArray rows=new JsonArray();
    private boolean started,finished;
    private String factorySource="";
    @Override public void onEnable(){Bukkit.getPluginManager().registerEvents(this,this);}
    @EventHandler public void loaded(ServerLoadEvent e) {
        if(started)return;started=true;
        try {
            World w=Bukkit.getWorlds().stream().filter(x->x.getEnvironment()==World.Environment.NORMAL).findFirst().orElseThrow();
            require(w.getSeed()==-4651369264513492755L,"Wrong seed");
            w.getChunkAtAsync(0,0,true).whenComplete((unused,error)-> {
                if(error!=null){finish(error);return;}
                Bukkit.getRegionScheduler().execute(this,w,0,0,()-> {
                    try {
                        ServerLevel world=((CraftWorld)w).getHandle();
                        ChunkAccess reference=world.getChunkAt(new BlockPos(8,64,8));
                        Object factory=factory(world,reference);
                        for(int[] center:new int[][]{{0,0},{-1700,-770}}) {
                            exercise(world,factory,center[0],center[1]);
                        }
                        require(rows.size()>=30,"Incomplete cavity coverage");
                        finish(null);
                    } catch(Throwable failure){finish(failure);}
                });
            });
        } catch(Throwable failure){finish(failure);}
    }
    private Constructor<?> constructor() {
        List<Constructor<?>> found=new ArrayList<>();
        for(Constructor<?> c:ProtoChunk.class.getConstructors())
            if(c.getParameterCount()==5 && c.getParameterTypes()[0]==ChunkPos.class
                && c.getParameterTypes()[1]==UpgradeData.class)found.add(c);
        require(found.size()==1,"Expected one inspected ProtoChunk constructor");return found.getFirst();
    }
    private Object factory(ServerLevel world,ChunkAccess reference)throws Exception {
        Class<?> type=constructor().getParameterTypes()[3];
        for(Object source:new Object[]{world,reference}) {
            for(Method m:source.getClass().getMethods()) {
                if(m.getParameterCount()==0 && m.getReturnType()==type && !Modifier.isStatic(m.getModifiers())) {
                    Object value=m.invoke(source);if(value!=null){factorySource=m.toString();return value;}
                }
            }
            for(Class<?> c=source.getClass();c!=null;c=c.getSuperclass())for(Field f:c.getDeclaredFields()) {
                if(f.getType()==type && !Modifier.isStatic(f.getModifiers())) {
                    f.setAccessible(true);Object value=f.get(source);if(value!=null){factorySource=f.toString();return value;}
                }
            }
        }
        for(Method m:type.getMethods()) {
            if(Modifier.isStatic(m.getModifiers()) && m.getReturnType()==type && m.getParameterCount()==1
                && m.getParameterTypes()[0].isInstance(world.registryAccess())) {
                Object value=m.invoke(null,world.registryAccess());if(value!=null){factorySource=m.toString();return value;}
            }
        }
        throw new AssertionError("No real palette factory available for "+type.getName());
    }
    private ChunkAccess[] window(ServerLevel world,Object factory,int cx,int cz,boolean noSky)throws Exception {
        ChunkAccess[] chunks=new ChunkAccess[9];
        for(int tile=0;tile<9;tile++) {
            ProtoChunk c=(ProtoChunk)constructor().newInstance(new ChunkPos(cx+tile%3-1,cz+tile/3-1),UpgradeData.EMPTY,world,factory,null);
            chunks[tile]=c;
            for(int z=0;z<16;z++)for(int x=0;x<16;x++) {
                put(c,x,0,z,Blocks.STONE.defaultBlockState());
                if(tile==4)put(c,x,90,z,Blocks.STONE.defaultBlockState());
                if(noSky)put(c,x,130,z,Blocks.STONE.defaultBlockState());
            }
            c.setPersistedStatus(ChunkStatus.FEATURES);
        }
        return chunks;
    }
    private void exercise(ServerLevel world,Object factory,int cx,int cz)throws Exception {
        String prefix=cx+","+cz+":";
        ChunkAccess[] chunks=window(world,factory,cx,cz,false);ChunkAccess owner=chunks[4];
        for(int y=39;y<=41;y++)for(int z=7;z<=9;z++)for(int x=7;x<=9;x++)put(owner,x,y,z,Blocks.STONE.defaultBlockState());
        put(owner,8,40,8,Blocks.AIR.defaultBlockState());
        put(owner,3,60,3,Blocks.LAVA.defaultBlockState());
        put(owner,5,60,5,Blocks.BLUE_ICE.defaultBlockState());
        BlockState flowing=Blocks.WATER.defaultBlockState().setValue(LiquidBlock.LEVEL,5);
        BlockState falling=Blocks.WATER.defaultBlockState().setValue(LiquidBlock.LEVEL,8);
        BlockState slab=Blocks.OAK_SLAB.defaultBlockState().setValue(BlockStateProperties.WATERLOGGED,true);
        put(owner,6,55,6,flowing);put(owner,7,55,6,falling);put(owner,8,55,6,slab);
        int bx=owner.getPos().getMinBlockX(),bz=owner.getPos().getMinBlockZ();
        owner.persistentDataContainer.set(new NamespacedKey("neverfolia","dry_mines_r12"),PersistentDataType.INTEGER_ARRAY,
            new int[]{1,1,bx+10,50,bz+10,bx+12,52,bz+12});
        owner.neverOverworldDryMineMaskR12=null;
        put(owner,11,51,11,Blocks.RAIL.defaultBlockState());
        // Protected geometry must not hide a lava block from adjacency checks.
        put(owner,9,50,10,Blocks.LAVA.defaultBlockState());
        List<String> neighbours=new ArrayList<>();for(int i=0;i<9;i++)if(i!=4)neighbours.add(hash(chunks[i]));
        int added=NeverOverworldOceanClosureR3910.closePrepared(owner,chunks);
        check(prefix+"positive_effect",added>0);
        for(int[] p:new int[][]{{1,64,8},{14,64,8},{8,64,1},{8,64,14}})
            check(prefix+"under_roof_"+Arrays.toString(p),get(owner,p[0],p[1],p[2]).is(Blocks.WATER));
        check(prefix+"sealed_room_dry",get(owner,8,40,8).isAir());
        check(prefix+"mine_inside_dry",get(owner,10,51,10).isAir());
        check(prefix+"mine_shell_dry",get(owner,9,51,10).isAir());
        check(prefix+"mine_rail_preserved",get(owner,11,51,11).is(Blocks.RAIL));
        check(prefix+"mine_guard_after_release",NeverOverworldDryMinesR12.protectedCell(owner,new BlockPos(bx+10,51,bz+10)));
        check(prefix+"protected_lava_preserved",get(owner,9,50,10).is(Blocks.LAVA));
        check(prefix+"protected_lava_outside_neighbour_dry",get(owner,8,50,10).isAir());
        for(int[] p:new int[][]{{2,60,3},{4,60,3},{3,59,3},{3,61,3},{3,60,2},{3,60,4}})
            check(prefix+"lava_barrier_"+Arrays.toString(p),get(owner,p[0],p[1],p[2]).isAir());
        check(prefix+"lava_preserved",get(owner,3,60,3).is(Blocks.LAVA));
        check(prefix+"ice_preserved",get(owner,5,60,5).is(Blocks.BLUE_ICE));
        check(prefix+"flowing_preserved",get(owner,6,55,6)==flowing);
        check(prefix+"falling_preserved",get(owner,7,55,6)==falling);
        check(prefix+"waterlogged_slab_preserved",get(owner,8,55,6)==slab);
        int j=0;for(int i=0;i<9;i++)if(i!=4)check(prefix+"neighbour_unchanged_"+i,neighbours.get(j++).equals(hash(chunks[i])));
        check(prefix+"idempotent",NeverOverworldOceanClosureR3910.closePrepared(owner,chunks)==0);
        ChunkAccess[] sealed=window(world,factory,cx,cz,true);
        put(sealed[4],8,64,8,Blocks.WATER.defaultBlockState());
        check(prefix+"underground_water_not_ocean_seed",NeverOverworldOceanClosureR3910.closePrepared(sealed[4],sealed)==0);
        check(prefix+"unconnected_air_dry",get(sealed[4],9,64,8).isAir());
        for(int i=0;i<9;i++)if(i!=4)sealed[i]=null;
        check(prefix+"unknown_neighbours_not_seeds",NeverOverworldOceanClosureR3910.closePrepared(sealed[4],sealed)==0);
        ((ProtoChunk)sealed[4]).setPersistedStatus(ChunkStatus.FULL);
        check(prefix+"full_chunk_skipped",NeverOverworldOceanClosureR3910.closePrepared(sealed[4],sealed)==0);
        check(prefix+"full_chunk_still_dry",get(sealed[4],9,64,8).isAir());
    }
    private static void put(ChunkAccess c,int x,int y,int z,BlockState state){c.setBlockState(new BlockPos(c.getPos().getMinBlockX()+x,y,c.getPos().getMinBlockZ()+z),state,0);}
    private static BlockState get(ChunkAccess c,int x,int y,int z){return c.getBlockState(new BlockPos(c.getPos().getMinBlockX()+x,y,c.getPos().getMinBlockZ()+z));}
    private static String hash(ChunkAccess c)throws Exception {
        ByteBuffer bytes=ByteBuffer.allocate(640*256*4);BlockPos.MutableBlockPos p=new BlockPos.MutableBlockPos();
        int bx=c.getPos().getMinBlockX(),bz=c.getPos().getMinBlockZ();
        for(int y=-511;y<=128;y++)for(int z=0;z<16;z++)for(int x=0;x<16;x++) {
            p.set(bx+x,y,bz+z);bytes.putInt(Block.BLOCK_STATE_REGISTRY.getId(c.getBlockState(p)));
        }
        return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes.array()));
    }
    private void check(String name,boolean value) {
        JsonObject row=new JsonObject();row.addProperty("name",name);row.addProperty("pass",value);rows.add(row);require(value,name);
    }
    private static void require(boolean value,String message){if(!value)throw new AssertionError(message);}
    private synchronized void finish(Throwable failure) {
        if(finished)return;finished=true;JsonObject out=new JsonObject();out.addProperty("pass",failure==null);
        out.addProperty("nonce",System.getProperty("neverfolia.qaNonce",""));out.addProperty("factory_source",factorySource);
        out.addProperty("scope","Detached real ProtoChunks only; under-roof opening, sealed room, persisted per-piece mine envelope, lava and native fluid preservation; not all natural cavities");
        out.add("cases",rows);if(failure!=null){out.addProperty("error",failure.toString());failure.printStackTrace();}
        try {getDataFolder().mkdirs();Files.writeString(getDataFolder().toPath().resolve("result.json"),new GsonBuilder().setPrettyPrinting().create().toJson(out));}
        catch(Exception error){error.printStackTrace();failure=error;}
        getLogger().info("R3910 CAVITY QA "+(failure==null?"PASS":"FAIL"));
    }
}
