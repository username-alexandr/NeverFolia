import com.google.gson.*;
import java.nio.file.Files;
import java.util.*;
import org.bukkit.*;
import org.bukkit.block.data.BlockData;
import org.bukkit.block.data.Levelled;
import org.bukkit.block.data.Waterlogged;
import org.bukkit.event.*;
import org.bukkit.event.server.ServerLoadEvent;
import org.bukkit.plugin.java.JavaPlugin;

public final class R3935OceanPillarFluidLight extends JavaPlugin implements Listener {
    private World world;
    private final List<int[]> targets=new ArrayList<>();
    private final JsonArray rows=new JsonArray();
    private int index;
    private boolean started,finished;
    private final String nonce=System.getProperty("neverfolia.qaNonce","");

    private static final int MIN_X=-3146,MAX_X=-3136;
    private static final int MIN_Z=-3450,MAX_Z=-3440;
    private static final int MIN_Y=64,MAX_Y=72;

    @Override public void onEnable(){Bukkit.getPluginManager().registerEvents(this,this);}

    @EventHandler public void loaded(ServerLoadEvent e){
        if(started)return;
        started=true;
        try{
            world=Bukkit.getWorlds().stream()
                .filter(w->w.getEnvironment()==World.Environment.NORMAL)
                .findFirst().orElseThrow();
            if(world.getSeed()!=-4651369264513492755L)throw new AssertionError("wrong seed");
            for(int cz=-217;cz<=-215;++cz)for(int cx=-198;cx<=-196;++cx)targets.add(new int[]{cx,cz});
            Bukkit.getGlobalRegionScheduler().execute(this,this::next);
        }catch(Throwable t){finish(t);}
    }

    private void next(){
        if(finished)return;
        if(index==targets.size()){finish(null);return;}
        int[] t=targets.get(index);int cx=t[0],cz=t[1];
        world.getChunkAtAsync(cx,cz,true).whenComplete((chunk,error)->{
            if(error!=null){finish(error);return;}
            Bukkit.getRegionScheduler().execute(this,world,cx,cz,()->{
                try{
                    var s=chunk.getChunkSnapshot(false,true,false);
                    int bx=cx<<4,bz=cz<<4;
                    int x0=Math.max(MIN_X,bx),x1=Math.min(MAX_X,bx+15);
                    int z0=Math.max(MIN_Z,bz),z1=Math.min(MAX_Z,bz+15);
                    if(x0<=x1&&z0<=z1){
                        for(int y=MIN_Y;y<=MAX_Y;++y)
                            for(int z=z0;z<=z1;++z)
                                for(int x=x0;x<=x1;++x){
                                    Material m=s.getBlockType(x&15,y,z&15);
                                    BlockData bd=s.getBlockData(x&15,y,z&15);
                                    int level=-1;
                                    boolean waterlogged=false;
                                    if(bd instanceof Levelled l)level=l.getLevel();
                                    if(bd instanceof Waterlogged w)waterlogged=w.isWaterlogged();
                                    JsonObject r=new JsonObject();
                                    r.addProperty("x",x);r.addProperty("y",y);r.addProperty("z",z);
                                    r.addProperty("material",m.getKey().toString());
                                    r.addProperty("data",bd.getAsString());
                                    r.addProperty("level",level);
                                    r.addProperty("waterlogged",waterlogged);
                                    r.addProperty("sky",s.getBlockSkyLight(x&15,y,z&15));
                                    r.addProperty("block_light",s.getBlockEmittedLight(x&15,y,z&15));
                                    rows.add(r);
                                }
                    }
                    ++index;
                    Bukkit.getGlobalRegionScheduler().execute(this,this::next);
                }catch(Throwable x){finish(x);}
            });
        });
    }

    private synchronized void finish(Throwable error){
        if(finished)return;
        finished=true;
        JsonObject o=new JsonObject();
        o.addProperty("pass",error==null);
        o.addProperty("nonce",nonce);
        o.addProperty("seed",world==null?0:world.getSeed());
        o.addProperty("rows",rows.size());

        int water=0,flowing=0,minSky=15,maxSky=0;
        JsonArray suspicious=new JsonArray();
        for(JsonElement e:rows){
            JsonObject r=e.getAsJsonObject();
            if("minecraft:water".equals(r.get("material").getAsString())){
                ++water;
                int level=r.get("level").getAsInt();
                int sky=r.get("sky").getAsInt();
                if(level>0)++flowing;
                minSky=Math.min(minSky,sky);
                maxSky=Math.max(maxSky,sky);
                if(level>0||sky<=10){
                    if(suspicious.size()<96)suspicious.add(r.deepCopy());
                }
            }
        }
        o.addProperty("water_cells",water);
        o.addProperty("flowing_water_cells",flowing);
        o.addProperty("min_water_skylight",water==0?-1:minSky);
        o.addProperty("max_water_skylight",water==0?-1:maxSky);
        o.add("suspicious",suspicious);
        o.add("cells",rows);
        if(error!=null){o.addProperty("error",error.toString());error.printStackTrace();}
        try{
            getDataFolder().mkdirs();
            Files.writeString(
                getDataFolder().toPath().resolve("result.json"),
                new GsonBuilder().setPrettyPrinting().create().toJson(o)
            );
        }catch(Exception x){x.printStackTrace();}
        getLogger().info("R3935 FLUID LIGHT "+(error==null?"PASS ":"FAIL ")+nonce+
            " water="+water+" flowing="+flowing+" sky="+(water==0?-1:minSky)+".."+(water==0?-1:maxSky));
    }
}
