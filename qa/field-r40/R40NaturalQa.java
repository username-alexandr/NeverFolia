import com.google.gson.*;
import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.*;
import org.bukkit.*;
import org.bukkit.craftbukkit.CraftWorld;
import org.bukkit.event.*;
import org.bukkit.event.server.ServerLoadEvent;
import org.bukkit.persistence.PersistentDataType;
import org.bukkit.plugin.java.JavaPlugin;
import net.minecraft.core.BlockPos;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.LiquidBlock;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.chunk.ChunkAccess;

/** Read-only observation in a fresh isolated CI world. Never installs fixtures. */
public final class R40NaturalQa extends JavaPlugin implements Listener {
    private World world;
    private final List<int[]> targets=new ArrayList<>();
    private final JsonArray rows=new JsonArray();
    private int next;
    private boolean started,finished;
    private final String nonce=System.getProperty("neverfolia.qaNonce","");
    private final boolean enabled=Boolean.getBoolean("neverfolia.r40Ocean");
    private final boolean reverse=Boolean.getBoolean("neverfolia.qaReverse");
    @Override public void onEnable(){Bukkit.getPluginManager().registerEvents(this,this);}
    @EventHandler public void loaded(ServerLoadEvent event) {
        if(started)return;started=true;
        try {
            if(nonce.length()<16)throw new AssertionError("Missing current-process identity");
            world=Bukkit.getWorlds().stream().filter(w->w.getEnvironment()==World.Environment.NORMAL).findFirst().orElseThrow();
            if(world.getSeed()!=-4651369264513492755L)throw new AssertionError("Wrong actual seed");
            int[][] centers={{7,1},{1,-4},{-197,-217},{-169,-250},{-189,-223},{-1699,-769},{-202,-213}};
            TreeMap<String,int[]> sorted=new TreeMap<>();
            for(int[] c:centers)for(int dz=-1;dz<=1;dz++)for(int dx=-1;dx<=1;dx++)sorted.put((c[0]+dx)+","+(c[1]+dz),new int[]{c[0]+dx,c[1]+dz});
            targets.addAll(sorted.values());if(reverse)Collections.reverse(targets);
            if(targets.size()!=63)throw new AssertionError("Invalid target set");
            Bukkit.getGlobalRegionScheduler().execute(this,()->advance());
        }catch(Throwable failure){finish(failure);}
    }
    private void advance() {
        if(finished)return;if(next==targets.size()){finish(null);return;}
        int[] p=targets.get(next);int cx=p[0],cz=p[1];
        world.getChunkAtAsync(cx,cz,true).whenComplete((chunk,failure)->{
            if(failure!=null){finish(failure);return;}
            Bukkit.getRegionScheduler().execute(this,world,cx,cz,()->{
                try {
                    ChunkAccess actual=((CraftWorld)world).getHandle().getChunkAt(new BlockPos(cx*16,0,cz*16));
                    rows.add(sample(actual,cx,cz));next++;
                    getLogger().info("R40 SAMPLE "+next+"/"+targets.size()+" "+cx+","+cz);
                    Bukkit.getGlobalRegionScheduler().execute(this,()->advance());
                }catch(Throwable error){finish(error);}
            });
        });
    }
    private JsonObject sample(ChunkAccess chunk,int cx,int cz)throws Exception {
        JsonObject row=new JsonObject(),counts=new JsonObject();Map<String,Integer> types=new TreeMap<>();
        IdentityHashMap<BlockState,byte[]> strings=new IdentityHashMap<>();MessageDigest full=MessageDigest.getInstance("SHA-256");
        byte[] water=new byte[640*256];BlockPos.MutableBlockPos pos=new BlockPos.MutableBlockPos();
        JsonArray iceExamples=new JsonArray(),airExamples=new JsonArray();int isolatedAir=0,isolatedIce=0;
        for(int y=-512;y<=511;y++)for(int z=0;z<16;z++)for(int x=0;x<16;x++) {
            pos.set(cx*16+x,y,cz*16+z);BlockState state=chunk.getBlockState(pos);
            full.update(strings.computeIfAbsent(state,s->(s.toString()+"\n").getBytes(StandardCharsets.UTF_8)));
            if(y< -511||y>128)continue;
            String name=net.minecraft.core.registries.BuiltInRegistries.BLOCK.getKey(state.getBlock()).toString();types.merge(name,1,Integer::sum);
            int k=((y+511)<<8)|(z<<4)|x;
            if(state.is(Blocks.WATER))water[k]=(byte)(1+state.getValue(LiquidBlock.LEVEL));else if(aquatic(state))water[k]=1;
            boolean ice=state.is(Blocks.ICE)||state.is(Blocks.PACKED_ICE)||state.is(Blocks.BLUE_ICE)||state.is(Blocks.FROSTED_ICE);
            if((state.isAir()||ice)&&x>0&&x<15&&z>0&&z<15&&y> -511&&y<128) {
                BlockPos here=pos.immutable();boolean surrounded=true;
                for(BlockPos other:List.of(here.east(),here.west(),here.above(),here.below(),here.north(),here.south()))if(!aquatic(chunk.getBlockState(other))){surrounded=false;break;}
                if(surrounded){JsonObject e=new JsonObject();e.addProperty("x",here.getX());e.addProperty("y",y);e.addProperty("z",here.getZ());e.addProperty("block",name);
                    if(ice){isolatedIce++;if(iceExamples.size()<24)iceExamples.add(e);}else{isolatedAir++;if(airExamples.size()<24)airExamples.add(e);}}
            }
        }
        types.forEach(counts::addProperty);row.addProperty("chunk_x",cx);row.addProperty("chunk_z",cz);row.add("block_counts",counts);
        row.addProperty("water_sha256",HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(water)));
        row.addProperty("full_state_sha256",HexFormat.of().formatHex(full.digest()));
        row.addProperty("single_air_with_six_aquatic_neighbours",isolatedAir);row.add("air_examples",airExamples);
        row.addProperty("single_ice_with_six_aquatic_neighbours",isolatedIce);row.add("ice_examples",iceExamples);
        byte[] snapshot=chunk.persistentDataContainer.get(new NamespacedKey("neverfolia","ocean_snapshot_r40_v1"),PersistentDataType.BYTE_ARRAY);
        row.addProperty("snapshot_bytes",snapshot==null?0:snapshot.length);
        boolean done=chunk.persistentDataContainer.has(new NamespacedKey("neverfolia","ocean_done_r40_v1"),PersistentDataType.BYTE);row.addProperty("closure_done",done);
        if(enabled&&(snapshot==null||!done))throw new AssertionError("Incomplete R40 stage at "+cx+","+cz);
        return row;
    }
    private static boolean aquatic(BlockState s){return s.is(Blocks.WATER)||s.is(Blocks.BUBBLE_COLUMN)||s.is(Blocks.KELP)||s.is(Blocks.KELP_PLANT)||s.is(Blocks.SEAGRASS)||s.is(Blocks.TALL_SEAGRASS);}
    private synchronized void finish(Throwable failure) {
        if(finished)return;finished=true;JsonObject result=new JsonObject();result.addProperty("pass",failure==null);result.addProperty("nonce",nonce);
        result.addProperty("seed",world==null?0:world.getSeed());result.addProperty("enabled",enabled);result.addProperty("reverse",reverse);result.add("chunks",rows);
        if(world!=null){var level=((CraftWorld)world).getHandle();result.addProperty("level_sea_y",level.getSeaLevel());result.addProperty("generator_sea_y",level.getChunkSource().getGenerator().getSeaLevel());}
        if(failure!=null){result.addProperty("error",failure.toString());failure.printStackTrace();}
        try{getDataFolder().mkdirs();Files.writeString(getDataFolder().toPath().resolve("result.json"),new GsonBuilder().setPrettyPrinting().create().toJson(result));}
        catch(Exception e){e.printStackTrace();failure=e;}
        getLogger().info("R40 NATURAL QA "+(failure==null?"PASS":"FAIL")+" "+nonce);
    }
}
