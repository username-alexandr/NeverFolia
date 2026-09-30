import com.google.gson.*;
import java.nio.file.Files;
import java.util.*;
import org.bukkit.*;
import org.bukkit.block.data.Levelled;
import org.bukkit.event.*;
import org.bukkit.event.server.ServerLoadEvent;
import org.bukkit.plugin.java.JavaPlugin;

public final class R3925NativeSeaQa extends JavaPlugin implements Listener {
    private static final int SEA_LEVEL=128, TOP_WATER_Y=127, LOW=-96, HIGH=192;
    private static final long SEED=-4651369264513492755L;
    private final List<int[]> targets=new ArrayList<>();
    private final JsonArray rows=new JsonArray();
    private World world; private int index; private boolean started,finished;

    private static final int[][] OLD_CENTERS={{7,1},{1,-4},{-197,-217},{-169,-250},{-189,-223},{-1699,-769}};
    private static final int[][] OLD_SCREENSHOT_CHUNKS={
        {8,1},{6,2},{6,1},{1,0},{3,2},{4,-3},{1,-2},{1,-5},{1,-4},{0,-5},{-3,-3},{-2,5},{6,-1},
        {-191,-216},{-181,-227},{-183,-229},{-183,-233},{-185,-236},{-1698,-771},{-1701,-766},{-1698,-769},
        {-196,-216},{-197,-217},{-198,-217},{-199,-219},{-170,-252},{-168,-249},{-161,-239},{-189,-223},{-169,-253}
    };
    // Chunks visible in the 2026-09-30 manual screenshots, plus radius 1 is added below.
    private static final int[][] USER_SCREENSHOT_CHUNKS={
        {-3,0},{-2,0},{-3,-1},{-4,-1},{-3,-3},{-2,-2},{-1,-3},{0,-3},{3,-5},{4,-4},{5,0},{5,2},{4,0}
    };

    @Override public void onEnable(){Bukkit.getPluginManager().registerEvents(this,this);}
    @EventHandler public void loaded(ServerLoadEvent event){
        if(started)return;started=true;
        try{
            world=Bukkit.getWorlds().stream().filter(w->w.getEnvironment()==World.Environment.NORMAL).findFirst().orElseThrow();
            if(world.getSeed()!=SEED)throw new AssertionError("Wrong seed "+world.getSeed());
            TreeMap<String,int[]> selected=new TreeMap<>();
            for(int[] c:OLD_CENTERS)for(int dz=-1;dz<=1;dz++)for(int dx=-1;dx<=1;dx++)put(selected,c[0]+dx,c[1]+dz);
            for(int[] c:OLD_SCREENSHOT_CHUNKS)put(selected,c[0],c[1]);
            for(int[] c:USER_SCREENSHOT_CHUNKS)for(int dz=-1;dz<=1;dz++)for(int dx=-1;dx<=1;dx++)put(selected,c[0]+dx,c[1]+dz);
            targets.addAll(selected.values());
            Bukkit.getGlobalRegionScheduler().execute(this,this::next);
        }catch(Throwable t){finish(t);}
    }
    private static void put(Map<String,int[]> m,int x,int z){m.put(x+","+z,new int[]{x,z});}

    private void next(){
        if(finished)return;
        if(index==targets.size()){finish(null);return;}
        int[] q=targets.get(index);int cx=q[0],cz=q[1];
        world.getChunkAtAsync(cx,cz,true).whenComplete((chunk,error)->{
            if(error!=null){finish(error);return;}
            Bukkit.getRegionScheduler().execute(this,world,cx,cz,()->{
                try{
                    ChunkSnapshot s=chunk.getChunkSnapshot(false,true,false);
                    rows.add(sample(s,cx,cz));index++;
                    getLogger().info("R3925 SAMPLE "+index+"/"+targets.size()+" "+cx+","+cz);
                    Bukkit.getGlobalRegionScheduler().execute(this,this::next);
                }catch(Throwable t){finish(t);}
            });
        });
    }

