import cc.neverland.client.EnchantmentVisibility;
import com.google.gson.*;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.security.MessageDigest;
import java.util.*;
import org.bukkit.*;
import org.bukkit.block.data.Levelled;
import org.bukkit.craftbukkit.CraftWorld;
import org.bukkit.event.*;
import org.bukkit.event.server.ServerLoadEvent;
import org.bukkit.plugin.java.JavaPlugin;
import net.minecraft.core.registries.Registries;
import net.minecraft.resources.Identifier;
import net.minecraft.resources.ResourceKey;

/** New isolated CI worlds only. Observes natural generated chunks, not fixtures.
 * No blocks/entities/spawners are placed. No player combat is simulated.
 */
public final class R395QaPlugin extends JavaPlugin implements Listener {
    private World world;
    private final List<int[]> targets=new ArrayList<>();
    private final JsonArray rows=new JsonArray(),enchants=new JsonArray();
    private int index;
    private boolean started,finished;
    private static final int LOW=-511,HIGH=128;
    @Override public void onEnable(){Bukkit.getPluginManager().registerEvents(this,this);}
    @EventHandler public void loaded(ServerLoadEvent event) {
        if(started)return;started=true;
        try {
            world=Bukkit.getWorlds().stream().filter(w->w.getEnvironment()==World.Environment.NORMAL).findFirst().orElseThrow();
            if(world.getSeed()!=-4651369264513492755L)throw new AssertionError("Wrong actual seed");
            checkEnchantments();
            int[][] centers={{7,1},{1,-4},{-197,-217},{-169,-250},{-189,-223},{-1699,-769}};
            TreeMap<String,int[]> selected=new TreeMap<>();
            for(int[] c:centers)for(int dz=-1;dz<=1;dz++)for(int dx=-1;dx<=1;dx++) {
                int cx=c[0]+dx,cz=c[1]+dz;selected.put(cx+","+cz,new int[]{cx,cz});
            }
            targets.addAll(selected.values());
            if(Boolean.getBoolean("neverfolia.qaReverse"))Collections.reverse(targets);
            if(targets.size()!=54)throw new AssertionError("Wrong target count");
            Bukkit.getGlobalRegionScheduler().execute(this,()->next());
        } catch(Throwable error){finish(error);}
    }
    private void checkEnchantments()throws Exception {
        var registry=((CraftWorld)world).getHandle().registryAccess().lookupOrThrow(Registries.ENCHANTMENT);
        JsonObject expected;
        try(var reader=new InputStreamReader(Objects.requireNonNull(getResource("expected-enchants.json")),StandardCharsets.UTF_8)) {
            expected=JsonParser.parseReader(reader).getAsJsonObject();
        }
        for(var entry:expected.entrySet()) {
            String[] id=entry.getKey().split(":",2);
            var holder=registry.getOrThrow(ResourceKey.create(Registries.ENCHANTMENT,Identifier.fromNamespaceAndPath(id[0],id[1])));
            boolean actual=EnchantmentVisibility.show(holder),want=entry.getValue().getAsBoolean();
            if(actual!=want)throw new AssertionError("Unexpected visibility: "+entry.getKey());
            JsonObject row=new JsonObject();row.addProperty("id",entry.getKey());row.addProperty("visible",actual);enchants.add(row);
        }
        if(enchants.size()!=35)throw new AssertionError("Expected 16 technical, 17 gameplay, 2 vanilla checks");
    }
    private void next() {
        if(finished)return;
        if(index==targets.size()){finish(null);return;}
        int[] target=targets.get(index);int cx=target[0],cz=target[1];
        world.getChunkAtAsync(cx,cz,true).whenComplete((chunk,error)->{
            if(error!=null){finish(error);return;}
            Bukkit.getRegionScheduler().execute(this,world,cx,cz,()->{
                try {
                    ChunkSnapshot snapshot=chunk.getChunkSnapshot(false,true,false);
                    rows.add(sample(snapshot,cx,cz));index++;
                    getLogger().info("R395 SAMPLE "+index+"/"+targets.size()+" "+cx+","+cz);
                    Bukkit.getGlobalRegionScheduler().execute(this,()->next());
                }catch(Throwable failure){finish(failure);}
            });
        });
    }
    private JsonObject sample(ChunkSnapshot snapshot,int cx,int cz)throws Exception {
        JsonObject row=new JsonObject(),counts=new JsonObject();Map<String,Integer> types=new TreeMap<>();
        JsonArray airExamples=new JsonArray(),iceExamples=new JsonArray();
        int isolatedAir=0,ice=0,isolatedIce=0;byte[] water=new byte[(HIGH-LOW+1)*256];
        for(int y=LOW;y<=HIGH;y++)for(int z=0;z<16;z++)for(int x=0;x<16;x++) {
            Material type=snapshot.getBlockType(x,y,z);String name=type.getKey().toString();types.merge(name,1,Integer::sum);
            int k=((y-LOW)<<8)|(z<<4)|x;
            if(type==Material.WATER)water[k]=(byte)(1+((Levelled)snapshot.getBlockData(x,y,z)).getLevel());
            else if(aquatic(type))water[k]=1;
            boolean frozen=type==Material.ICE||type==Material.PACKED_ICE||type==Material.BLUE_ICE||type==Material.FROSTED_ICE;
            if(frozen)ice++;
            if((type.isAir()||frozen)&&x>0&&x<15&&z>0&&z<15&&y>LOW&&y<HIGH) {
                boolean surrounded=aquatic(snapshot.getBlockType(x-1,y,z))&&aquatic(snapshot.getBlockType(x+1,y,z))
                    &&aquatic(snapshot.getBlockType(x,y-1,z))&&aquatic(snapshot.getBlockType(x,y+1,z))
                    &&aquatic(snapshot.getBlockType(x,y,z-1))&&aquatic(snapshot.getBlockType(x,y,z+1));
                if(surrounded) {
                    JsonObject point=new JsonObject();point.addProperty("x",cx*16+x);point.addProperty("y",y);point.addProperty("z",cz*16+z);point.addProperty("block",name);
                    if(type.isAir()){isolatedAir++;if(airExamples.size()<16)airExamples.add(point);}
                    else {isolatedIce++;if(iceExamples.size()<16)iceExamples.add(point);}
                }
            }
        }
        types.forEach(counts::addProperty);row.addProperty("chunk_x",cx);row.addProperty("chunk_z",cz);
        row.addProperty("min_y",LOW);row.addProperty("max_y",HIGH);row.add("block_counts",counts);
        row.addProperty("water_sha256",HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(water)));
        row.addProperty("single_air_with_six_aquatic_neighbours",isolatedAir);row.add("air_examples",airExamples);
        row.addProperty("ice_blocks",ice);row.addProperty("single_ice_with_six_aquatic_neighbours",isolatedIce);row.add("ice_examples",iceExamples);
        return row;
    }
    private static boolean aquatic(Material type) {
        return type==Material.WATER||type==Material.BUBBLE_COLUMN||type==Material.KELP||type==Material.KELP_PLANT||type==Material.SEAGRASS||type==Material.TALL_SEAGRASS;
    }
    private synchronized void finish(Throwable error) {
        if(finished)return;finished=true;
        JsonObject result=new JsonObject();result.addProperty("pass",error==null);
        result.addProperty("scope","54 naturally generated chunks; exact runtime enchant visibility predicates; no player, combat, full closure or screenshot equivalence proof");
        result.addProperty("seed",world==null?0:world.getSeed());result.addProperty("completed_chunks",rows.size());result.add("chunks",rows);result.add("enchantment_visibility",enchants);
        result.addProperty("reverse_order",Boolean.getBoolean("neverfolia.qaReverse"));
        if(error!=null){result.addProperty("error",error.toString());error.printStackTrace();}
        try {getDataFolder().mkdirs();Files.writeString(getDataFolder().toPath().resolve("result.json"),new GsonBuilder().setPrettyPrinting().create().toJson(result));}
        catch(Exception failure){failure.printStackTrace();error=failure;}
        getLogger().info("R395 NATURAL QA "+(error==null?"PASS":"FAIL"));
    }
}
