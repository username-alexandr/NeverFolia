import com.google.gson.*;
import java.nio.file.Files;
import java.util.*;
import org.bukkit.*;
import org.bukkit.event.*;
import org.bukkit.event.server.ServerLoadEvent;
import org.bukkit.generator.structure.GeneratedStructure;
import org.bukkit.plugin.java.JavaPlugin;
import org.bukkit.util.BoundingBox;

public final class R3935OceanPillarQa extends JavaPlugin implements Listener {
    private World world;
    private final List<int[]> targets=new ArrayList<>();
    private boolean started,finished;
    private int index;
    private int pillarCount;
    private int pillarPieces=-1;
    private int airInside;
    private String cell68="";
    private String cell69="";
    private final String nonce=System.getProperty("neverfolia.qaNonce","");

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
                    var snap=chunk.getChunkSnapshot(false,true,false);
                    for(GeneratedStructure gs:chunk.getStructures()){
                        if(!"structory_towers:ocean_pillar".equals(gs.getStructure().getKey().toString()))continue;
                        BoundingBox bb=gs.getBoundingBox();
                        if(pillarPieces<0){
                            ++pillarCount;
                            pillarPieces=gs.getPieces().size();
                            getLogger().info("R3935 OCEAN_PILLAR bbox="+bb+" pieces="+pillarPieces);
                        }

                        int minX=Math.max(cx<<4,(int)Math.floor(bb.getMinX()));
                        int maxX=Math.min((cx<<4)+15,(int)Math.floor(bb.getMaxX()));
                        int minZ=Math.max(cz<<4,(int)Math.floor(bb.getMinZ()));
                        int maxZ=Math.min((cz<<4)+15,(int)Math.floor(bb.getMaxZ()));
                        int minY=Math.max(world.getMinHeight(),(int)Math.floor(bb.getMinY()));
                        int maxY=Math.min(world.getMaxHeight()-1,(int)Math.floor(bb.getMaxY()));
                        for(int z=minZ;z<=maxZ;++z)
                            for(int x=minX;x<=maxX;++x)
                                for(int y=minY;y<=maxY;++y)
                                    if(snap.getBlockType(x&15,y,z&15).isAir())++airInside;
                    }

                    if(cx==-197&&cz==-216){
                        cell68=snap.getBlockType((-3140)&15,68,(-3445)&15).getKey().toString();
                        cell69=snap.getBlockType((-3140)&15,69,(-3445)&15).getKey().toString();
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
        if(error==null){
            if(pillarCount!=1)error=new AssertionError("ocean_pillar count="+pillarCount);
            else if(pillarPieces!=1)error=new AssertionError("ocean_pillar still has child piece count="+pillarPieces);
            else if(airInside!=0)error=new AssertionError("ocean_pillar contains AIR after generation: "+airInside);
            else if(!"minecraft:water".equals(cell68)||!"minecraft:water".equals(cell69))
                error=new AssertionError("former waystone cells are not native water: "+cell68+", "+cell69);
        }

        JsonObject o=new JsonObject();
        o.addProperty("pass",error==null);
        o.addProperty("nonce",nonce);
        o.addProperty("seed",world==null?0:world.getSeed());
        o.addProperty("generated_chunks",index);
        o.addProperty("ocean_pillar_count",pillarCount);
        o.addProperty("ocean_pillar_pieces",pillarPieces);
        o.addProperty("air_inside_bbox",airInside);
        o.addProperty("cell_-3140_68_-3445",cell68);
        o.addProperty("cell_-3140_69_-3445",cell69);
        if(error!=null){o.addProperty("error",error.toString());error.printStackTrace();}

        try{
            getDataFolder().mkdirs();
            Files.writeString(
                getDataFolder().toPath().resolve("result.json"),
                new GsonBuilder().setPrettyPrinting().create().toJson(o)
            );
        }catch(Exception x){x.printStackTrace();}
        getLogger().info("R3935 OCEAN PILLAR QA "+(error==null?"PASS ":"FAIL ")+nonce+" "+o);
    }
}
