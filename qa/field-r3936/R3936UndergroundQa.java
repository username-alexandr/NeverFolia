import com.google.gson.*;
import java.nio.file.Files;
import java.util.*;
import org.bukkit.*;
import org.bukkit.event.*;
import org.bukkit.event.server.ServerLoadEvent;
import org.bukkit.generator.structure.GeneratedStructure;
import org.bukkit.plugin.java.JavaPlugin;
import org.bukkit.util.BoundingBox;

public final class R3936UndergroundQa extends JavaPlugin implements Listener {
    private World world;
    private final List<int[]> targets=new ArrayList<>();
    private final Map<String,JsonObject> found=new LinkedHashMap<>();
    private int index;
    private boolean started,finished;
    private final String nonce=System.getProperty("neverfolia.qaNonce","");

    private static final Set<String> CUSTOM=Set.of(
        "neverfolia:buried_sanctum",
        "neverfolia:abyssal_archive",
        "neverfolia:ancient_cistern",
        "neverfolia:collapsed_mine",
        "neverfolia:geode_vault",
        "neverfolia:flooded_ruins",
        "neverfolia:prospector_camp",
        "neverfolia:sealed_cache"
    );

    @Override public void onEnable(){Bukkit.getPluginManager().registerEvents(this,this);}

    @EventHandler public void loaded(ServerLoadEvent e){
        if(started)return;started=true;
        try{
            world=Bukkit.getWorlds().stream()
                .filter(w->w.getEnvironment()==World.Environment.NORMAL)
                .findFirst().orElseThrow();
            if(world.getSeed()!=-4651369264513492755L)throw new AssertionError("wrong seed");

            // Deterministic areas that already contain custom NeverOverworld
            // underground starts on this seed. X/Z placement is unchanged by
            // R39.36; only the vertical resolver changes.
            addArea(-206,-224,3);
            addArea(-216,-215,3);
            Bukkit.getGlobalRegionScheduler().execute(this,this::next);
        }catch(Throwable t){finish(t);}
    }

    private void addArea(int cx,int cz,int radius){
        for(int dz=-radius;dz<=radius;++dz)
            for(int dx=-radius;dx<=radius;++dx)
                targets.add(new int[]{cx+dx,cz+dz});
    }

    private void next(){
        if(finished)return;
        if(index==targets.size()){finish(null);return;}
        int[] t=targets.get(index);int cx=t[0],cz=t[1];
        world.getChunkAtAsync(cx,cz,true).whenComplete((chunk,error)->{
            if(error!=null){finish(error);return;}
            Bukkit.getRegionScheduler().execute(this,world,cx,cz,()->{
                try{
                    for(GeneratedStructure gs:chunk.getStructures()){
                        String id=gs.getStructure().getKey().toString();
                        if(!CUSTOM.contains(id)||found.containsKey(id))continue;
                        BoundingBox b=gs.getBoundingBox();
                        JsonObject row=new JsonObject();
                        row.addProperty("id",id);
                        row.addProperty("min_y",(int)Math.floor(b.getMinY()));
                        row.addProperty("max_y",(int)Math.floor(b.getMaxY()));
                        row.addProperty("seen_chunk_x",cx);
                        row.addProperty("seen_chunk_z",cz);
                        row.addProperty("pieces",gs.getPieces().size());
                        found.put(id,row);
                        getLogger().info("R3936 STRUCTURE "+id+" bbox="+b+" pieces="+gs.getPieces().size());
                    }
                    ++index;
                    Bukkit.getGlobalRegionScheduler().execute(this,this::next);
                }catch(Throwable x){finish(x);}
            });
        });
    }

    private synchronized void finish(Throwable error){
        if(finished)return;finished=true;
        if(error==null){
            if(found.size()<2)error=new AssertionError("too few deterministic custom structures found: "+found.keySet());
            for(JsonObject row:found.values()){
                int min=row.get("min_y").getAsInt();
                int max=row.get("max_y").getAsInt();
                if(min<-512||max>511){
                    error=new AssertionError("custom structure escaped dimension: "+row);
                    break;
                }
            }
        }

        JsonObject o=new JsonObject();
        o.addProperty("pass",error==null);
        o.addProperty("nonce",nonce);
        o.addProperty("seed",world==null?0:world.getSeed());
        o.addProperty("generated_chunks",index);
        JsonArray a=new JsonArray();
        for(JsonObject row:found.values())a.add(row);
        o.add("structures",a);
        if(error!=null){o.addProperty("error",error.toString());error.printStackTrace();}

        try{
            getDataFolder().mkdirs();
            Files.writeString(
                getDataFolder().toPath().resolve("result.json"),
                new GsonBuilder().setPrettyPrinting().create().toJson(o)
            );
        }catch(Exception x){x.printStackTrace();}
        getLogger().info("R3936 UNDERGROUND QA "+(error==null?"PASS ":"FAIL ")+nonce+" "+o);
    }
}
