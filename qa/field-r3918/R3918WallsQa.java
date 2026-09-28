import com.google.gson.*;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.*;
import java.util.concurrent.CompletableFuture;
import org.bukkit.Bukkit;
import org.bukkit.craftbukkit.CraftWorld;
import org.bukkit.event.*;
import org.bukkit.event.server.ServerLoadEvent;
import org.bukkit.plugin.java.JavaPlugin;
import net.minecraft.core.BlockPos;
import net.minecraft.core.registries.Registries;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.nbt.NbtIo;
import net.minecraft.resources.*;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.util.RandomSource;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.levelgen.structure.templatesystem.StructurePlaceSettings;
import net.minecraft.world.phys.AABB;

/** Actual isolated direct template placements. NOT a complete jigsaw fort. */
public final class R3918WallsQa extends JavaPlugin implements Listener {
    private static final BlockPos AT=new BlockPos(0,400,0);
    private static final AABB AREA=new AABB(0,398,0,32,433,32);
    private final String nonce=System.getProperty("neverfolia.qaNonce","");
    private final JsonArray checks=new JsonArray(),walls=new JsonArray();
    private final List<Entity> previous=new ArrayList<>();
    private JsonArray cases;private org.bukkit.World world;private ServerLevel level;private boolean started,finished;
    private static void need(boolean ok,String text){if(!ok)throw new AssertionError(text);}
    private void check(String name,boolean pass){JsonObject x=new JsonObject();x.addProperty("name",name);x.addProperty("pass",pass);checks.add(x);need(pass,name);}
    @Override public void onEnable(){Bukkit.getPluginManager().registerEvents(this,this);}
    @EventHandler public void loaded(ServerLoadEvent event){
        if(started)return;started=true;
        try{
            try(var in=new InputStreamReader(Objects.requireNonNull(getResource("wall-cases.json")),StandardCharsets.UTF_8)){cases=JsonParser.parseReader(in).getAsJsonArray();}
            need(cases.size()==36,"incomplete authored family");
            world=Bukkit.getWorlds().stream().filter(w->w.getEnvironment()==org.bukkit.World.Environment.NORMAL).findFirst().orElseThrow();level=((CraftWorld)world).getHandle();
            Bukkit.getGlobalRegionScheduler().execute(this,()->{
                List<CompletableFuture<?>> futures=new ArrayList<>();
                for(int z=0;z<2;z++)for(int x=0;x<2;x++){world.setChunkForceLoaded(x,z,true);futures.add(world.getChunkAtAsync(x,z,true));}
                CompletableFuture.allOf(futures.toArray(new CompletableFuture<?>[0])).whenComplete((v,e)->{if(e!=null)finish(e);else Bukkit.getRegionScheduler().execute(this,world,0,0,()->ready(0));});
            });
        }catch(Throwable t){finish(t);}
    }
    private boolean owned(){for(int z=0;z<2;z++)for(int x=0;x<2;x++)if(!ca.spottedleaf.moonrise.common.util.TickThread.isTickThreadFor(level,new BlockPos(x*16+8,410,z*16+8)))return false;return true;}
    private void ready(int tries){
        try{
            if(!owned()){need(tries<100,"test region did not merge; do not bypass ownership");Bukkit.getRegionScheduler().runDelayed(this,world,0,0,t->ready(tries+1),2);return;}
            check("fresh_nonce",!nonce.isBlank());check("actual_seed",world.getSeed()==-4651369264513492755L);check("owned_region",owned());
            check("malformed_identifier_interpretation",Identifier.parse("minecraft/empty").toString().equals("minecraft:minecraft/empty"));
            check("old_unresolved_template",level.getStructureManager().get(Identifier.parse("minecraft:minecraft/empty")).isEmpty());
            var empty=level.getStructureManager().get(Identifier.parse("minecraft:empty")).orElseThrow();
            check("canonical_template_dimensions",empty.getSize().getX()==1&&empty.getSize().getY()==1&&empty.getSize().getZ()==1);
            check("canonical_template_air_block",empty.filterBlocks(BlockPos.ZERO,new StructurePlaceSettings(),Blocks.AIR).size()==1);
            for(String id:new String[]{"minecraft:illager_mansion/illager_mansion_room","minecraft:illager_mansion/illager_mansion_room_basement"})check("loaded_pool:"+id,level.registryAccess().lookupOrThrow(Registries.TEMPLATE_POOL).getOrThrow(ResourceKey.create(Registries.TEMPLATE_POOL,Identifier.parse(id))).value()!=null);
            next(0);
        }catch(Throwable t){finish(t);}
    }
    private void next(int i){
        if(finished)return;if(i==cases.size()){finish(null);return;}
        try{
            need(owned(),"lost scene ownership");Set<Entity> retire=new LinkedHashSet<>(previous);retire.addAll(level.getEntitiesOfClass(Entity.class,AREA,e->!e.isRemoved()));
            for(Entity e:retire){need(ca.spottedleaf.moonrise.common.util.TickThread.isTickThreadFor(e),"source entity escaped owned area");e.discard();}previous.clear();
            Bukkit.getRegionScheduler().runDelayed(this,world,0,0,t->{try{need(owned(),"cleanup barrier ownership");need(level.getEntitiesOfClass(Entity.class,AREA,e->!e.isRemoved()).isEmpty(),"stale scene entity");place(i);}catch(Throwable e){finish(e);}},2);
        }catch(Throwable t){finish(t);}
    }
    private void place(int i){
        try{
            need(owned(),"placement ownership");var c=cases.get(i).getAsJsonObject();String id=c.get("id").getAsString();
            var template=level.getStructureManager().get(Identifier.parse(id)).orElseThrow();var size=c.getAsJsonArray("size");
            need(template.getSize().getX()==size.get(0).getAsInt()&&template.getSize().getY()==size.get(1).getAsInt()&&template.getSize().getZ()==size.get(2).getAsInt(),"data fixer altered bounds "+id);
            need(template.filterBlocks(BlockPos.ZERO,new StructurePlaceSettings(),Blocks.JIGSAW).size()==c.get("jigsaw_count").getAsInt(),"lost authored jigsaws "+id);
            BlockPos.MutableBlockPos p=new BlockPos.MutableBlockPos();
            for(int y=399;y<=432;y++)for(int z=0;z<32;z++)for(int x=0;x<32;x++)level.setBlock(p.set(x,y,z),(y==399?Blocks.STONE:Blocks.AIR).defaultBlockState(),2);
            var settings=new StructurePlaceSettings().setKnownShape(true).setIgnoreEntities(false);
            need(template.placeInWorld(level,AT,AT,settings,RandomSource.create(391800L+i),2),"actual template placement failed "+id);
            int nonair=0;
            for(int y=0;y<template.getSize().getY();y++)for(int z=0;z<template.getSize().getZ();z++)for(int x=0;x<template.getSize().getX();x++){
                var state=level.getBlockState(p.set(x,400+y,z));if(!state.isAir()&&!state.is(Blocks.STRUCTURE_VOID))nonair++;
            }
            need(nonair==c.get("nonair").getAsInt(),"geometry count mismatch "+id+" actual="+nonair+" expected="+c.get("nonair"));
            var path=getDataFolder().toPath().resolve("converted");Files.createDirectories(path);NbtIo.writeCompressed(template.save(new CompoundTag()),path.resolve("wall-"+i+".nbt"));
            JsonObject row=new JsonObject();row.addProperty("id",id);row.add("size",size.deepCopy());row.addProperty("loaded_jigsaws",c.get("jigsaw_count").getAsInt());row.addProperty("placed_nonair",nonair);row.addProperty("pass",true);
            Bukkit.getRegionScheduler().runDelayed(this,world,0,0,t->{try{
                need(owned(),"observation ownership");JsonArray entities=new JsonArray();
                for(Entity entity:level.getEntitiesOfClass(Entity.class,AREA,e->!e.isRemoved())){JsonObject e=new JsonObject();e.addProperty("type",net.minecraft.core.registries.BuiltInRegistries.ENTITY_TYPE.getKey(entity.getType()).toString());e.addProperty("uuid",entity.getUUID().toString());entities.add(e);previous.add(entity);}
                row.add("observed_entities",entities);walls.add(row);persist(null,false);getLogger().info("R3918 WALL "+(i+1)+"/36 "+id+" PASS");next(i+1);
            }catch(Throwable e){finish(e);}},2);
        }catch(Throwable t){finish(t);}
    }
    private void persist(Throwable failure,boolean complete)throws Exception{
        JsonObject out=new JsonObject();out.addProperty("pass",complete&&failure==null&&walls.size()==36);out.addProperty("nonce",nonce);out.addProperty("seed",world==null?0:world.getSeed());out.add("checks",checks);out.add("wall_checks",walls);
        out.addProperty("scope","36 actual direct template loads/placements on owned chunks; retains authored jigsaws. Not full fort assembly, natural frequency or mob combat acceptance.");
        if(failure!=null)out.addProperty("error",failure.toString());getDataFolder().mkdirs();Files.writeString(getDataFolder().toPath().resolve("result.json"),new GsonBuilder().setPrettyPrinting().create().toJson(out)+"\n");
    }
    private synchronized void finish(Throwable failure){
        if(finished)return;finished=true;if(failure!=null)failure.printStackTrace();try{persist(failure,true);}catch(Exception e){e.printStackTrace();failure=e;}
        getLogger().info("R3918 RESOURCE QA "+(failure==null?"PASS":"FAIL")+" nonce="+nonce);
    }
}
