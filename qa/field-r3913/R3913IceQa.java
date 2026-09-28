import com.google.gson.*;
import java.io.*;
import java.lang.reflect.*;
import java.nio.file.*;
import java.util.*;
import java.util.zip.GZIPOutputStream;
import net.minecraft.core.BlockPos;
import net.minecraft.core.registries.Registries;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.level.ChunkPos;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.LiquidBlock;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.chunk.*;
import net.minecraft.world.level.chunk.status.ChunkStatus;
import org.bukkit.Bukkit;
import org.bukkit.World;
import org.bukkit.NamespacedKey;
import org.bukkit.craftbukkit.CraftWorld;
import org.bukkit.event.*;
import org.bukkit.event.server.ServerLoadEvent;
import org.bukkit.persistence.PersistentDataType;
import org.bukkit.plugin.java.JavaPlugin;

/** Detached real ProtoChunk fixtures plus separately requested natural chunks.
 * No fixtures are installed into a user's world. Region ownership is respected
 * for sampling live chunks. This does not claim screenshot equivalence.
 */
public final class R3913IceQa extends JavaPlugin implements Listener {
    private final String nonce=System.getProperty("neverfolia.iceQaNonce","");
    private final boolean fixtures=Boolean.getBoolean("neverfolia.iceQaFixtures");
    private World world;private ServerLevel level;private boolean started,finished;private int index;
    private final JsonArray rows=new JsonArray();private final List<int[]> targets=new ArrayList<>();
    private static final String[] NAMES={"ice_in_water","packed_ice_in_water","blue_ice_in_water","ice_below_magma","rock_cap_retained","dry_face_retained","floor_contact_retained","surface_buffer_retained","surface_connected_retained","large_component_retained","chunk_boundary_retained","persisted_mine_retained","structure_reference_retained","light_chunk_skipped","full_chunk_skipped","negative_chunk","flowing_neighbours_preserved","frosted_ice_retained","bottom_boundary_retained"};
    @Override public void onEnable(){Bukkit.getPluginManager().registerEvents(this,this);}
    @EventHandler public void loaded(ServerLoadEvent e){
        if(started)return;started=true;
        try{
            need(!nonce.isBlank(),"Missing nonce");world=Bukkit.getWorlds().stream().filter(w->w.getEnvironment()==World.Environment.NORMAL).findFirst().orElseThrow();
            need(world.getSeed()==-4651369264513492755L,"Wrong actual seed");level=((CraftWorld)world).getHandle();
            if(fixtures){world.getChunkAtAsync(0,0,true).whenComplete((c,error)->{if(error!=null){finish(error);return;}scheduleFixture();});}
            else{
                TreeMap<String,int[]> chosen=new TreeMap<>();
                for(int[] center:new int[][]{{-189,-223},{-169,-253},{-197,-217}})for(int dz=-1;dz<=1;dz++)for(int dx=-1;dx<=1;dx++){
                    int x=center[0]+dx,z=center[1]+dz;chosen.put(x+","+z,new int[]{x,z});
                }
                targets.addAll(chosen.values());need(targets.size()==27,"Target drift");next();
            }
        }catch(Throwable t){finish(t);}
    }
    private void scheduleFixture(){
        Bukkit.getRegionScheduler().runDelayed(this,world,0,0,task->{
            try{if(index==NAMES.length){finish(null);return;}test(index);index++;scheduleFixture();}
            catch(Throwable error){finish(error);}
        },1L);
    }
    private ProtoChunk fresh(int cx,int cz)throws Exception{
        List<Method> factories=Arrays.stream(level.getClass().getMethods()).filter(m->m.getParameterCount()==0&&m.getReturnType().getSimpleName().equals("PalettedContainerFactory")).toList();
        need(factories.size()==1,"Palette factory ambiguity");Object factory=factories.getFirst().invoke(level);
        List<Constructor<?>> constructors=Arrays.stream(ProtoChunk.class.getConstructors()).filter(c->c.getParameterCount()==5&&c.getParameterTypes()[0]==ChunkPos.class&&c.getParameterTypes()[3].isInstance(factory)).toList();
        need(constructors.size()==1,"ProtoChunk constructor ambiguity");
        ProtoChunk chunk=(ProtoChunk)constructors.getFirst().newInstance(new ChunkPos(cx,cz),UpgradeData.EMPTY,level,factory,null);
        need(chunk.getMinY()==-512&&chunk.getHeight()==1024,"Wrong envelope");
        BlockPos.MutableBlockPos p=new BlockPos.MutableBlockPos();
        for(int y=48;y<=129;y++)for(int z=0;z<16;z++)for(int x=0;x<16;x++)chunk.setBlockState(p.set(cx*16+x,y,cz*16+z),Blocks.WATER.defaultBlockState(),0);
        chunk.setPersistedStatus(ChunkStatus.FEATURES);return chunk;
    }
    private static void put(ChunkAccess c,int x,int y,int z,BlockState s){c.setBlockState(new BlockPos(c.getPos().getMinBlockX()+x,y,c.getPos().getMinBlockZ()+z),s,0);}
    private static BlockState[] capture(ChunkAccess c){
        BlockState[] data=new BlockState[1024*256];BlockPos.MutableBlockPos p=new BlockPos.MutableBlockPos();
        for(int y=-512;y<=511;y++)for(int z=0;z<16;z++)for(int x=0;x<16;x++)data[((y+512)<<8)|(z<<4)|x]=c.getBlockState(p.set(c.getPos().getMinBlockX()+x,y,c.getPos().getMinBlockZ()+z));return data;
    }
    private void test(int which)throws Exception{
        ProtoChunk c=fresh(which==15?-1:0,which==15?-1:0);int expected=1;
        put(c,8,64,8,Blocks.ICE.defaultBlockState());
        switch(which){
            case 1 -> put(c,8,64,8,Blocks.PACKED_ICE.defaultBlockState());
            case 2 -> put(c,8,64,8,Blocks.BLUE_ICE.defaultBlockState());
            case 3 -> {put(c,8,65,8,Blocks.ICE.defaultBlockState());put(c,8,66,8,Blocks.MAGMA_BLOCK.defaultBlockState());expected=2;}
            case 4 -> {put(c,8,65,8,Blocks.STONE.defaultBlockState());expected=0;}
            case 5 -> {put(c,9,64,8,Blocks.AIR.defaultBlockState());expected=0;}
            case 6 -> {put(c,8,63,8,Blocks.STONE.defaultBlockState());expected=0;}
            case 7 -> {put(c,8,64,8,Blocks.WATER.defaultBlockState());put(c,8,112,8,Blocks.ICE.defaultBlockState());expected=0;}
            case 8 -> {for(int y=64;y<=128;y++)put(c,8,y,8,Blocks.ICE.defaultBlockState());expected=0;}
            case 9 -> {for(int y=64;y<67;y++)for(int z=6;z<=10;z++)for(int x=6;x<=10;x++)put(c,x,y,z,Blocks.PACKED_ICE.defaultBlockState());expected=0;}
            case 10 -> {put(c,8,64,8,Blocks.WATER.defaultBlockState());put(c,0,64,8,Blocks.ICE.defaultBlockState());expected=0;}
            case 11 -> {c.persistentDataContainer.set(new NamespacedKey("neverfolia","dry_mines_r12"),PersistentDataType.INTEGER_ARRAY,new int[]{1,1,6,62,6,10,66,10});c.neverOverworldDryMineMaskR12=null;expected=0;}
            case 12 -> {var registry=level.registryAccess().lookupOrThrow(Registries.STRUCTURE);var s=registry.iterator().next();c.getAllReferences().put(s,new it.unimi.dsi.fastutil.longs.LongOpenHashSet(new long[]{ChunkPos.asLong(0,0)}));expected=0;}
            case 13 -> {c.setPersistedStatus(ChunkStatus.LIGHT);expected=0;}
            case 14 -> {c.setPersistedStatus(ChunkStatus.FULL);expected=0;}
            case 16 -> put(c,9,64,8,Blocks.WATER.defaultBlockState().setValue(LiquidBlock.LEVEL,5));
            case 17 -> {put(c,8,64,8,Blocks.FROSTED_ICE.defaultBlockState());expected=0;}
            case 18 -> {put(c,8,64,8,Blocks.WATER.defaultBlockState());put(c,8,-511,8,Blocks.ICE.defaultBlockState());expected=0;}
        }
        BlockState[] before=capture(c);int[] pdc=c.persistentDataContainer.get(new NamespacedKey("neverfolia","dry_mines_r12"),PersistentDataType.INTEGER_ARRAY);
        int changed=NeverOverworldIceFragmentsR3913.apply(level,c);need(changed==expected,NAMES[which]+": expected "+expected+", got "+changed);
        BlockState[] after=capture(c);int observed=0;
        for(int i=0;i<before.length;i++)if(before[i]!=after[i]){
            need(NeverOverworldIceFragmentsR3913.ice(before[i])&&after[i]==Blocks.WATER.defaultBlockState(),"Unexpected block mutation");observed++;
        }
        need(observed==changed,"Write count mismatch");need(Arrays.equals(pdc,c.persistentDataContainer.get(new NamespacedKey("neverfolia","dry_mines_r12"),PersistentDataType.INTEGER_ARRAY)),"PDC changed");
        need(NeverOverworldIceFragmentsR3913.apply(level,c)==0,"Not idempotent");
        JsonObject row=new JsonObject();row.addProperty("name",NAMES[which]);row.addProperty("pass",true);row.addProperty("ice_to_water",changed);row.addProperty("other_changes",0);rows.add(row);
        getLogger().info("ICE_FIXTURE "+NAMES[which]+" PASS");
    }
    private void next(){
        if(finished)return;if(index==targets.size()){finish(null);return;}
        int[] t=targets.get(index);world.getChunkAtAsync(t[0],t[1],true).whenComplete((chunk,error)->{
            if(error!=null){finish(error);return;}
            Bukkit.getRegionScheduler().execute(this,world,t[0],t[1],()->{
                try{
                    ChunkAccess c=level.getChunkAt(new BlockPos(t[0]*16,64,t[1]*16));BlockState[] states=capture(c);
                    LinkedHashMap<String,Integer> palette=new LinkedHashMap<>();int[] ids=new int[states.length];int ice=0;
                    for(int i=0;i<states.length;i++){String s=states[i].toString();ids[i]=palette.computeIfAbsent(s,k->palette.size());if(NeverOverworldIceFragmentsR3913.ice(states[i]))ice++;}
                    Path dir=getDataFolder().toPath();Files.createDirectories(dir);
                    try(DataOutputStream out=new DataOutputStream(new GZIPOutputStream(Files.newOutputStream(dir.resolve(t[0]+"_"+t[1]+".blocks.gz"))))){
                        out.writeUTF("R3913S1");out.writeInt(t[0]);out.writeInt(t[1]);out.writeInt(-512);out.writeInt(1024);out.writeInt(palette.size());
                        for(String s:palette.keySet())out.writeUTF(s);out.writeInt(ids.length);for(int id:ids)out.writeInt(id);
                    }
                    JsonObject row=new JsonObject();row.addProperty("chunk_x",t[0]);row.addProperty("chunk_z",t[1]);row.addProperty("ice_blocks",ice);rows.add(row);index++;
                    getLogger().info("ICE_SAMPLE "+index+"/"+targets.size()+" "+t[0]+","+t[1]+" ice="+ice);Bukkit.getGlobalRegionScheduler().execute(this,()->next());
                }catch(Throwable failure){finish(failure);}
            });
        });
    }
    private static void need(boolean ok,String why){if(!ok)throw new AssertionError(why);}
    private synchronized void finish(Throwable error){
        if(finished)return;finished=true;JsonObject r=new JsonObject();r.addProperty("pass",error==null);r.addProperty("nonce",nonce);r.addProperty("fixtures",fixtures);
        r.addProperty("seed",world==null?0:world.getSeed());r.addProperty("completed",rows.size());r.add("rows",rows);r.addProperty("visual_tested",false);
        if(error!=null){r.addProperty("error",error.toString());error.printStackTrace();}
        try{getDataFolder().mkdirs();Files.writeString(getDataFolder().toPath().resolve("result.json"),new GsonBuilder().setPrettyPrinting().create().toJson(r));}catch(Exception failure){failure.printStackTrace();error=failure;}
        getLogger().info("R3913 QA "+(error==null?"PASS ":"FAIL ")+nonce);
    }
}
