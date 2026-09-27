import com.google.gson.*;
import java.lang.reflect.Method;
import java.nio.file.Files;
import org.bukkit.Bukkit;
import org.bukkit.World;
import org.bukkit.NamespacedKey;
import org.bukkit.craftbukkit.CraftWorld;
import org.bukkit.event.EventHandler;
import org.bukkit.event.Listener;
import org.bukkit.event.server.ServerLoadEvent;
import org.bukkit.persistence.PersistentDataType;
import org.bukkit.plugin.java.JavaPlugin;
import net.minecraft.core.BlockPos;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.LiquidBlock;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.chunk.ChunkAccess;
import net.minecraft.world.level.chunk.NeverOverworldDryMinesR12;
import net.minecraft.world.level.chunk.NeverOverworldOceanClosureR40;

/** Destructive SYNTHETIC fixture confined to a fresh CI world's region-owned
 * chunk. NEVER shipped in a user kit. Calls the exact private implementation
 * used by the live LIGHT hook; FULL suppression is separately asserted.
 * Eight unavailable neighbours remain UNKNOWN, rather than supplying fake water.
 */
public final class R40Fixture extends JavaPlugin implements Listener {
    private final JsonArray rows=new JsonArray();
    private final String nonce=System.getProperty("neverfolia.qaNonce","");
    private boolean started,finished;
    private World world;
    @Override public void onEnable(){Bukkit.getPluginManager().registerEvents(this,this);}
    @EventHandler public void loaded(ServerLoadEvent event){
        if(started)return;started=true;
        try {
            if(nonce.isEmpty())throw new IllegalStateException("Missing process nonce");
            world=Bukkit.getWorlds().stream().filter(w->w.getEnvironment()==World.Environment.NORMAL).findFirst().orElseThrow();
            check("actual_seed",world.getSeed()==-4651369264513492755L);
            world.getChunkAtAsync(0,0,true).whenComplete((loaded,error)->{
                if(error!=null){finish(error);return;}
                Bukkit.getRegionScheduler().execute(this,world,0,0,()->{
                    try{exercise(((CraftWorld)world).getHandle().getChunkAt(new BlockPos(8,72,8)));finish(null);}
                    catch(Throwable failure){finish(failure);}
                });
            });
        }catch(Throwable failure){finish(failure);}
    }
    private static BlockPos p(int x,int y,int z){return new BlockPos(x,y,z);}
    private static void set(ChunkAccess c,int x,int y,int z,BlockState state){c.setBlockState(p(x,y,z),state,0);}
    private static boolean is(ChunkAccess c,int x,int y,int z,net.minecraft.world.level.block.Block block){return c.getBlockState(p(x,y,z)).is(block);}
    private void check(String name,boolean pass){JsonObject row=new JsonObject();row.addProperty("name",name);row.addProperty("pass",pass);rows.add(row);if(!pass)throw new AssertionError(name);}
    private void exercise(ChunkAccess c)throws Exception {
        check("world_envelope",c.getMinY()==-512&&c.getHeight()==1024);
        check("full_chunk_not_regenerated",NeverOverworldOceanClosureR40.apply(((CraftWorld)world).getHandle(),null,c)==0);
        c.persistentDataContainer.remove(new NamespacedKey("neverfolia","dry_mines_r12"));c.neverOverworldDryMineMaskR12=null;
        BlockState stone=Blocks.STONE.defaultBlockState(),air=Blocks.AIR.defaultBlockState(),water=Blocks.WATER.defaultBlockState();
        for(int y=-511;y<512;y++)for(int z=0;z<16;z++)for(int x=0;x<16;x++)set(c,x,y,z,stone);
        for(int y=70;y<512;y++)set(c,2,y,2,y<=128?water:air);
        for(int x=3;x<=8;x++)set(c,x,72,2,air);
        for(int y=70;y<=73;y++)for(int z=2;z<=4;z++)for(int x=6;x<=8;x++)set(c,x,y,z,air);
        for(int y=70;y<=72;y++)for(int z=10;z<=12;z++)for(int x=10;x<=12;x++)set(c,x,y,z,air);
        for(int y=70;y<=73;y++)for(int z=5;z<=6;z++)for(int x=3;x<=4;x++)set(c,x,y,z,air);
        set(c,3,72,3,air);set(c,3,72,4,air);
        int[] geometry={1,1,3,70,5,4,73,6};
        c.persistentDataContainer.set(new NamespacedKey("neverfolia","dry_mines_r12"),PersistentDataType.INTEGER_ARRAY,geometry);
        set(c,7,71,2,Blocks.LAVA.defaultBlockState());set(c,6,70,3,Blocks.ICE.defaultBlockState());
        BlockState flow=water.setValue(LiquidBlock.LEVEL,5),fall=water.setValue(LiquidBlock.LEVEL,8);
        set(c,3,72,2,flow);set(c,4,72,2,fall);
        set(c,14,90,8,air);set(c,15,90,8,air);
        BlockState[] before=new BlockState[640*256];
        for(int y=-511;y<=128;y++)for(int z=0;z<16;z++)for(int x=0;x<16;x++)before[((y+511)<<8)|(z<<4)|x]=c.getBlockState(p(x,y,z));
        ChunkAccess[] witness=new ChunkAccess[9];witness[4]=c;
        Method method=NeverOverworldOceanClosureR40.class.getDeclaredMethod("close",ChunkAccess[].class);method.setAccessible(true);
        int added=(Integer)method.invoke(null,(Object)witness);
        check("positive_fill",added>0);
        check("side_path_under_solid_roof_filled",is(c,8,72,3,Blocks.WATER));
        check("roof_preserved",is(c,8,74,3,Blocks.STONE));
        check("sealed_cave_preserved",is(c,11,71,11,Blocks.AIR));
        check("persisted_mine_without_cache_protected",c.neverOverworldDryMineMaskR12==null&&NeverOverworldDryMinesR12.protectedCell(c,p(3,72,5)));
        check("mine_interior_stays_air",is(c,3,72,5,Blocks.AIR));
        check("lava_neighbour_stays_air",is(c,7,72,2,Blocks.AIR));
        check("lava_preserved",is(c,7,71,2,Blocks.LAVA));
        check("ice_preserved",is(c,6,70,3,Blocks.ICE));
        check("flowing_state_preserved",c.getBlockState(p(3,72,2))==flow);
        check("falling_state_preserved",c.getBlockState(p(4,72,2))==fall);
        check("unknown_neighbour_not_ocean_seed",is(c,15,90,8,Blocks.AIR));
        int actual=0;
        for(int y=-511;y<=128;y++)for(int z=0;z<16;z++)for(int x=0;x<16;x++){
            BlockState old=before[((y+511)<<8)|(z<<4)|x],now=c.getBlockState(p(x,y,z));
            if(old!=now){if(!old.isAir()||now!=water)throw new AssertionError("Non AIR -> source WATER change at "+p(x,y,z));actual++;}
        }
        check("entire_owner_delta_air_only",actual==added);
        check("metadata_unchanged",java.util.Arrays.equals(geometry,c.persistentDataContainer.get(new NamespacedKey("neverfolia","dry_mines_r12"),PersistentDataType.INTEGER_ARRAY)));
    }
    private synchronized void finish(Throwable failure){
        if(finished)return;finished=true;
        JsonObject result=new JsonObject();result.addProperty("pass",failure==null);result.addProperty("nonce",nonce);
        result.addProperty("seed",world==null?0:world.getSeed());result.add("cases",rows);
        result.addProperty("scope","Synthetic real-owner integration; private close implementation plus public FULL guard; not natural mineshaft or global ocean acceptance");
        if(failure!=null){result.addProperty("error",failure.toString());failure.printStackTrace();}
        try{getDataFolder().mkdirs();Files.writeString(getDataFolder().toPath().resolve("result.json"),new GsonBuilder().setPrettyPrinting().create().toJson(result));}
        catch(Exception error){failure=error;error.printStackTrace();}
        getLogger().info("R40 FIXTURE "+(failure==null?"PASS":"FAIL")+" "+nonce);
    }
}
