import com.google.gson.JsonObject;
import java.nio.file.Files;
import org.bukkit.Bukkit;
import org.bukkit.Chunk;
import org.bukkit.World;
import org.bukkit.event.EventHandler;
import org.bukkit.event.Listener;
import org.bukkit.event.server.ServerLoadEvent;
import org.bukkit.plugin.java.JavaPlugin;

public final class R3924IceTargetQa extends JavaPlugin implements Listener {
    private boolean started;
    @Override public void onEnable(){Bukkit.getPluginManager().registerEvents(this,this);}
    @EventHandler public void loaded(ServerLoadEvent event){
        if(started)return;started=true;
        try{
            World world=Bukkit.getWorlds().stream().filter(w->w.getEnvironment()==World.Environment.NORMAL).findFirst().orElseThrow();
            if(world.getSeed()!=-4651369264513492755L)throw new AssertionError("Wrong seed");
            world.getChunkAtAsync(-189,-223,true).whenComplete((chunk,error)->{
                if(error!=null){finish(null,error);return;}
                Bukkit.getRegionScheduler().execute(this,world,-189,-223,()->finish(chunk,null));
            });
        }catch(Throwable t){finish(null,t);}
    }
    private synchronized void finish(Chunk chunk,Throwable error){
        JsonObject r=new JsonObject();r.addProperty("pass",error==null);
        if(chunk!=null){
            r.addProperty("chunk_x",chunk.getX());r.addProperty("chunk_z",chunk.getZ());
            r.addProperty("target_block",chunk.getBlock(Math.floorMod(-3022,16),62,Math.floorMod(-3564,16)).getType().getKey().toString());
        }
        if(error!=null){r.addProperty("error",error.toString());error.printStackTrace();}
        try{getDataFolder().mkdirs();Files.writeString(getDataFolder().toPath().resolve("result.json"),r+"\n");}
        catch(Exception e){e.printStackTrace();}
        getLogger().info("R3924 ICE TARGET "+(error==null?"PASS":"FAIL")+" "+r);
        Bukkit.getGlobalRegionScheduler().runDelayed(this,task->Bukkit.shutdown(),20L);
    }
}