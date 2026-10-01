import com.google.gson.*;
import java.nio.file.Files;
import java.util.*;
import org.bukkit.*;
import org.bukkit.event.*;
import org.bukkit.event.server.ServerLoadEvent;
import org.bukkit.generator.structure.GeneratedStructure;
import org.bukkit.plugin.java.JavaPlugin;
import org.bukkit.util.BoundingBox;

public final class R3934MonumentQa extends JavaPlugin implements Listener {
    private World world;
    private final List<int[]> targets=new ArrayList<>();
    private final Set<String> sampled=new HashSet<>();
    private int index;
    private int monumentCount;
    private int minBaseY=Integer.MAX_VALUE;
    private int maxBaseY=Integer.MIN_VALUE;
    private int maxSupportRun;
    private boolean started,finished;
    private final String nonce=System.getProperty("neverfolia.qaNonce","");

    @Override public void onEnable(){Bukkit.getPluginManager().registerEvents(this,this);}

    @EventHandler public void loaded(ServerLoadEvent e){
        if(started)return;started=true;
        try{
            world=Bukkit.getWorlds().stream()
                .filter(w->w.getEnvironment()==World.Environment.NORMAL)
                .findFirst().orElseThrow();
            if(world.getSeed()!=-4651369264513492755L)throw new AssertionError("wrong seed");
            // Known deterministic vanilla monument from the user's current screenshot.
            for(int dz=-4;dz<=4;++dz)for(int dx=-4;dx<=4;++dx)targets.add(new int[]{-212+dx,-212+dz});
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
                    var snap=chunk.getChunkSnapshot(false,true,false);
                    for(GeneratedStructure gs:chunk.getStructures()){
                        if(!"minecraft:monument".equals(gs.getStructure().getKey().toString()))continue;
                        BoundingBox bb=gs.getBoundingBox();
                        String sig=bb.toString();
                        if(sampled.add(sig)){
                            ++monumentCount;
                            minBaseY=Math.min(minBaseY,(int)Math.floor(bb.getMinY()));
                            maxBaseY=Math.max(maxBaseY,(int)Math.floor(bb.getMinY()));
                            getLogger().info("R3934 MONUMENT bbox="+bb);
                        }

                        int minX=Math.max(cx<<4,(int)Math.floor(bb.getMinX()));
                        int maxX=Math.min((cx<<4)+15,(int)Math.floor(bb.getMaxX()));
                        int minZ=Math.max(cz<<4,(int)Math.floor(bb.getMinZ()));
                        int maxZ=Math.min((cz<<4)+15,(int)Math.floor(bb.getMaxZ()));
                        int base=(int)Math.floor(bb.getMinY());
                        for(int z=minZ;z<=maxZ;++z)for(int x=minX;x<=maxX;++x){
                            int run=0;
                            for(int y=base-1;y>=Math.max(world.getMinHeight(),base-64);--y){
                                Material m=snap.getBlockType(x&15,y,z&15);
                                if(isFoundation(m))++run;
                                else break;
                            }
                            maxSupportRun=Math.max(maxSupportRun,run);
                        }
                    }
                    ++index;
                    Bukkit.getGlobalRegionScheduler().execute(this,this::next);
                }catch(Throwable x){finish(x);}
            });
        });
    }

    private static boolean isFoundation(Material m){
        return m==Material.PRISMARINE||m==Material.PRISMARINE_BRICKS||m==Material.DARK_PRISMARINE;
    }

    private synchronized void finish(Throwable error){
        if(finished)return;finished=true;
        if(error==null){
            // This deterministic candidate is the exact steep-seabed Monument
            // from the user's screenshot. R39.34 must reject it entirely.
            if(monumentCount!=0)error=new AssertionError(
                "steep-seabed monument candidate was not rejected: count="+monumentCount+
                " baseY="+minBaseY+" maxSupport="+maxSupportRun
            );
        }

        JsonObject o=new JsonObject();
        o.addProperty("pass",error==null);
        o.addProperty("nonce",nonce);
        o.addProperty("seed",world==null?0:world.getSeed());
        o.addProperty("generated_chunks",index);
        o.addProperty("monument_count",monumentCount);
        o.addProperty("min_base_y",minBaseY==Integer.MAX_VALUE?0:minBaseY);
        o.addProperty("max_base_y",maxBaseY==Integer.MIN_VALUE?0:maxBaseY);
        o.addProperty("max_support_run",maxSupportRun);
        o.addProperty("steep_candidate_rejected",monumentCount==0);
        if(error!=null){o.addProperty("error",error.toString());error.printStackTrace();}
        try{
            getDataFolder().mkdirs();
            Files.writeString(getDataFolder().toPath().resolve("result.json"),
                new GsonBuilder().setPrettyPrinting().create().toJson(o));
        }catch(Exception x){x.printStackTrace();}
        getLogger().info("R3934 MONUMENT QA "+(error==null?"PASS ":"FAIL ")+nonce+" "+o);
    }
}