    private JsonObject sample(ChunkSnapshot s,int cx,int cz){
        JsonObject row=new JsonObject();
        int wetColumns=0,airGapCells=0,surfaceGapColumns=0,livingFloorColumns=0,flowingWaterCells=0,waterAtOrAboveSea=0;
        JsonArray gapExamples=new JsonArray(),livingExamples=new JsonArray(),flowExamples=new JsonArray();
        JsonArray west=new JsonArray(),east=new JsonArray(),north=new JsonArray(),south=new JsonArray();

        for(int z=0;z<16;z++)for(int x=0;x<16;x++){
            int solid=solidSurface(s,x,z);
            if(x==0)west.add(solid);if(x==15)east.add(solid);if(z==0)north.add(solid);if(z==15)south.add(solid);

            Material top=s.getBlockType(x,TOP_WATER_Y,z);
            boolean frozenTop=frozen(top);
            boolean wetTop=aquatic(top)||frozenTop;
            if(wetTop){
                wetColumns++;
                int start=frozenTop?TOP_WATER_Y-1:TOP_WATER_Y;
                boolean foundFloor=false;
                for(int y=start;y>=LOW;y--){
                    Material type=s.getBlockType(x,y,z);
                    if(type.isAir()){
                        airGapCells++;
                        if(gapExamples.size()<24)gapExamples.add(point(cx,x,y,cz,z,type));
                        continue;
                    }
                    if(type==Material.WATER){
                        if(s.getBlockData(x,y,z) instanceof Levelled l && l.getLevel()!=0){
                            flowingWaterCells++;
                            if(flowExamples.size()<24)flowExamples.add(point(cx,x,y,cz,z,type));
                        }
                        continue;
                    }
                    if(aquatic(type)||frozen(type))continue;
                    foundFloor=true;
                    if(livingFloor(type)){
                        livingFloorColumns++;
                        if(livingExamples.size()<24)livingExamples.add(point(cx,x,y,cz,z,type));
                    }
                    break;
                }
                if(!foundFloor)throw new AssertionError("No floor in wet column "+cx+","+cz+" local "+x+","+z);
            }else if(top.isAir()){
                // If the first non-air cell below the native sea surface is water,
                // this column contains a dry cap/gap in what should be ocean volume.
                for(int y=TOP_WATER_Y-1;y>=LOW;y--){
                    Material type=s.getBlockType(x,y,z);
                    if(type.isAir())continue;
                    if(aquatic(type)||type==Material.WATER||frozen(type)){
                        surfaceGapColumns++;
                        if(gapExamples.size()<24)gapExamples.add(point(cx,x,TOP_WATER_Y,cz,z,top));
                    }
                    break;
                }
            }

            for(int y=SEA_LEVEL;y<=HIGH;y++){
                if(s.getBlockType(x,y,z)==Material.WATER)waterAtOrAboveSea++;
            }
        }

        row.addProperty("chunk_x",cx);row.addProperty("chunk_z",cz);
        row.addProperty("wet_columns",wetColumns);
        row.addProperty("air_gap_cells_in_wet_columns",airGapCells);
        row.addProperty("surface_gap_columns",surfaceGapColumns);
        row.addProperty("living_floor_columns",livingFloorColumns);
        row.addProperty("flowing_water_cells_in_wet_columns",flowingWaterCells);
        row.addProperty("water_cells_y128_or_above",waterAtOrAboveSea);
        row.add("gap_examples",gapExamples);row.add("living_floor_examples",livingExamples);row.add("flow_examples",flowExamples);
        row.add("west_solid_edge",west);row.add("east_solid_edge",east);row.add("north_solid_edge",north);row.add("south_solid_edge",south);
        return row;
    }

    private static int solidSurface(ChunkSnapshot s,int x,int z){
        for(int y=HIGH;y>=LOW;y--){
            Material type=s.getBlockType(x,y,z);
            if(type.isAir()||aquatic(type)||frozen(type))continue;
            return y;
        }
        return LOW-1;
    }
    private static boolean livingFloor(Material t){
        return t==Material.GRASS_BLOCK||t==Material.PODZOL||t==Material.MYCELIUM||t==Material.MOSS_BLOCK
            ||t==Material.DIRT_PATH||t==Material.ROOTED_DIRT||t==Material.SNOW_BLOCK;
    }
    private static boolean aquatic(Material t){
        return t==Material.WATER||t==Material.BUBBLE_COLUMN||t==Material.KELP||t==Material.KELP_PLANT
            ||t==Material.SEAGRASS||t==Material.TALL_SEAGRASS||t==Material.SEA_PICKLE;
    }
    private static boolean frozen(Material t){
        return t==Material.ICE||t==Material.PACKED_ICE||t==Material.BLUE_ICE||t==Material.FROSTED_ICE;
    }
    private static JsonObject point(int cx,int lx,int y,int cz,int lz,Material t){
        JsonObject p=new JsonObject();p.addProperty("x",cx*16+lx);p.addProperty("y",y);p.addProperty("z",cz*16+lz);
        p.addProperty("block",t.getKey().toString());return p;
    }

    private synchronized void finish(Throwable error){
        if(finished)return;finished=true;
        JsonObject out=new JsonObject();out.addProperty("pass",error==null);out.addProperty("seed",world==null?0:world.getSeed());
        out.addProperty("sea_level",SEA_LEVEL);out.addProperty("top_source_water_y",TOP_WATER_Y);
        out.addProperty("target_chunks",targets.size());out.addProperty("completed_chunks",rows.size());out.add("chunks",rows);
        if(error!=null){out.addProperty("error",error.toString());error.printStackTrace();}
        try{getDataFolder().mkdirs();Files.writeString(getDataFolder().toPath().resolve("result.json"),new GsonBuilder().setPrettyPrinting().create().toJson(out));}
        catch(Exception e){e.printStackTrace();}
        getLogger().info("R3925 NATIVE SEA QA "+(error==null?"PASS":"FAIL"));
        Bukkit.getGlobalRegionScheduler().runDelayed(this,task->Bukkit.shutdown(),20L);
    }
}
