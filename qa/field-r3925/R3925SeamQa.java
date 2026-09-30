import com.google.gson.*;
import java.nio.file.Files;
import org.bukkit.*;
import org.bukkit.event.*;
import org.bukkit.event.server.ServerLoadEvent;
import org.bukkit.plugin.java.JavaPlugin;
import org.bukkit.craftbukkit.CraftWorld;
import net.minecraft.world.level.levelgen.Heightmap;

public final class R3925SeamQa extends JavaPlugin implements Listener {
    private World world; private boolean started,finished; private int loaded;
    @Override public void onEnable(){Bukkit.getPluginManager().registerEvents(this,this);}
    @EventHandler public void loaded(ServerLoadEvent event){
        if(started)return;started=true;
        try{
            world=Bukkit.getWorlds().stream().filter(w->w.getEnvironment()==World.Environment.NORMAL).findFirst().orElseThrow();
            if(world.getSeed()!=-4651369264513492755L)throw new AssertionError("Wrong seed");
            request(-2,-3);request(-2,-2);
        }catch(Throwable t){finish(t);}
    }
    private void request(int cx,int cz){
        world.getChunkAtAsync(cx,cz,true).whenComplete((chunk,error)->{
            if(error!=null){finish(error);return;}
            Bukkit.getRegionScheduler().execute(this,world,cx,cz,()->{
                synchronized(this){loaded++;if(loaded==2)Bukkit.getGlobalRegionScheduler().execute(this,()->sample());}
            });
        });
    }
    private void sample(){
        try{
            var level=((CraftWorld)world).getHandle();
            var source=level.getChunkSource();
            var generator=source.getGenerator();
            var random=source.randomState();
            JsonArray rows=new JsonArray();
            for(int x=-32;x<=-17;x++){
                JsonObject r=new JsonObject();r.addProperty("x",x);
                int actualNorth=solidTop(x,-33),actualSouth=solidTop(x,-32);
                int baseNorth=generator.getBaseHeight(x,-33,Heightmap.Types.WORLD_SURFACE_WG,level,random);
                int baseSouth=generator.getBaseHeight(x,-32,Heightmap.Types.WORLD_SURFACE_WG,level,random);
                r.addProperty("north_z",-33);r.addProperty("south_z",-32);
                r.addProperty("actual_north",actualNorth);r.addProperty("actual_south",actualSouth);
                r.addProperty("actual_delta",Math.abs(actualNorth-actualSouth));
                r.addProperty("base_north",baseNorth);r.addProperty("base_south",baseSouth);
                r.addProperty("base_delta",Math.abs(baseNorth-baseSouth));
                r.addProperty("north_top_block",world.getBlockAt(x,actualNorth,-33).getType().getKey().toString());
                r.addProperty("south_top_block",world.getBlockAt(x,actualSouth,-32).getType().getKey().toString());
                rows.add(r);
            }
            JsonObject out=new JsonObject();out.addProperty("pass",true);out.add("rows",rows);
            write(out);finish(null);
        }catch(Throwable t){finish(t);}
    }
    private int solidTop(int x,int z){
        for(int y=192;y>=-96;y--){
            Material t=world.getBlockAt(x,y,z).getType();
            if(t.isAir()||aquatic(t)||frozen(t))continue;
            return y;
        }
        return -97;
    }
    private static boolean aquatic(Material t){
        return t==Material.WATER||t==Material.BUBBLE_COLUMN||t==Material.KELP||t==Material.KELP_PLANT
            ||t==Material.SEAGRASS||t==Material.TALL_SEAGRASS||t==Material.SEA_PICKLE;
    }
    private static boolean frozen(Material t){
        return t==Material.ICE||t==Material.PACKED_ICE||t==Material.BLUE_ICE||t==Material.FROSTED_ICE;
    }
    private void write(JsonObject out)throws Exception{
        getDataFolder().mkdirs();Files.writeString(getDataFolder().toPath().resolve("result.json"),new GsonBuilder().setPrettyPrinting().create().toJson(out));
    }
    private synchronized void finish(Throwable error){
        if(finished)return;finished=true;
        if(error!=null){
            error.printStackTrace();
            try{JsonObject o=new JsonObject();o.addProperty("pass",false);o.addProperty("error",error.toString());write(o);}catch(Exception ignored){}
        }
        getLogger().info("R3925 SEAM QA "+(error==null?"PASS":"FAIL"));
        Bukkit.getGlobalRegionScheduler().runDelayed(this,t->Bukkit.shutdown(),20L);
    }
}
