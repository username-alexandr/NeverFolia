import com.google.gson.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.io.InputStreamReader;
import java.util.*;
import org.bukkit.Bukkit;
import org.bukkit.craftbukkit.CraftWorld;
import org.bukkit.entity.Villager;
import org.bukkit.event.*;
import org.bukkit.event.server.ServerLoadEvent;
import org.bukkit.plugin.java.JavaPlugin;
import net.minecraft.core.BlockPos;
import net.minecraft.core.registries.Registries;
import net.minecraft.resources.*;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.levelgen.structure.pools.JigsawPlacement;
import net.minecraft.world.phys.AABB;

/** 22 restored models plus three source armorer carts with repaired aliases.
 * Real jigsaw/NPC assembly in a disposable owned region, not natural frequency,
 * villager profession acquisition or trade testing. No count relaxation.
 */
public final class R3915CartQa extends JavaPlugin implements Listener {
    private static final BlockPos AT=new BlockPos(8,400,8);
    private static final AABB AREA=new AABB(0,397,0,16,413,16);
    private final JsonArray checks=new JsonArray(),teardowns=new JsonArray();
    private final List<LivingEntity> previous=new ArrayList<>();
    private final String nonce=System.getProperty("neverfolia.qaNonce","");
    private JsonArray cases;
    private org.bukkit.World world;
    private ServerLevel level;
    private boolean started,finished;
    private static void need(boolean ok,String text){if(!ok)throw new AssertionError(text);}
    @Override public void onEnable(){Bukkit.getPluginManager().registerEvents(this,this);}
    @EventHandler public void loaded(ServerLoadEvent e){
        if(started)return;started=true;
        try {
            need(!nonce.isBlank(),"fresh nonce absent");
            try(var r=new InputStreamReader(Objects.requireNonNull(getResource("cases.json")),StandardCharsets.UTF_8)){cases=JsonParser.parseReader(r).getAsJsonArray();}
            need(cases.size()==25,"wrong reviewed case count");
            world=Bukkit.getWorlds().stream().filter(w->w.getEnvironment()==org.bukkit.World.Environment.NORMAL).findFirst().orElseThrow();
            level=((CraftWorld)world).getHandle();need(world.getSeed()==-4651369264513492755L,"wrong seed");
            Bukkit.getGlobalRegionScheduler().execute(this,()->{world.setChunkForceLoaded(0,0,true);next(0);});
        }catch(Throwable t){finish(t);}
    }
    private void next(int i){
        if(finished)return;if(i==cases.size()){finish(null);return;}
        world.getChunkAtAsync(0,0,true).whenComplete((c,error)->{
            if(error!=null){finish(error);return;}
            Bukkit.getRegionScheduler().execute(this,world,0,0,()->clean(i));
        });
    }
    private void clean(int i){
        try {
            need(ca.spottedleaf.moonrise.common.util.TickThread.isTickThreadFor(level,AT),"wrong cleanup owner");
            Set<LivingEntity> removed=new LinkedHashSet<>(previous);removed.addAll(level.getEntitiesOfClass(LivingEntity.class,AREA,e->!e.isRemoved()));
            JsonObject row=new JsonObject();row.addProperty("next_case",i);JsonArray ids=new JsonArray();
            for(var entity:removed){if(!entity.isRemoved()){need(ca.spottedleaf.moonrise.common.util.TickThread.isTickThreadFor(entity),"fixture escaped region");entity.discard();}need(entity.isRemoved(),"discard did not remove fixture");ids.add(entity.getUUID().toString());}
            previous.clear();row.add("retired_uuids",ids);teardowns.add(row);
            Bukkit.getRegionScheduler().runDelayed(this,world,0,0,task->{try{int n=level.getEntitiesOfClass(LivingEntity.class,AREA,e->!e.isRemoved()).size();row.addProperty("live_after_barrier",n);need(n==0,"live NPC contamination before next cart");place(i);}catch(Throwable t){finish(t);}},2);
        }catch(Throwable t){finish(t);}
    }
    private void place(int i){
        JsonObject c=cases.get(i).getAsJsonObject();String id=c.get("id").getAsString(),role=c.get("role").getAsString();
        try {
            need(ca.spottedleaf.moonrise.common.util.TickThread.isTickThreadFor(level,AT),"wrong cart owner");
            BlockPos.MutableBlockPos p=new BlockPos.MutableBlockPos();
            for(int y=397;y<=412;y++)for(int z=0;z<16;z++)for(int x=0;x<16;x++)level.setBlock(p.set(x,y,z),(y==398?Blocks.STONE:Blocks.AIR).defaultBlockState(),2);
            var template=level.getStructureManager().get(Identifier.parse(id)).orElseThrow();JsonArray size=c.getAsJsonArray("root_size");
            need(template.getSize().getX()==size.get(0).getAsInt()&&template.getSize().getY()==size.get(1).getAsInt()&&template.getSize().getZ()==size.get(2).getAsInt(),"template dimensions changed "+id);
            var key=ResourceKey.create(Registries.TEMPLATE_POOL,Identifier.parse("neverfolia_qa:cart/case_"+i));
            var pool=level.registryAccess().lookupOrThrow(Registries.TEMPLATE_POOL).getOrThrow(key);
            need(JigsawPlacement.generateJigsaw(level,pool,Identifier.parse(c.get("target").getAsString()),2,AT,false),"jigsaw rejected "+id);
            Bukkit.getRegionScheduler().runDelayed(this,world,0,0,task->{
                try {
                    int unfinished=0,station=0,geometry=0;BlockPos.MutableBlockPos q=new BlockPos.MutableBlockPos();
                    for(int y=399;y<=412;y++)for(int z=0;z<16;z++)for(int x=0;x<16;x++){
                        var b=level.getBlockState(q.set(x,y,z));if(b.is(Blocks.JIGSAW))unfinished++;if(!b.isAir())geometry++;
                        if(b.is(switch(role){case "cartographer"->Blocks.CARTOGRAPHY_TABLE;case "cleric"->Blocks.BREWING_STAND;case "armorer"->Blocks.BLAST_FURNACE;default->throw new AssertionError("unreviewed role");}))station++;
                    }
                    var villagers=level.getEntitiesOfClass(LivingEntity.class,AREA,e->!e.isRemoved()&&e.getBukkitEntity() instanceof Villager);
                    JsonArray npc=new JsonArray();for(var entity:villagers){JsonObject n=new JsonObject();n.addProperty("uuid",entity.getUUID().toString());n.addProperty("profession",((Villager)entity.getBukkitEntity()).getProfession().name());n.addProperty("position",entity.position().toString());npc.add(n);}
                    getLogger().info("R3915 CART OBSERVE "+id+" "+npc);
                    need(unfinished==0,"unfinished joints "+id);need(station==1,"wrong station count "+id+": "+station);need(geometry>8,"missing cart geometry "+id);
                    int expected=c.get("expected_villagers").getAsInt();need(villagers.size()==expected,"NPC count "+id+" actual="+villagers.size()+" expected="+expected);
                    previous.addAll(villagers);JsonObject row=c.deepCopy();row.addProperty("workstations",station);row.addProperty("remaining_jigsaws",unfinished);row.addProperty("nonair_cart_blocks",geometry);row.addProperty("observed_villagers",villagers.size());row.add("npc_observations",npc);row.addProperty("pass",true);checks.add(row);persist(null,false);
                    getLogger().info("R3915 CART "+checks.size()+"/25 PASS");Bukkit.getGlobalRegionScheduler().execute(this,()->next(i+1));
                }catch(Throwable t){finish(t);}
            },10);
        }catch(Throwable t){finish(t);}
    }
    private void persist(Throwable e,boolean complete)throws Exception {
        JsonObject r=new JsonObject();r.addProperty("pass",complete&&e==null&&checks.size()==25);r.addProperty("seed",world==null?0:world.getSeed());r.addProperty("nonce",nonce);r.addProperty("completed",checks.size());r.add("checks",checks);r.add("entity_teardowns",teardowns);r.addProperty("scope","Actual jigsaw and spawned NPCs with strict empty-population barriers; no natural distribution or villager trading test.");if(e!=null)r.addProperty("error",e.toString());getDataFolder().mkdirs();Files.writeString(getDataFolder().toPath().resolve("result.json"),new GsonBuilder().setPrettyPrinting().create().toJson(r)+"\n");
    }
    private synchronized void finish(Throwable e){if(finished)return;finished=true;if(e!=null)e.printStackTrace();try{persist(e,true);}catch(Exception t){t.printStackTrace();e=t;}getLogger().info("R3915 CART QA "+(e==null?"PASS":"FAIL")+" nonce="+nonce);}
}
