import com.google.gson.*;
import java.nio.file.Files;
import java.util.*;
import org.bukkit.*;
import org.bukkit.event.*;
import org.bukkit.event.server.ServerLoadEvent;
import org.bukkit.generator.structure.GeneratedStructure;
import org.bukkit.generator.structure.StructurePiece;
import org.bukkit.plugin.java.JavaPlugin;
import org.bukkit.util.BoundingBox;

public final class R3934StructureTrace extends JavaPlugin implements Listener {
    private World world;
    private final List<int[]> targets = new ArrayList<>();
    private final JsonArray structures = new JsonArray();
    private final JsonArray samples = new JsonArray();
    private final Set<String> seen = new HashSet<>();
    private int index;
    private boolean started, finished;
    private final String nonce = System.getProperty("neverfolia.qaNonce", "");

    @Override public void onEnable() {
        Bukkit.getPluginManager().registerEvents(this, this);
    }

    @EventHandler public void loaded(ServerLoadEvent e) {
        if (started) return;
        started = true;
        try {
            world = Bukkit.getWorlds().stream()
                .filter(w -> w.getEnvironment() == World.Environment.NORMAL)
                .findFirst().orElseThrow();
            if (world.getSeed() != -4651369264513492755L) {
                throw new AssertionError("Wrong seed " + world.getSeed());
            }

            // Screenshot 1: around x=-3138,z=-3449 -> chunk -197,-216.
            // Screenshot 2: around x=-3264,z=-3573 -> chunk -204/-205,-224.
            addArea(-197, -216, 2);
            addArea(-205, -224, 2);
            Bukkit.getGlobalRegionScheduler().execute(this, this::next);
        } catch (Throwable t) {
            finish(t);
        }
    }

    private void addArea(int cx, int cz, int radius) {
        for (int dz=-radius; dz<=radius; ++dz) {
            for (int dx=-radius; dx<=radius; ++dx) {
                targets.add(new int[]{cx+dx,cz+dz});
            }
        }
    }

    private static JsonArray box(BoundingBox b) {
        JsonArray a=new JsonArray();
        a.add(b.getMinX());a.add(b.getMinY());a.add(b.getMinZ());
        a.add(b.getMaxX());a.add(b.getMaxY());a.add(b.getMaxZ());
        return a;
    }

    private void next() {
        if (finished) return;
        if (index == targets.size()) {
            finish(null);
            return;
        }
        int[] t = targets.get(index);
        int cx=t[0],cz=t[1];
        world.getChunkAtAsync(cx,cz,true).whenComplete((chunk,error)->{
            if (error!=null) { finish(error); return; }
            Bukkit.getRegionScheduler().execute(this,world,cx,cz,()->{
                try {
                    var snapshot=chunk.getChunkSnapshot(false,true,false);
                    for (GeneratedStructure gs : chunk.getStructures()) {
                        String id=gs.getStructure().getKey().toString();
                        BoundingBox bb=gs.getBoundingBox();
                        String sig=id+"|"+bb.toString();
                        if (seen.add(sig)) {
                            JsonObject row=new JsonObject();
                            row.addProperty("id",id);
                            row.addProperty("seen_in_chunk_x",cx);
                            row.addProperty("seen_in_chunk_z",cz);
                            row.add("bounding_box",box(bb));
                            JsonArray pieces=new JsonArray();
                            for (StructurePiece piece : gs.getPieces()) {
                                pieces.add(box(piece.getBoundingBox()));
                            }
                            row.add("pieces",pieces);
                            structures.add(row);
                            getLogger().info("R3934 STRUCTURE "+id+" bbox="+bb+" pieces="+pieces.size());
                        }

                        int chunkMinX=cx<<4,chunkMinZ=cz<<4;
                        int minX=Math.max(chunkMinX,(int)Math.floor(bb.getMinX()));
                        int maxX=Math.min(chunkMinX+15,(int)Math.floor(bb.getMaxX()));
                        int minZ=Math.max(chunkMinZ,(int)Math.floor(bb.getMinZ()));
                        int maxZ=Math.min(chunkMinZ+15,(int)Math.floor(bb.getMaxZ()));
                        int minY=Math.max(world.getMinHeight(),(int)Math.floor(bb.getMinY()));
                        int maxY=Math.min(world.getMaxHeight()-1,(int)Math.floor(bb.getMaxY()));
                        if (minX<=maxX && minZ<=maxZ && minY<=maxY) {
                            int air=0,water=0,other=0;
                            for(int z=minZ;z<=maxZ;++z)for(int x=minX;x<=maxX;++x)for(int y=minY;y<=maxY;++y){
                                Material m=snapshot.getBlockType(x&15,y,z&15);
                                if(m.isAir())++air;
                                else if(aquatic(m))++water;
                                else ++other;
                            }
                            JsonObject sample=new JsonObject();
                            sample.addProperty("id",id);
                            sample.addProperty("chunk_x",cx);sample.addProperty("chunk_z",cz);
                            sample.addProperty("air",air);sample.addProperty("water",water);sample.addProperty("other",other);
                            samples.add(sample);
                        }
                    }
                    ++index;
                    Bukkit.getGlobalRegionScheduler().execute(this,this::next);
                } catch (Throwable x) {
                    finish(x);
                }
            });
        });
    }

    private static boolean aquatic(Material m) {
        return m==Material.WATER||m==Material.BUBBLE_COLUMN||m==Material.KELP||m==Material.KELP_PLANT
            ||m==Material.SEAGRASS||m==Material.TALL_SEAGRASS;
    }

    private synchronized void finish(Throwable e) {
        if (finished) return;
        finished=true;
        JsonObject o=new JsonObject();
        o.addProperty("pass",e==null);
        o.addProperty("nonce",nonce);
        o.addProperty("seed",world==null?0:world.getSeed());
        o.addProperty("generated_chunks",index);
        o.add("structures",structures);
        o.add("samples",samples);
        if (e!=null) {
            o.addProperty("error",e.toString());
            e.printStackTrace();
        }
        try {
            getDataFolder().mkdirs();
            Files.writeString(
                getDataFolder().toPath().resolve("result.json"),
                new GsonBuilder().setPrettyPrinting().create().toJson(o)
            );
        } catch(Exception x) {
            x.printStackTrace();
        }
        getLogger().info("R3934 STRUCTURE TRACE "+(e==null?"PASS ":"FAIL ")+nonce);
    }
}
