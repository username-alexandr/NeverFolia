import ca.spottedleaf.concurrentutil.util.Priority;
import com.google.gson.*;
import java.io.*;
import java.nio.file.*;
import java.security.MessageDigest;
import java.util.*;
import java.util.concurrent.*;
import java.util.zip.GZIPOutputStream;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.properties.Property;
import net.minecraft.world.level.chunk.ChunkAccess;
import net.minecraft.world.level.chunk.status.ChunkStatus;
import org.bukkit.Bukkit;
import org.bukkit.craftbukkit.CraftWorld;
import org.bukkit.event.*;
import org.bukkit.event.server.ServerLoadEvent;
import org.bukkit.plugin.java.JavaPlugin;

/** Independent FULL-only diagnostic in NEW frozen worlds. Does not relax or replace the original CARVERS/LIGHT stage gate. */
public final class NeverNetherRoofProbeR14 extends JavaPlugin implements Listener {
    private final Gson gson = new GsonBuilder().setPrettyPrinting().create();
    private final JsonObject report = new JsonObject();
    private final JsonArray observations = new JsonArray();
    private volatile boolean cancelled;
    private boolean testMutations;
    private final JsonArray boundaryFailures=new JsonArray();
    private int boundaryChecks;
    private Thread worker;
    private Path output;
    private static <T extends Comparable<T>> String value(BlockState state, Property<T> property) { return property.getName(state.getValue(property)); }
    private static String stateName(BlockState state) {
        String name = BuiltInRegistries.BLOCK.getKey(state.getBlock()).toString();
        var props = new TreeMap<String,String>();
        for (var p : state.getProperties()) props.put(p.getName(), value(state,p));
        return props.isEmpty() ? name : name + "[" + String.join(",", props.entrySet().stream().map(e -> e.getKey()+"="+e.getValue()).toList()) + "]";
    }
    @Override public void onEnable() {
        if (!Bukkit.getIp().equals("127.0.0.1") || !Boolean.getBoolean("neverfolia.qa.stageProbe") || !Files.isRegularFile(Path.of(".nevernether-r8-isolated")))
            throw new IllegalStateException("Stage probe requires a NEW loopback-only disposable world and explicit QA opt-in");
        output = getDataFolder().toPath();
        Bukkit.getPluginManager().registerEvents(this,this);
    }
    @Override public void onDisable() { cancelled=true; if(worker!=null)worker.interrupt(); }
    @EventHandler public void loaded(ServerLoadEvent event) {
        if (worker != null) return;
        ServerLevel level=((CraftWorld)Bukkit.getWorlds().stream().filter(w->w.getEnvironment()==org.bukkit.World.Environment.NETHER).findFirst().orElseThrow()).getHandle();
        level.getServer().tickRateManager().setFrozen(true);
        level.getServer().tickRateManager().setFrozenTicksToRun(0);
        level.getServer().tickRateManager().tick();
        if(level.tickRateManager().runsNormally())throw new IllegalStateException("Tick isolation failed");
        worker=Thread.ofPlatform().name("NN-R8-stage-probe").unstarted(()->{
            try { run(level); }
            catch(Throwable e) { getLogger().log(java.util.logging.Level.SEVERE,"Stage probe failed",e); report.addProperty("error",e.toString()); try { save("failed"); } catch(Exception ignored){} }
        }); worker.start();
    }
    private void run(ServerLevel level) throws Exception {
        JsonObject plan=JsonParser.parseString(Files.readString(Path.of("stage-plan.json"))).getAsJsonObject();
        if(plan.get("seed").getAsLong()!=level.getSeed())throw new IllegalArgumentException("Seed mismatch");
        testMutations=plan.has("test_mutations") && plan.get("test_mutations").getAsBoolean();
        JsonArray raw=plan.getAsJsonArray("chunks");
        if(raw.isEmpty()||raw.size()>2048)throw new IllegalArgumentException("Expected 1..2048 explicit roof512 QA coordinates");
        var chunks=new ArrayList<int[]>();var unique=new HashSet<String>();
        for(var entry:raw){var c=entry.getAsJsonArray();if(c.size()!=2)throw new IllegalArgumentException("Expected X,Z");int x=c.get(0).getAsInt(),z=c.get(1).getAsInt();
            if(Math.max(Math.abs((long)x),Math.abs((long)z))<6 || Math.max(Math.abs((long)x),Math.abs((long)z))>100000)throw new IllegalArgumentException("Probe must stay far from spawn and within bounded coordinates");
            if(!unique.add(x+","+z))throw new IllegalArgumentException("Duplicate chunk");chunks.add(new int[]{x,z});}
        var ordered=new ArrayList<int[]>(chunks);ordered.sort(Comparator.<int[]>comparingInt(c->c[0]).thenComparingInt(c->c[1]));
        var canonical=new StringBuilder();for(var c:ordered)canonical.append(c[0]).append(",").append(c[1]).append("\n");
        var planHash=HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(canonical.toString().getBytes(java.nio.charset.StandardCharsets.UTF_8)));
        
