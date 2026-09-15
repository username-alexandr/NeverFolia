import com.google.gson.*;
import java.nio.file.*;
import java.util.*;
import org.bukkit.*;
import org.bukkit.block.BlockFace;
import org.bukkit.block.data.Directional;
import org.bukkit.entity.FallingBlock;
import org.bukkit.event.*;
import org.bukkit.event.server.ServerLoadEvent;
import org.bukkit.plugin.java.JavaPlugin;

/** Disposable runtime physics checks only. This is never a production plugin. */
public final class NeverNetherRoofPhysicsR14 extends JavaPlugin implements Listener {
    private static final int CX=160,CZ=160,X=(CX<<4)+4,Z=(CZ<<4)+4;
    private final JsonArray results=new JsonArray();
    private final Gson gson=new GsonBuilder().setPrettyPrinting().create();
    private FallingBlock falling, dropping;
    private int aboveRoofAttempts;
    private boolean started;
    private volatile boolean forcedHeld;
    @Override public void onEnable() {
        if(!Bukkit.getIp().equals("127.0.0.1") || !Boolean.getBoolean("neverfolia.qa.stageProbe")
            || !Files.isRegularFile(Path.of(".nevernether-r8-isolated")))
            throw new IllegalStateException("New marked loopback QA world required");
        Bukkit.getPluginManager().registerEvents(this,this);
    }
    @EventHandler public void loaded(ServerLoadEvent event) {
        if(started)return;started=true;
        World world=Bukkit.getWorlds().stream().filter(w->w.getEnvironment()==World.Environment.NETHER).findFirst().orElseThrow();
        write("running",null);
        Bukkit.getGlobalRegionScheduler().execute(this,()->{
            try {
                world.setChunkForceLoaded(CX,CZ,true);
                forcedHeld=world.isChunkForceLoaded(CX,CZ);
                world.getChunkAtAsync(CX,CZ,true).whenComplete((chunk,error)->{
                    if(error!=null){write("failed",error);return;}
                    Bukkit.getRegionScheduler().execute(this,world,CX,CZ,()->setup(world));
                });
            } catch(Throwable error) {write("failed",error);}
        });
    }
    @EventHandler public void fallingAttempt(org.bukkit.event.entity.EntityChangeBlockEvent event) {
        if(event.getBlock().getY()>512 && (event.getEntity().equals(falling) || event.getEntity().equals(dropping))) aboveRoofAttempts++;
    }
    private void check(boolean passed,String label) {
        var r=new JsonObject();r.addProperty("phase",label);r.addProperty("x",CX);r.addProperty("z",CZ);r.addProperty("passed",passed);results.add(r);
        if(!passed)throw new AssertionError(label);
    }
    private void setup(World world) {
        try {
            check(Bukkit.isOwnedByCurrentRegion(world,CX,CZ),"owning Folia region");
            check(world.getBlockAt(X,512,Z).getType()==Material.BEDROCK,"roof exists before physics");
            check(forcedHeld,"test chunk held for active fluid ticks");
            // A small isolated test cell below the genuine generated bedrock.
            for(int dx=0;dx<10;dx++)for(int dz=0;dz<6;dz++)for(int y=508;y<=511;y++)
                world.getBlockAt(X+dx,y,Z+dz).setType(y==508?Material.STONE:Material.AIR,false);
            Directional piston=(Directional)Material.PISTON.createBlockData();piston.setFacing(BlockFace.UP);
            world.getBlockAt(X+1,510,Z+1).setBlockData(piston,false);
            world.getBlockAt(X+1,511,Z+1).setType(Material.STONE,false);
            world.getBlockAt(X+2,510,Z+1).setType(Material.REDSTONE_BLOCK,true);
            check(world.getBlockAt(X+1,512,Z+1).getType()==Material.BEDROCK,"powered piston cannot replace roof immediately");
            // Seal a lava chamber; floor is 508, source 511, top is native 512.
            for(int dx=5;dx<=8;dx++)for(int dz=1;dz<=4;dz++)for(int y=509;y<=511;y++)
                if(dx==5||dx==8||dz==1||dz==4)world.getBlockAt(X+dx,y,Z+dz).setType(Material.STONE,false);
            world.getBlockAt(X+6,511,Z+2).setType(Material.LAVA,true);
            var nativeLevel=((org.bukkit.craftbukkit.CraftWorld)world).getHandle();
            nativeLevel.scheduleTick(new net.minecraft.core.BlockPos(X+6,511,Z+2),net.minecraft.world.level.material.Fluids.LAVA,1);
            falling=world.spawnFallingBlock(new Location(world,X+4.5,518,Z+4.5),Material.SAND.createBlockData());
            falling.setDropItem(false);falling.setHurtEntities(false);
            check(falling.isValid(),"falling sand admitted for above-roof negative placement test");
            dropping=world.spawnFallingBlock(new Location(world,X+3.5,518,Z+4.5),Material.SAND.createBlockData());
            dropping.setDropItem(true);dropping.setHurtEntities(false);
            check(dropping.isValid(),"drop-enabled sand admitted for preservation control");
            write("running",null);
            // Simulation is deliberately active here; this protocol is NOT used for order comparisons.
            Bukkit.getRegionScheduler().runDelayed(this,world,CX,CZ,task->finish(world),100L);
        }catch(Throwable t){write("failed",t);}
    }
    private void finish(World world) {
        try {
            check(Bukkit.isOwnedByCurrentRegion(world,CX,CZ),"physics observation on owning region");
            check(!falling.isValid(),"falling sand finished without remaining above roof");
            check(!dropping.isValid(),"drop-enabled sand finished on its original lifecycle path");
            check(aboveRoofAttempts>=2,"both sand entities reached actual above-roof placement events");
            check(world.getBlockAt(X+4,513,Z+4).getType().isAir(),"falling sand did not place at Y513");
            check(world.getBlockAt(X+1,511,Z+1).getType()==Material.STONE,"piston target stayed below roof");
            check(!((org.bukkit.block.data.type.Piston)world.getBlockAt(X+1,510,Z+1).getBlockData()).isExtended(),"piston did not extend into bedrock");
            check(world.getBlockAt(X+6,511,Z+2).getType()==Material.LAVA,"lava source below roof remains");
            check(world.getBlockAt(X+6,510,Z+2).getType()==Material.LAVA,"lava simulation actually flowed downward");
            int roof=0,padding=0;
            for(int dx=0;dx<16;dx++)for(int dz=0;dz<16;dz++){
                check(world.getBlockAt((CX<<4)+dx,512,(CZ<<4)+dz).getType()==Material.BEDROCK,"roof cell "+dx+","+dz);roof++;
                for(int y=513;y<=527;y++){
                    if(!world.getBlockAt((CX<<4)+dx,y,(CZ<<4)+dz).getType().isAir())throw new AssertionError("padding occupied "+dx+","+y+","+dz);
                    padding++;
                }
            }
            check(roof==256&&padding==3840,"all roof and padding cells observed after active ticks");
            write("completed",null);
        }catch(Throwable t){write("failed",t);}
    }
    private synchronized void write(String stage,Throwable error) {
        try {
            Files.createDirectories(getDataFolder().toPath());
            var report=new JsonObject();report.addProperty("schema",1);report.addProperty("probe","NN-ROOF-PHYSICS-R14");
            report.addProperty("stage",stage);report.add("observations",results.deepCopy());
            report.addProperty("simulation_frozen",false);report.addProperty("scheduled_test_ticks",100);report.addProperty("above_roof_placement_attempts",aboveRoofAttempts);
            report.addProperty("client_packet_tested",false);report.addProperty("release_ready",false);
            report.addProperty("scope","One disposable owning-region piston/falling-sand/lava scenario, not full fluid determinism or all gameplay.");
            if(error!=null){report.addProperty("error",error.toString());getLogger().log(java.util.logging.Level.SEVERE,"Roof physics QA failed",error);}
            Path temp=getDataFolder().toPath().resolve("report.tmp");Files.writeString(temp,gson.toJson(report));
            Files.move(temp,getDataFolder().toPath().resolve("report.json"),StandardCopyOption.REPLACE_EXISTING,StandardCopyOption.ATOMIC_MOVE);
            getLogger().info("NN-ROOF-PHYSICS "+stage+" checks="+results.size());
        }catch(Exception failure){getLogger().log(java.util.logging.Level.SEVERE,"Cannot write QA report",failure);}
    }
}
