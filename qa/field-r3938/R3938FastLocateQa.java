import com.google.gson.*;
import com.mojang.datafixers.util.Pair;
import java.nio.file.Files;
import java.util.concurrent.CompletableFuture;
import org.bukkit.*;
import org.bukkit.craftbukkit.CraftWorld;
import org.bukkit.event.*;
import org.bukkit.event.server.ServerLoadEvent;
import org.bukkit.generator.structure.GeneratedStructure;
import org.bukkit.plugin.java.JavaPlugin;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Holder;
import net.minecraft.core.HolderSet;
import net.minecraft.core.Registry;
import net.minecraft.core.registries.Registries;
import net.minecraft.resources.Identifier;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.level.ChunkPos;
import net.minecraft.world.level.levelgen.structure.Structure;

public final class R3938FastLocateQa extends JavaPlugin implements Listener {
    private boolean started, finished;
    private final String nonce=System.getProperty("neverfolia.qaNonce","");

    @Override public void onEnable(){
        Bukkit.getPluginManager().registerEvents(this,this);
    }

    @EventHandler public void loaded(ServerLoadEvent event){
        if(started)return;
        started=true;
        Bukkit.getGlobalRegionScheduler().execute(this,this::runLocate);
    }

    private void runLocate(){
        try{
            World bw=Bukkit.getWorlds().stream()
                .filter(w->w.getEnvironment()==World.Environment.NETHER)
                .findFirst().orElseThrow();
            ServerLevel level=((CraftWorld)bw).getHandle();
            Registry<Structure> registry=level.registryAccess().lookupOrThrow(Registries.STRUCTURE);
            Holder<Structure> holder=registry.get(Identifier.parse("nova_structures:nether_keep"))
                .orElseThrow();

            long start=System.nanoTime();
            Pair<BlockPos,Holder<Structure>> result=
                level.getChunkSource().getGenerator().findNearestMapStructure(
                    level,
                    HolderSet.direct(holder),
                    new BlockPos(0,64,0),
                    100,
                    false
                );
            long elapsedMs=(System.nanoTime()-start)/1_000_000L;
            if(result==null)throw new AssertionError("fast locate returned null");
            if(elapsedMs>=4000L)throw new AssertionError("fast locate too slow: "+elapsedMs+"ms");

            String locatedId=result.getSecond().unwrapKey()
                .map(k->k.identifier().toString()).orElse("");
            if(!"nova_structures:nether_keep".equals(locatedId)){
                throw new AssertionError("located wrong structure: "+locatedId);
            }

            BlockPos pos=result.getFirst();
            ChunkPos cp=ChunkPos.containing(pos);
            getLogger().info("R3938 LOCATE RESULT x="+pos.getX()+" z="+pos.getZ()+
                " chunk="+cp.x()+","+cp.z()+" elapsedMs="+elapsedMs);

            CompletableFuture<Chunk> future=bw.getChunkAtAsync(cp.x(),cp.z(),true);
            future.whenComplete((chunk,error)->{
                if(error!=null){finish(error,null);return;}
                Bukkit.getRegionScheduler().execute(this,bw,cp.x(),cp.z(),()->{
                    try{
                        boolean found=false;
                        int structures=0;
                        JsonArray actualIds=new JsonArray();
                        for(GeneratedStructure gs:chunk.getStructures()){
                            ++structures;
                            String actualId=gs.getStructure().getKey().toString();
                            actualIds.add(actualId);
                            if("nova_structures:nether_keep".equals(actualId)){
                                found=true;
                            }
                        }
                        if(!found){
                            throw new AssertionError(
                                "located candidate did not generate nether_keep; structures="
                                +structures+" ids="+actualIds
                            );
                        }
                        JsonObject out=new JsonObject();
                        out.addProperty("pass",true);
                        out.addProperty("nonce",nonce);
                        out.addProperty("elapsed_ms",elapsedMs);
                        out.addProperty("x",pos.getX());
                        out.addProperty("z",pos.getZ());
                        out.addProperty("chunk_x",cp.x());
                        out.addProperty("chunk_z",cp.z());
                        out.addProperty("generated_nether_keep",true);
                        out.addProperty("structure_count_in_chunk",structures);
                        finish(null,out);
                    }catch(Throwable t){finish(t,null);}
                });
            });
        }catch(Throwable t){
            finish(t,null);
        }
    }

    private synchronized void finish(Throwable error,JsonObject provided){
        if(finished)return;
        finished=true;
        JsonObject out=provided==null?new JsonObject():provided;
        if(!out.has("pass"))out.addProperty("pass",error==null);
        out.addProperty("nonce",nonce);
        if(error!=null){
            out.addProperty("pass",false);
            out.addProperty("error",error.toString());
            error.printStackTrace();
        }
        try{
            getDataFolder().mkdirs();
            Files.writeString(
                getDataFolder().toPath().resolve("result.json"),
                new GsonBuilder().setPrettyPrinting().create().toJson(out)
            );
        }catch(Exception e){e.printStackTrace();}
        getLogger().info("R3938 FAST LOCATE "+(out.get("pass").getAsBoolean()?"PASS ":"FAIL ")+nonce+" "+out);
    }
}