        report.addProperty("coverage_sha256",planHash);
        Files.createDirectories(output);
        var states=new TreeMap<Integer,String>();for(BlockState state:Block.BLOCK_STATE_REGISTRY)states.put(Block.getId(state),stateName(state));
        byte[] dictionary=gson.toJson(states).getBytes(java.nio.charset.StandardCharsets.UTF_8);Files.write(output.resolve("states.json"),dictionary);
        report.addProperty("schema",1);report.addProperty("probe","NN-ROOF-R14");report.addProperty("seed",level.getSeed());report.add("plan",plan);
        report.addProperty("state_dictionary_sha256",HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(dictionary)));
        report.addProperty("target_FULL_requests",chunks.size()*(plan.has("readback")&&plan.get("readback").getAsBoolean()?1:2));report.addProperty("simulation_frozen_before_probe",true);report.addProperty("release_ready",false);report.add("observations",observations);save("running");
        // This protocol requests final chunks explicitly; it never calls a FULL
        // observation a pre-FULL stage. Both snapshots require region ownership.
        if(!plan.has("readback") || !plan.get("readback").getAsBoolean()) for(var chunk:chunks)load(level,chunk[0],chunk[1],ChunkStatus.FULL,"full");
        for(var chunk:chunks)load(level,chunk[0],chunk[1],ChunkStatus.FULL,"settled");
        report.addProperty("boundary_checks",boundaryChecks);report.add("boundary_failures",boundaryFailures);
        save("completed");getLogger().info("NN-STAGE-R8 COMPLETE chunks="+chunks.size());
    }
    private void load(ServerLevel level,int x,int z,ChunkStatus wanted,String phase)throws Exception{
        if(cancelled)throw new InterruptedException();var done=new CompletableFuture<JsonObject>();
        level.moonrise$getChunkTaskScheduler().scheduleChunkLoad(x,z,wanted,true,Priority.NORMAL,chunk->{
            try {
                if(chunk==null || chunk.getPos().x()!=x||chunk.getPos().z()!=z)throw new IllegalStateException("Wrong chunk");
                var status=chunk.getPersistedStatus();
                if(!level.tickRateManager().isFrozen() || level.tickRateManager().runsNormally() || level.tickRateManager().isSteppingForward())throw new IllegalStateException("Tick isolation lost");
                if(wanted!=ChunkStatus.FULL || status!=ChunkStatus.FULL)throw new IllegalStateException("FULL-only snapshot before FULL: "+status);
                if(status==ChunkStatus.FULL && !ca.spottedleaf.moonrise.common.util.TickThread.isTickThreadFor(level,x,z))throw new IllegalStateException("FULL snapshot off owning region");
                if(chunk.getMinY()!=-128||chunk.getHeight()!=656)throw new IllegalStateException("Unexpected Nether bounds");
                int roofErrors=0,paddingErrors=0,upperOpen=0;
                var actualSections=chunk.getSections();
                if(actualSections.length!=41)throw new IllegalStateException("Expected 41 sections");
                for(int lx=0;lx<16;lx++)for(int lz=0;lz<16;lz++) {
                    if(!actualSections[40].getBlockState(lx,0,lz).is(net.minecraft.world.level.block.Blocks.BEDROCK))roofErrors++;
                    for(int ly=1;ly<16;ly++)if(!actualSections[40].getBlockState(lx,ly,lz).isAir())paddingErrors++;
                    for(int y=384;y<=506;y++)if(actualSections[(y+128)>>4].getBlockState(lx,y&15,lz).isAir())upperOpen++;
                }
                if(testMutations && phase.equals("full")) testBoundary(level,chunk,x,z);
                Path folder=output.resolve(phase);Files.createDirectories(folder);Path file=folder.resolve(x+"_"+z+".bin.gz");
                // Capture section copies while checking the generation barrier. Compression and
                // file I/O use ONLY detached copies, so later promotion cannot contaminate them.
                var liveSections=chunk.getSections();
                var captured=new net.minecraft.world.level.chunk.LevelChunkSection[liveSections.length];
                for(int sectionIndex=0;sectionIndex<liveSections.length;sectionIndex++)captured[sectionIndex]=liveSections[sectionIndex].copy();
                if(chunk.getPersistedStatus()!=status)throw new IllegalStateException("Status changed during immutable capture");
                byte[] snapshot=snapshot(captured,x,z);Files.write(file,snapshot);
                var meta = new net.minecraft.nbt.ListTag();
                int sy=chunk.getMinSectionY();
                for(var section:captured) {
                    var data=net.minecraft.world.level.levelgen.placement.NeverNetherStorageR11.encode(section,chunk.getPos(),sy++);
                    if(data==null)throw new IllegalStateException("Missing R14 section metadata at "+x+","+z);
                    meta.add(data);
                }
                var compound=new net.minecraft.nbt.CompoundTag();compound.put("Substrate",meta);
                Path metadata=folder.resolve(x+"_"+z+".substrate.nbt");
                net.minecraft.nbt.NbtIo.writeCompressed(compound,metadata);

                var record=new JsonObject();record.addProperty("x",x);record.addProperty("z",z);record.addProperty("phase",phase);
                record.addProperty("status",status.toString());record.addProperty("class",chunk.getClass().getName());record.addProperty("simulation_frozen",!level.tickRateManager().runsNormally());record.addProperty("file",phase+"/"+file.getFileName());record.addProperty("bytes",snapshot.length);
                record.addProperty("sha256",HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(snapshot)));
                record.addProperty("roof_non_bedrock",roofErrors);record.addProperty("padding_non_air",paddingErrors);record.addProperty("upper_cave_air",upperOpen);
                record.addProperty("metadata_file",phase+"/"+metadata.getFileName());
                record.addProperty("metadata_sha256",HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(metadata))));
                record.addProperty("metadata_bytes",Files.size(metadata));record.addProperty("metadata_sections",meta.size());
                record.addProperty("capture_protocol","immutable-section-copy-r11");
                record.addProperty("capture_status_before",status.toString());record.addProperty("capture_status_after",status.toString());
                done.complete(record);
            } catch(Throwable e){done.completeExceptionally(e);}
        });
        observations.add(done.get(90,TimeUnit.SECONDS));save("running");
    }
    private void verify(boolean condition,String label){boundaryChecks++;if(!condition)boundaryFailures.add(label);}
    private void testBoundary(ServerLevel level,ChunkAccess chunk,int cx,int cz) {
        var sections=chunk.getSections();
        int x=(cx<<4)+8,z=(cz<<4)+8;
        for(int y:new int[]{-129,-128,511,512,513,527,528}) {
            verify(level.isInsideBuildHeight(y)==!level.isOutsideBuildHeight(y),"inside/outside complement y="+y);
            verify(level.isOutsideBuildHeight(y)==(y < -128 || y>512),"logical limit y="+y);
        }
        for(int y:new int[]{512,513,527}) {
            var p=new net.minecraft.core.BlockPos(x,y,z);var sec=sections[(y+128)>>4];
            var expected=sec.getBlockState(8,y&15,8);
            var states=y==512?List.of(net.minecraft.world.level.block.Blocks.AIR,net.minecraft.world.level.block.Blocks.STONE,net.minecraft.world.level.block.Blocks.LAVA):List.of(net.minecraft.world.level.block.Blocks.STONE,net.minecraft.world.level.block.Blocks.LAVA,net.minecraft.world.level.block.Blocks.BEDROCK);
            for(var block:states) {
                verify(!level.setBlock(p,block.defaultBlockState(),2),"level rejects "+y+" "+block);
                verify(sec.getBlockState(8,y&15,8)==expected,"level unchanged "+y);
                chunk.setBlockState(p,block.defaultBlockState(),2);
                verify(sec.getBlockState(8,y&15,8)==expected,"chunk rejects "+y);
                sec.setBlockState(8,y&15,8,block.defaultBlockState());
                verify(sec.getBlockState(8,y&15,8)==expected,"section rejects "+y);
                var bukkit=level.getWorld().getBlockAt(x,y,z);
                try{bukkit.setType(org.bukkit.Material.STONE,false);}catch(IllegalArgumentException rejected){}
                verify(sec.getBlockState(8,y&15,8)==expected,"Bukkit rejects "+y);
            }
        }
        var p=new net.minecraft.core.BlockPos(x,506,z);
        var original=level.getBlockState(p);
        verify(level.setBlock(p,net.minecraft.world.level.block.Blocks.GOLD_BLOCK.defaultBlockState(),2),"can build below roof");
        verify(level.getBlockState(p).is(net.minecraft.world.level.block.Blocks.GOLD_BLOCK),"below roof placed");
        level.setBlock(p,original,2);
        verify(level.getBlockState(p)==original,"below roof restored");
    }
    private byte[] snapshot(net.minecraft.world.level.chunk.LevelChunkSection[] sections,int cx,int cz)throws IOException{
        var bytes=new ByteArrayOutputStream();
        try(var out=new DataOutputStream(new GZIPOutputStream(bytes))){
            out.writeInt(0x4e4e5238);out.writeInt(1);out.writeInt(cx);out.writeInt(cz);out.writeInt(-128);out.writeInt(656);
            for(int y=-128;y<528;y++)for(int z=0;z<16;z++)for(int x=0;x<16;x++)out.writeInt(Block.getId(sections[(y+128)>>4].getBlockState(x,y&15,z)));
        }return bytes.toByteArray();
    }
    private void save(String stage)throws IOException{
        report.addProperty("stage",stage);Path temp=output.resolve("report.tmp");Files.writeString(temp,gson.toJson(report));Files.move(temp,output.resolve("report.json"),StandardCopyOption.REPLACE_EXISTING,StandardCopyOption.ATOMIC_MOVE);
    }
}
