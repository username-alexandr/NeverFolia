import com.google.gson.*;
import java.nio.file.Files;
import org.bukkit.Bukkit;
import org.bukkit.craftbukkit.CraftWorld;
import org.bukkit.event.*;
import org.bukkit.event.server.ServerLoadEvent;
import org.bukkit.plugin.java.JavaPlugin;
import net.minecraft.core.BlockPos;
import net.minecraft.core.registries.Registries;
import net.minecraft.resources.*;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.levelgen.structure.templatesystem.StructurePlaceSettings;

/** Read-only registry/resource check. Does not generate a mansion or summon NPCs. */
public final class R3918ResourceQa extends JavaPlugin implements Listener {
    private final String nonce=System.getProperty("neverfolia.qaNonce","");
    private final JsonArray checks=new JsonArray();
    private boolean started;
    private void check(String name,boolean pass){JsonObject x=new JsonObject();x.addProperty("name",name);x.addProperty("pass",pass);checks.add(x);if(!pass)throw new AssertionError(name);}
    @Override public void onEnable(){Bukkit.getPluginManager().registerEvents(this,this);}
    @EventHandler public void loaded(ServerLoadEvent event){
        if(started)return;started=true;
        var world=Bukkit.getWorlds().stream().filter(w->w.getEnvironment()==org.bukkit.World.Environment.NORMAL).findFirst().orElseThrow();
        world.getChunkAtAsync(0,0,true).whenComplete((chunk,error)->{
            if(error!=null){finish(error,world.getSeed());return;}
            Bukkit.getRegionScheduler().execute(this,world,0,0,()->{
                Throwable failure=null;
                try{
                    var level=((CraftWorld)world).getHandle();
                    check("fresh_nonce",!nonce.isBlank());
                    check("actual_seed",world.getSeed()==-4651369264513492755L);
                    check("owned_region",ca.spottedleaf.moonrise.common.util.TickThread.isTickThreadFor(level,new BlockPos(8,128,8)));
                    check("malformed_identifier_interpretation",Identifier.parse("minecraft/empty").toString().equals("minecraft:minecraft/empty"));
                    var manager=level.getStructureManager();
                    check("old_unresolved_template",manager.get(Identifier.parse("minecraft:minecraft/empty")).isEmpty());
                    var t=manager.get(Identifier.parse("minecraft:empty")).orElseThrow();
                    check("canonical_template_dimensions",t.getSize().getX()==1&&t.getSize().getY()==1&&t.getSize().getZ()==1);
                    check("canonical_template_air_block",t.filterBlocks(BlockPos.ZERO,new StructurePlaceSettings(),Blocks.AIR).size()==1);
                    for(String id:new String[]{"minecraft:illager_mansion/illager_mansion_room","minecraft:illager_mansion/illager_mansion_room_basement"}){
                        var key=ResourceKey.create(Registries.TEMPLATE_POOL,Identifier.parse(id));
                        check("loaded_pool:"+id,level.registryAccess().lookupOrThrow(Registries.TEMPLATE_POOL).getOrThrow(key).value()!=null);
                    }
                }catch(Throwable t){failure=t;}
                finish(failure,world.getSeed());
            });
        });
    }
    private void finish(Throwable failure,long seed){
        JsonObject out=new JsonObject();out.addProperty("pass",failure==null);out.addProperty("nonce",nonce);out.addProperty("seed",seed);out.add("checks",checks);
        out.addProperty("scope","Read-only actual registry/template resolution; not complete mansion placement, all NPCs, loot or worldgen acceptance.");
        if(failure!=null){out.addProperty("error",failure.toString());failure.printStackTrace();}
        try{getDataFolder().mkdirs();Files.writeString(getDataFolder().toPath().resolve("result.json"),new GsonBuilder().setPrettyPrinting().create().toJson(out)+"\n");}
        catch(Exception e){e.printStackTrace();failure=e;}
        getLogger().info("R3918 RESOURCE QA "+(failure==null?"PASS":"FAIL")+" nonce="+nonce);
    }
}
