import com.google.gson.*;
import java.lang.reflect.Method;
import java.nio.file.Files;
import java.util.*;
import org.bukkit.Bukkit;
import org.bukkit.World;
import org.bukkit.NamespacedKey;
import org.bukkit.craftbukkit.CraftWorld;
import org.bukkit.event.*;
import org.bukkit.event.server.ServerLoadEvent;
import org.bukkit.persistence.PersistentDataType;
import org.bukkit.plugin.java.JavaPlugin;
import net.minecraft.core.BlockPos;
import net.minecraft.tags.FluidTags;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.LiquidBlock;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.chunk.ChunkAccess;
import net.minecraft.world.level.chunk.NeverOverworldDryMinesR12;
import net.minecraft.world.level.chunk.NeverOverworldWaterPolicyR38;
import net.minecraft.world.level.levelgen.Heightmap;

/** Synthetic per-piece geometry in NEW isolated CI worlds only. Not a natural
 * mineshaft generation test. Reload validates persisted PDC before any fixture
 * writes. Reflection invokes the existing mask builder only inside this QA.
 */
public final class R399MineQa extends JavaPlugin implements Listener {
    private static final NamespacedKey KEY=new NamespacedKey("neverfolia","dry_mines_r12");
    private final boolean fixed=Boolean.getBoolean("neverfolia.qaFixedMineGuard");
    private final boolean reload=Boolean.getBoolean("neverfolia.qaMineReload");
    private final String nonce=System.getProperty("neverfolia.qaNonce","");
    private final JsonArray rows=new JsonArray();
    private boolean started,finished;
    private World world;
    private int index;
    private final int[][] chunks={{0,0},{-1,-1}};
    private String prefix="";
    @Override public void onEnable(){Bukkit.getPluginManager().registerEvents(this,this);}
    @EventHandler public void loaded(ServerLoadEvent event){
        if(started)return;started=true;
        try{
            require(!nonce.isEmpty(),"Missing current-process nonce");
            world=Bukkit.getWorlds().stream().filter(w->w.getEnvironment()==World.Environment.NORMAL).findFirst().orElseThrow();
            require(world.getSeed()==-4651369264513492755L,"Wrong actual seed");
            next();
        }catch(Throwable t){finish(t);}
    }
    private void next(){
        if(index==chunks.length){finish(null);return;}
        int cx=chunks[index][0],cz=chunks[index][1];
        world.getChunkAtAsync(cx,cz,true).whenComplete((loaded,error)->{
            if(error!=null){finish(error);return;}
            Bukkit.getRegionScheduler().execute(this,world,cx,cz,()->{
                try{
                    BlockPos p=new BlockPos(cx*16+3,64,cz*16+3);
                    ChunkAccess chunk=((CraftWorld)world).getHandle().getChunkAt(p);
                    prefix=cx+","+cz+":";
                    exercise(chunk);
                    index++;
                    Bukkit.getGlobalRegionScheduler().execute(this,()->next());
                }catch(Throwable t){finish(t);}
            });
        });
    }
    private int[] geometry(ChunkAccess c){
        int x=c.getPos().getMinBlockX(),z=c.getPos().getMinBlockZ();
        return new int[]{1,5, x+2,60,z+2,x+4,64,z+4, x+10,60,z+2,x+12,64,z+4,
            x+14,63,z+10,x+19,66,z+12, x+6,127,z+6,x+8,130,z+8,
            x+6,-512,z+6,x+8,-510,z+8};
    }
    private BlockPos pos(ChunkAccess c,int x,int y,int z){return new BlockPos(c.getPos().getMinBlockX()+x,y,c.getPos().getMinBlockZ()+z);}
    private NeverOverworldDryMinesR12.Mask mask(ChunkAccess c)throws Exception{
        Method m=NeverOverworldDryMinesR12.class.getDeclaredMethod("mask",ChunkAccess.class);
        m.setAccessible(true);
        return (NeverOverworldDryMinesR12.Mask)m.invoke(null,c);
    }
    private boolean expected(ChunkAccess c,int[] g,BlockPos p){
        int x=p.getX()-c.getPos().getMinBlockX(),z=p.getZ()-c.getPos().getMinBlockZ(),y=p.getY();
        if(x<0||x>15||z<0||z>15||y<=-512||y>128)return false;
        for(int i=2;i<g.length;i+=6)if(p.getX()>=g[i]&&y>=g[i+1]&&p.getZ()>=g[i+2]
            &&p.getX()<=g[i+3]&&y<=g[i+4]&&p.getZ()<=g[i+5])return true;
        return false;
    }
    private void row(String name,Object actual,Object expected){
        JsonObject r=new JsonObject();r.addProperty("name",prefix+name);
        r.addProperty("actual",String.valueOf(actual));r.addProperty("expected",String.valueOf(expected));
        boolean pass=Objects.equals(actual,expected);r.addProperty("pass",pass);rows.add(r);
        require(pass,name+": expected "+expected+", got "+actual);
    }
    private void membership(ChunkAccess c,boolean cached)throws Exception{
        c.neverOverworldDryMineMaskR12=cached?mask(c):null;
        int[][] points={{3,62,3},{11,62,3},{7,62,3},{1,62,3},{15,64,11},{16,64,11},
            {7,128,7},{7,129,7},{7,-512,7},{7,-511,7}};
        String[] names={"left_piece","right_piece","gap","shell_not_interior","chunk_face",
            "foreign_chunk","sea_bound","above_sea_bound","bedrock","above_bedrock"};
        boolean[] valid={true,true,false,false,true,false,true,false,false,true};
        for(int i=0;i<points.length;i++){
            int[] q=points[i];
            row((cached?"cached_":"released_")+names[i],
                NeverOverworldDryMinesR12.protectedCell(c,pos(c,q[0],q[1],q[2])),valid[i]&&(cached||fixed));
        }
    }
    private void exercise(ChunkAccess c)throws Exception{
        require(c.getMinY()==-512&&c.getHeight()==1024,"Wrong world envelope");
        int[] g=geometry(c);BlockPos marker=pos(c,0,500,0);
        if(reload){
            row("serialized_geometry_roundtrip",Arrays.equals(g,c.persistentDataContainer.get(KEY,PersistentDataType.INTEGER_ARRAY)),true);
            row("reload_cache_initially_null",c.neverOverworldDryMineMaskR12==null,true);
            row("saved_marker_roundtrip",c.getBlockState(marker).is(Blocks.GOLD_BLOCK),true);
        }else{
            c.persistentDataContainer.set(KEY,PersistentDataType.INTEGER_ARRAY,g);
            c.neverOverworldDryMineMaskR12=null;
        }
        membership(c,true);membership(c,false);
        int[] ys={-512,-511,-510,59,60,62,63,64,65,66,67,126,127,128,129,130,511,512};
        long startedAt=System.nanoTime();int comparisons=0,protectedCount=0;
        for(boolean cached:new boolean[]{true,false}){
            c.neverOverworldDryMineMaskR12=cached?mask(c):null;
            for(int y:ys)for(int z=-1;z<=16;z++)for(int x=-1;x<=16;x++){
                BlockPos p=pos(c,x,y,z);boolean want=expected(c,g,p)&&(cached||fixed);
                require(NeverOverworldDryMinesR12.protectedCell(c,p)==want,"Membership mismatch at "+p);
                if(want)protectedCount++;comparisons++;
            }
        }
        row("membership_comparisons",comparisons,11664);
        JsonObject stats=new JsonObject();stats.addProperty("name",prefix+"timing_observation");stats.addProperty("pass",true);
        stats.addProperty("comparisons",comparisons);stats.addProperty("positive_answers",protectedCount);
        stats.addProperty("elapsed_ms",(System.nanoTime()-startedAt)/1_000_000.0);rows.add(stats);
        c.neverOverworldDryMineMaskR12=null;
        if(!reload){
            int[][] invalid={ {2,1,0,60,0,1,64,1}, {1,1}, {1,-1},
                {1,2,g[2],g[3],g[4],g[5],g[6],g[7],10,60,10,5,64,11}};
            for(int n=0;n<invalid.length;n++){
                c.persistentDataContainer.set(KEY,PersistentDataType.INTEGER_ARRAY,invalid[n]);
                boolean threw=false;
                try{NeverOverworldDryMinesR12.protectedCell(c,pos(c,3,62,3));}
                catch(IllegalStateException expected){threw=true;}
                row("invalid_metadata_"+n,threw,fixed);
            }
            c.persistentDataContainer.remove(KEY);
            row("no_geometry",NeverOverworldDryMinesR12.protectedCell(c,pos(c,3,62,3)),false);
            c.persistentDataContainer.set(KEY,PersistentDataType.INTEGER_ARRAY,g);
            BlockPos p=prepareSnow(c,3,3);
            c.neverOverworldDryMineMaskR12=mask(c);
            row("policy_cached_inside",replacement(c,p),Blocks.AIR.defaultBlockState().toString());
            c.neverOverworldDryMineMaskR12=null;
            row("policy_released_inside",replacement(c,p),(fixed?Blocks.AIR:Blocks.WATER).defaultBlockState().toString());
            BlockPos outside=prepareSnow(c,7,3);
            row("r396_snow_fix_outside",replacement(c,outside),Blocks.WATER.defaultBlockState().toString());
            BlockState flow=Blocks.WATER.defaultBlockState().setValue(LiquidBlock.LEVEL,5);
            row("existing_fluid_preserved",NeverOverworldWaterPolicyR38.afterPlantRemoval(c,p,flow,false).toString(),flow.getFluidState().createLegacyBlock().toString());
            // Persist fixture identity so restart cannot rebuild missing metadata and pass.
            c.setBlockState(marker,Blocks.GOLD_BLOCK.defaultBlockState(),0);
        }
        row("geometry_unchanged_by_queries",Arrays.equals(g,c.persistentDataContainer.get(KEY,PersistentDataType.INTEGER_ARRAY)),true);
        row("no_cache_repopulation",c.neverOverworldDryMineMaskR12==null,true);
    }
    private BlockPos prepareSnow(ChunkAccess c,int x,int z){
        for(int y=-511;y<512;y++)c.setBlockState(pos(c,x,y,z),Blocks.AIR.defaultBlockState(),0);
        BlockPos p=pos(c,x,64,z);
        c.setBlockState(pos(c,x,60,z),Blocks.STONE.defaultBlockState(),0);
        c.setBlockState(p,Blocks.SNOW_BLOCK.defaultBlockState(),0);
        c.setBlockState(p.east(),Blocks.WATER.defaultBlockState(),0);
        Heightmap.primeHeightmaps(c,EnumSet.of(Heightmap.Types.OCEAN_FLOOR_WG));
        require(c.getHeight(Heightmap.Types.OCEAN_FLOOR_WG,x,z)==64,"Snow height fixture failed");
        require(c.getBlockState(p.east()).getFluidState().is(FluidTags.WATER),"Missing water contact");
        return p;
    }
    private String replacement(ChunkAccess c,BlockPos p){
        return NeverOverworldWaterPolicyR38.afterPlantRemoval(c,p,c.getBlockState(p),true).toString();
    }
    private static void require(boolean ok,String msg){if(!ok)throw new AssertionError(msg);}
    private synchronized void finish(Throwable failure){
        if(finished)return;finished=true;
        JsonObject r=new JsonObject();r.addProperty("pass",failure==null);r.addProperty("fixed",fixed);r.addProperty("reload",reload);
        r.addProperty("nonce",nonce);r.addProperty("seed",world==null?0:world.getSeed());r.addProperty("completed_chunks",index);
        r.addProperty("scope","Synthetic persisted geometry, real server chunks/masks/heightmap, positive and negative chunk coordinates. Not natural mineshaft or ocean completeness acceptance.");r.add("cases",rows);
        if(failure!=null){r.addProperty("error",failure.toString());failure.printStackTrace();}
        try{getDataFolder().mkdirs();Files.writeString(getDataFolder().toPath().resolve("result.json"),new GsonBuilder().setPrettyPrinting().create().toJson(r));}
        catch(Exception e){failure=e;e.printStackTrace();}
        getLogger().info("R399 MINE QA "+(failure==null?"PASS":"FAIL")+" "+nonce);
    }
}
