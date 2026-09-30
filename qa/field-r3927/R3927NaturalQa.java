import com.google.gson.*;
import java.nio.file.Files;
import java.util.*;
import org.bukkit.*;
import org.bukkit.block.data.Levelled;
import org.bukkit.event.*;
import org.bukkit.event.server.ServerLoadEvent;
import org.bukkit.plugin.java.JavaPlugin;

/** Generates fixed natural chunks only; never writes blocks. */
public final class R3927NaturalQa extends JavaPlugin implements Listener {
    private World world;
    private final List<int[]> targets=new ArrayList<>();
    private final JsonArray rows=new JsonArray();
    private int index;
    private boolean started,finished;
    private final String nonce=System.getProperty("neverfolia.qaNonce","");
    private static final int LOW=-511,HIGH=128;

    @Override public void onEnable(){Bukkit.getPluginManager().registerEvents(this,this);}
    @EventHandler public void loaded(ServerLoadEvent event) {
        if(started)return;started=true;
        try {
            world=Bukkit.getWorlds().stream().filter(w->w.getEnvironment()==World.Environment.NORMAL).findFirst().orElseThrow();
            if(world.getSeed()!=-4651369264513492755L)throw new AssertionError("Wrong seed");
            int[][] centers={{7,1},{1,-4},{-197,-217},{-169,-250},{-189,-223},{-1699,-769}};
            TreeMap<String,int[]> selected=new TreeMap<>();
            for(int[] c:centers)for(int dz=-1;dz<=1;dz++)for(int dx=-1;dx<=1;dx++) {
                int cx=c[0]+dx,cz=c[1]+dz;selected.put(cx+","+cz,new int[]{cx,cz});
            }
            targets.addAll(selected.values());
            if(targets.size()!=54)throw new AssertionError("Wrong target count");
            Bukkit.getGlobalRegionScheduler().execute(this,this::next);
        } catch(Throwable error){finish(error);}
    }

    private void next() {
        if(finished)return;
        if(index==targets.size()){finish(null);return;}
        int[] t=targets.get(index);int cx=t[0],cz=t[1];
        world.getChunkAtAsync(cx,cz,true).whenComplete((chunk,error)->{
            if(error!=null){finish(error);return;}
            Bukkit.getRegionScheduler().execute(this,world,cx,cz,()->{
                try {
                    ChunkSnapshot s=chunk.getChunkSnapshot(false,true,false);
                    rows.add(sample(s,cx,cz));index++;
                    getLogger().info("R3927 SAMPLE "+index+"/"+targets.size()+" "+cx+","+cz);
                    Bukkit.getGlobalRegionScheduler().execute(this,this::next);
                } catch(Throwable failure){finish(failure);}
            });
        });
    }

    private static JsonObject sample(ChunkSnapshot s,int cx,int cz) {
        JsonObject row=new JsonObject();JsonArray examples=new JsonArray();
        int air=0,isolated=0,water=0;
        for(int y=LOW;y<=HIGH;y++)for(int z=0;z<16;z++)for(int x=0;x<16;x++) {
            Material type=s.getBlockType(x,y,z);
            if(type.isAir())air++;
            if(aquatic(type))water++;
            if(type.isAir()&&x>0&&x<15&&z>0&&z<15&&y>LOW&&y<HIGH) {
                boolean surrounded=aquatic(s.getBlockType(x-1,y,z))&&aquatic(s.getBlockType(x+1,y,z))
                    &&aquatic(s.getBlockType(x,y-1,z))&&aquatic(s.getBlockType(x,y+1,z))
                    &&aquatic(s.getBlockType(x,y,z-1))&&aquatic(s.getBlockType(x,y,z+1));
                if(surrounded) {
                    isolated++;
                    if(examples.size()<12) {
                        JsonObject p=new JsonObject();p.addProperty("x",cx*16+x);p.addProperty("y",y);p.addProperty("z",cz*16+z);examples.add(p);
                    }
                }
            }
        }
        row.addProperty("chunk_x",cx);row.addProperty("chunk_z",cz);
        row.addProperty("air_blocks",air);row.addProperty("aquatic_blocks",water);
        row.addProperty("isolated_air",isolated);row.add("isolated_air_examples",examples);
        return row;
    }

    private static boolean aquatic(Material t) {
        return t==Material.WATER||t==Material.BUBBLE_COLUMN||t==Material.KELP||t==Material.KELP_PLANT
            ||t==Material.SEAGRASS||t==Material.TALL_SEAGRASS;
    }

    private synchronized void finish(Throwable error) {
        if(finished)return;finished=true;
        JsonObject r=new JsonObject();r.addProperty("pass",error==null);
        r.addProperty("nonce",nonce);r.addProperty("seed",world==null?0:world.getSeed());
        r.addProperty("completed_chunks",rows.size());r.add("chunks",rows);
        if(error!=null){r.addProperty("error",error.toString());error.printStackTrace();}
        try {getDataFolder().mkdirs();Files.writeString(getDataFolder().toPath().resolve("result.json"),new GsonBuilder().setPrettyPrinting().create().toJson(r));}
        catch(Exception failure){failure.printStackTrace();error=failure;}
        getLogger().info("R3927 NATURAL QA "+(error==null?"PASS ":"FAIL ")+nonce);
    }
}
