import com.google.gson.*;
import java.nio.file.Files;
import java.util.*;
import org.bukkit.Bukkit;
import org.bukkit.craftbukkit.CraftWorld;
import org.bukkit.entity.Villager;
import org.bukkit.event.EventHandler;
import org.bukkit.event.Listener;
import org.bukkit.event.server.ServerLoadEvent;
import org.bukkit.plugin.java.JavaPlugin;
import net.minecraft.core.BlockPos;
import net.minecraft.core.registries.Registries;
import net.minecraft.resources.Identifier;
import net.minecraft.resources.ResourceKey;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.levelgen.structure.pools.JigsawPlacement;
import net.minecraft.world.phys.AABB;

/** Isolated CI world ONLY. Deliberate synthetic placement, not natural tavern selection. */
public final class R3914CartQa extends JavaPlugin implements Listener {
    private static final String[] BIOMES={"acacia","birch","cherry","desert","jungle","mangrove","oak","pale","snowy","spruce","swamp"};
    private static final String[] ROLES={"cartographer","cleric"};
    private static final BlockPos ANCHOR=new BlockPos(8,400,8);
    private static final AABB AREA=new AABB(0,397,0,16,413,16);
    private final JsonArray rows=new JsonArray();
    private final String nonce=System.getProperty("neverfolia.qaNonce","");
    private org.bukkit.World world;
    private ServerLevel level;
    private boolean started,finished;
    @Override public void onEnable(){Bukkit.getPluginManager().registerEvents(this,this);}
    @EventHandler public void loaded(ServerLoadEvent event){
        if(started)return;started=true;
        try{
            require(!nonce.isBlank(),"missing current process nonce");
            world=Bukkit.getWorlds().stream().filter(w->w.getEnvironment()==org.bukkit.World.Environment.NORMAL).findFirst().orElseThrow();
            require(world.getSeed()==-4651369264513492755L,"unexpected actual world seed");
            level=((CraftWorld)world).getHandle();next(0);
        }catch(Throwable t){finish(t);}
    }
    private static void require(boolean ok,String message){if(!ok)throw new AssertionError(message);}
    private void next(int index){
        if(finished)return;if(index==22){finish(null);return;}
        world.getChunkAtAsync(0,0,true).whenComplete((chunk,error)->{
            if(error!=null){finish(error);return;}
            Bukkit.getRegionScheduler().execute(this,world,0,0,()->place(index));
        });
    }
    private void place(int index){
        String biome=BIOMES[index/2],role=ROLES[index%2];
        try{
            require(ca.spottedleaf.moonrise.common.util.TickThread.isTickThreadFor(level,ANCHOR),"wrong fixture owner");
            for(var entity:level.getEntitiesOfClass(net.minecraft.world.entity.LivingEntity.class,AREA,e->true))entity.getBukkitEntity().remove();
            BlockPos.MutableBlockPos p=new BlockPos.MutableBlockPos();
            for(int y=397;y<=412;y++)for(int z=0;z<16;z++)for(int x=0;x<16;x++)
                level.setBlock(p.set(x,y,z),(y==398?Blocks.STONE:Blocks.AIR).defaultBlockState(),2);
            var id=Identifier.parse("nova_structures:tavern/tavern_event_trader_car_"+role+"_"+biome);
            var template=level.getStructureManager().get(id).orElseThrow();
            require(template.getSize().getX()==5 && template.getSize().getZ()==5
                && template.getSize().getY()==(biome.equals("snowy")?5:4),"invalid actual template dimensions "+id);
            var registry=level.registryAccess().lookupOrThrow(Registries.TEMPLATE_POOL);
            var selected=registry.getOrThrow(ResourceKey.create(Registries.TEMPLATE_POOL,Identifier.parse("neverfolia_qa:cart/"+role+"_"+biome)));
            require(JigsawPlacement.generateJigsaw(level,selected,Identifier.parse("nova_structures:tavern_trader_car_"+biome),2,ANCHOR,false),"jigsaw rejected cart "+id);
            Bukkit.getRegionScheduler().runDelayed(this,world,0,0,task->{
                try{
                    require(ca.spottedleaf.moonrise.common.util.TickThread.isTickThreadFor(level,ANCHOR),"wrong observer owner");
                    int jigsaws=0,workstations=0,geometry=0;
                    BlockPos.MutableBlockPos q=new BlockPos.MutableBlockPos();
                    for(int y=399;y<=412;y++)for(int z=0;z<16;z++)for(int x=0;x<16;x++){
                        var state=level.getBlockState(q.set(x,y,z));
                        if(state.is(Blocks.JIGSAW))jigsaws++;
                        if(!state.isAir())geometry++;
                        if(state.is(role.equals("cartographer")?Blocks.CARTOGRAPHY_TABLE:Blocks.BREWING_STAND))workstations++;
                    }
                    var villagers=level.getEntitiesOfClass(net.minecraft.world.entity.LivingEntity.class,AREA,e->e.getBukkitEntity() instanceof Villager);
                    int expected=biome.equals("pale")?0:1;
                    require(jigsaws==0,"unfinished joints "+id);
                    require(workstations==1,"missing or duplicate profession workstation "+id+": "+workstations);
                    require(geometry>8,"cart geometry absent "+id);
                    require(villagers.size()==expected,"unexpected child-pool villager count "+id+": "+villagers.size()+" expected "+expected);
                    JsonObject row=new JsonObject();row.addProperty("id",id.toString());row.addProperty("biome",biome);row.addProperty("role",role);
                    row.addProperty("workstations",workstations);row.addProperty("nonair_cart_blocks",geometry);row.addProperty("remaining_jigsaws",jigsaws);
                    row.addProperty("expected_villagers",expected);row.addProperty("observed_villagers",villagers.size());
                    JsonArray professions=new JsonArray();for(var e:villagers)professions.add(((Villager)e.getBukkitEntity()).getProfession().name());row.add("observed_professions",professions);
                    row.addProperty("pass",true);rows.add(row);persist(null,false);
                    getLogger().info("R3914 CART "+rows.size()+"/22 "+id+" PASS");
                    Bukkit.getGlobalRegionScheduler().execute(this,()->next(index+1));
                }catch(Throwable t){finish(t);}
            },10);
        }catch(Throwable t){finish(t);}
    }
    private void persist(Throwable error,boolean complete)throws Exception{
        JsonObject result=new JsonObject();result.addProperty("pass",complete && error==null && rows.size()==22);result.addProperty("nonce",nonce);
        result.addProperty("seed",world==null?0:world.getSeed());result.addProperty("completed",rows.size());result.add("checks",rows);
        result.addProperty("scope","22 synthetic actual jigsaw assemblies from original parent element settings and original NPC child pool; pale follows the existing no-villager design. Not natural tavern frequency, job acquisition, trades, combat, or every dungeon.");
        if(error!=null)result.addProperty("error",error.toString());getDataFolder().mkdirs();
        Files.writeString(getDataFolder().toPath().resolve("result.json"),new GsonBuilder().setPrettyPrinting().create().toJson(result)+"\n");
    }
    private synchronized void finish(Throwable error){
        if(finished)return;finished=true;if(error!=null)error.printStackTrace();
        try{persist(error,true);}catch(Exception e){e.printStackTrace();error=e;}
        getLogger().info("R3914 CART QA "+(error==null?"PASS":"FAIL")+" nonce="+nonce);
    }
}
