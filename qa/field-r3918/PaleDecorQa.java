import com.google.gson.*;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.*;
import org.bukkit.Bukkit;
import org.bukkit.craftbukkit.CraftWorld;
import org.bukkit.event.*;
import org.bukkit.event.server.ServerLoadEvent;
import org.bukkit.plugin.java.JavaPlugin;
import net.minecraft.core.BlockPos;
import net.minecraft.core.registries.Registries;
import net.minecraft.resources.*;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.levelgen.structure.pools.JigsawPlacement;

/** Disposable fixture hosts cropped from four actual parent connector contexts.
 * The target decoration pool, authored banner NBT and processors are not
 * replaced in the QA pack. This is not full natural-building placement.
 */
public final class PaleDecorQa extends JavaPlugin implements Listener {
    private final String nonce=System.getProperty("neverfolia.qaNonce","");
    private final boolean baseline=Boolean.getBoolean("neverfolia.qaBaseline");
    private final boolean reload=Boolean.getBoolean("neverfolia.qaReload");
    private final JsonArray rows=new JsonArray();
    private JsonArray cases;private org.bukkit.World world;private ServerLevel level;
    private boolean started,finished;
    private static final BlockPos AT=new BlockPos(8,400,8);
    private static void need(boolean v,String s){if(!v)throw new AssertionError(s);}
    @Override public void onEnable(){Bukkit.getPluginManager().registerEvents(this,this);}
    @EventHandler public void loaded(ServerLoadEvent event){
        if(started)return;started=true;
        try {
            need(!nonce.isBlank(),"missing nonce");
            try(var r=new InputStreamReader(Objects.requireNonNull(getResource("cases.json")),StandardCharsets.UTF_8)){cases=JsonParser.parseReader(r).getAsJsonArray();}
            need(cases.size()==4,"wrong parent connector coverage");
            world=Bukkit.getWorlds().stream().filter(w->w.getEnvironment()==org.bukkit.World.Environment.NORMAL).findFirst().orElseThrow();
            level=((CraftWorld)world).getHandle();need(world.getSeed()==-4651369264513492755L,"wrong seed");
            world.getChunkAtAsync(0,0,true).whenComplete((c,e)->{if(e!=null){finish(e);return;}Bukkit.getRegionScheduler().execute(this,world,0,0,()->{try {if(reload)verifyReload();else place(0);}catch(Throwable x){finish(x);}});});
        }catch(Throwable e){finish(e);}
    }
    private JsonArray snapshot(){
        JsonArray result=new JsonArray();BlockPos.MutableBlockPos p=new BlockPos.MutableBlockPos();
        for(int y=397;y<=412;y++)for(int z=0;z<16;z++)for(int x=0;x<16;x++)result.add(level.getBlockState(p.set(x,y,z)).toString());
        return result;
    }
    private void verifyReload()throws Exception {
        need(ca.spottedleaf.moonrise.common.util.TickThread.isTickThreadFor(level,AT),"wrong reload owner");
        JsonArray saved=JsonParser.parseString(Files.readString(getDataFolder().toPath().resolve("saved-scene.json"))).getAsJsonArray();
        JsonArray now=snapshot();need(saved.size()==4096&&now.equals(saved),"saved scene changed after restart");
        JsonObject r=new JsonObject();r.addProperty("reload_equal",true);r.addProperty("positions",4096);rows.add(r);finish(null);
    }
    private void place(int i){
        try {
            if(i==cases.size()){
                Files.writeString(getDataFolder().toPath().resolve("saved-scene.json"),snapshot().toString());finish(null);return;
            }
            need(ca.spottedleaf.moonrise.common.util.TickThread.isTickThreadFor(level,AT),"wrong fixture owner");
            BlockPos.MutableBlockPos p=new BlockPos.MutableBlockPos();
            for(int y=397;y<=412;y++)for(int z=0;z<16;z++)for(int x=0;x<16;x++)level.setBlock(p.set(x,y,z),(y==398?Blocks.STONE:Blocks.AIR).defaultBlockState(),2);
            level.random.setSeed(518004L+i);
            var pool=level.registryAccess().lookupOrThrow(Registries.TEMPLATE_POOL).getOrThrow(ResourceKey.create(Registries.TEMPLATE_POOL,Identifier.parse("neverfolia_qa:pale/case_"+i)));
            need(JigsawPlacement.generateJigsaw(level,pool,Identifier.parse("neverfolia_qa:pale_anchor"),1,AT,false),"root placement failed "+i);
            Bukkit.getRegionScheduler().runDelayed(this,world,0,0,t->{try {
                int banners=0,signs=0,jigsaws=0;BlockPos.MutableBlockPos q=new BlockPos.MutableBlockPos();
                for(int y=397;y<=412;y++)for(int z=0;z<16;z++)for(int x=0;x<16;x++){
                    var state=level.getBlockState(q.set(x,y,z));if(state.is(Blocks.WHITE_BANNER))banners++;if(state.is(Blocks.BIRCH_WALL_SIGN))signs++;if(state.is(Blocks.JIGSAW))jigsaws++;
                }
                JsonObject c=cases.get(i).getAsJsonObject();int added=baseline?0:1;
                JsonObject row=c.deepCopy();row.addProperty("observed_banners",banners);row.addProperty("observed_signs",signs);row.addProperty("remaining_jigsaws",jigsaws);row.add("states",snapshot());rows.add(row);
                need(jigsaws==0,"unfinished source joints "+i);
                need(banners==c.get("baseline_banners").getAsInt()+added,"banner missing/excess: case="+i+" actual="+banners);
                need(signs==c.get("baseline_signs").getAsInt()+added,"sign missing/excess: case="+i+" actual="+signs);
                row.addProperty("pass",true);persist(null,false);getLogger().info("R3918 PALE CASE "+i+" banners="+banners+" signs="+signs);
                Bukkit.getRegionScheduler().runDelayed(this,world,0,0,next->place(i+1),2);
            }catch(Throwable e){finish(e);}},5);
        }catch(Throwable e){finish(e);}
    }
    private void persist(Throwable e,boolean complete)throws Exception {
        JsonObject result=new JsonObject();result.addProperty("pass",complete&&e==null);result.addProperty("nonce",nonce);result.addProperty("seed",world.getSeed());result.addProperty("baseline",baseline);result.addProperty("reload",reload);result.add("checks",rows);
        result.addProperty("scope","Source-cropped parent contexts with original decoration child pool; not natural distribution or whole-building regression");if(e!=null)result.addProperty("error",e.toString());
        getDataFolder().mkdirs();Files.writeString(getDataFolder().toPath().resolve("result.json"),new GsonBuilder().setPrettyPrinting().create().toJson(result));
    }
    private synchronized void finish(Throwable e){if(finished)return;finished=true;if(e!=null)e.printStackTrace();try{persist(e,true);}catch(Exception x){x.printStackTrace();e=x;}getLogger().info("R3918 PALE QA "+(e==null?"PASS":"FAIL")+" nonce="+nonce);}
}
