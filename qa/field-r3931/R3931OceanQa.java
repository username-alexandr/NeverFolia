import com.google.gson.*;
import java.nio.file.Files;
import java.util.*;
import org.bukkit.*;
import org.bukkit.block.data.Levelled;
import org.bukkit.event.*;
import org.bukkit.event.server.ServerLoadEvent;
import org.bukkit.plugin.java.JavaPlugin;

public final class R3931OceanQa extends JavaPlugin implements Listener {
    private World world; private final List<int[]> targets=new ArrayList<>(); private final JsonArray rows=new JsonArray();
    private int index; private boolean started,finished; private final String nonce=System.getProperty("neverfolia.qaNonce","");
    private static final int LOW=0,HIGH=128;
    @Override public void onEnable(){Bukkit.getPluginManager().registerEvents(this,this);}
    @EventHandler public void loaded(ServerLoadEvent e){
        if(started)return;started=true;
        try{
            world=Bukkit.getWorlds().stream().filter(w->w.getEnvironment()==World.Environment.NORMAL).findFirst().orElseThrow();
            if(world.getSeed()!=-4651369264513492755L)throw new AssertionError("Wrong seed");
            int[][] centers={{7,1},{-197,-217},{-169,-250},{-189,-223}};
            for(int[] c:centers)targets.add(new int[]{c[0],c[1]});
            if(targets.size()!=4)throw new AssertionError("target count");
            Bukkit.getGlobalRegionScheduler().execute(this,this::next);
        }catch(Throwable t){finish(t);}
    }
    private void next(){
        if(finished)return;if(index==targets.size()){finish(null);return;}
        int[] t=targets.get(index);int cx=t[0],cz=t[1];
        world.getChunkAtAsync(cx,cz,true).whenComplete((chunk,error)->{
            if(error!=null){finish(error);return;}
            Bukkit.getRegionScheduler().execute(this,world,cx,cz,()->{
                try{rows.add(sample(chunk.getChunkSnapshot(false,true,false),cx,cz));index++;getLogger().info("R3931 SAMPLE "+index+"/4 "+cx+","+cz);Bukkit.getGlobalRegionScheduler().execute(this,this::next);}
                catch(Throwable x){finish(x);}
            });
        });
    }
    private JsonObject sample(ChunkSnapshot s,int cx,int cz){
        JsonObject r=new JsonObject();int isolatedAir=0,iceBelow=0,airBelow=0,waterBelow=0;
        int longAirColumns=0,underRoofAirColumns=0,iceAtSurface=0;
        for(int z=0;z<16;z++)for(int x=0;x<16;x++){
            int run=0,maxRun=0;boolean roofAbove=false;
            for(int y=129;y<=180;y++){Material m=s.getBlockType(x,y,z);if(!m.isAir()&&!aquatic(m)){roofAbove=true;break;}}
            for(int y=LOW;y<=HIGH;y++){
                Material m=s.getBlockType(x,y,z);
                if(m.isAir()){airBelow++;run++;maxRun=Math.max(maxRun,run);}else run=0;
                if(aquatic(m))waterBelow++;
                if(frozen(m)){if(y<128)iceBelow++;else iceAtSurface++;}
                if(m.isAir()&&x>0&&x<15&&z>0&&z<15&&y>LOW&&y<HIGH
                    &&aquatic(s.getBlockType(x-1,y,z))&&aquatic(s.getBlockType(x+1,y,z))
                    &&aquatic(s.getBlockType(x,y-1,z))&&aquatic(s.getBlockType(x,y+1,z))
                    &&aquatic(s.getBlockType(x,y,z-1))&&aquatic(s.getBlockType(x,y,z+1)))isolatedAir++;
            }
            if(maxRun>=16){longAirColumns++;if(roofAbove)underRoofAirColumns++;}
        }
        r.addProperty("chunk_x",cx);r.addProperty("chunk_z",cz);r.addProperty("water_0_128",waterBelow);r.addProperty("air_0_128",airBelow);
        r.addProperty("isolated_air_in_water",isolatedAir);r.addProperty("ice_below_128",iceBelow);r.addProperty("ice_at_128",iceAtSurface);
        r.addProperty("long_air_columns_ge16",longAirColumns);r.addProperty("long_air_columns_under_roof",underRoofAirColumns);
        return r;
    }
    private static boolean aquatic(Material m){return m==Material.WATER||m==Material.BUBBLE_COLUMN||m==Material.KELP||m==Material.KELP_PLANT||m==Material.SEAGRASS||m==Material.TALL_SEAGRASS;}
    private static boolean frozen(Material m){return m==Material.ICE||m==Material.PACKED_ICE||m==Material.BLUE_ICE||m==Material.FROSTED_ICE;}
    private synchronized void finish(Throwable e){
        if(finished)return;finished=true;JsonObject o=new JsonObject();o.addProperty("pass",e==null);o.addProperty("nonce",nonce);o.addProperty("seed",world==null?0:world.getSeed());o.addProperty("completed_chunks",rows.size());o.add("chunks",rows);
        if(e!=null){o.addProperty("error",e.toString());e.printStackTrace();}
        try{getDataFolder().mkdirs();Files.writeString(getDataFolder().toPath().resolve("result.json"),new GsonBuilder().setPrettyPrinting().create().toJson(o));}catch(Exception x){x.printStackTrace();e=x;}
        getLogger().info("R3931 OCEAN QA "+(e==null?"PASS ":"FAIL ")+nonce);
    }
}
