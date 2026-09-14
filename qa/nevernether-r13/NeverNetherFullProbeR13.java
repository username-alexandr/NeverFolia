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
public final class NeverNetherFullProbeR13 extends JavaPlugin implements Listener {
    private final Gson gson = new GsonBuilder().setPrettyPrinting().create();
    private final JsonObject report = new JsonObject();
    private final JsonArray observations = new JsonArray();
    private volatile boolean cancelled;
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
        JsonArray raw=plan.getAsJsonArray("chunks");
        if(raw.isEmpty()||raw.size()!=1599)throw new IllegalArgumentException("Expected exactly 1599 pinned R7 chunks");
        var chunks=new ArrayList<int[]>();var unique=new HashSet<String>();
        for(var entry:raw){var c=entry.getAsJsonArray();if(c.size()!=2)throw new IllegalArgumentException("Expected X,Z");int x=c.get(0).getAsInt(),z=c.get(1).getAsInt();
            if(Math.max(Math.abs((long)x),Math.abs((long)z))<6 || Math.max(Math.abs((long)x),Math.abs((long)z))>100000)throw new IllegalArgumentException("Probe must stay far from spawn and within bounded coordinates");
            if(!unique.add(x+","+z))throw new IllegalArgumentException("Duplicate chunk");chunks.add(new int[]{x,z});}
        var ordered=new ArrayList<int[]>(chunks);ordered.sort(Comparator.<int[]>comparingInt(c->c[0]).thenComparingInt(c->c[1]));
        var canonical=new StringBuilder();for(var c:ordered)canonical.append(c[0]).append(",").append(c[1]).append("\n");
        var planHash=HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(canonical.toString().getBytes(java.nio.charset.StandardCharsets.UTF_8)));
        if(level.getSeed()!=7270913L || !planHash.equals("cb4f123132048322c8601eaf097ca68679128882a9269f43fe9740dff285d2e6"))throw new IllegalArgumentException("Unrecognized R7 footprint plan");
        report.addProperty("exact_r7_coverage_sha256",planHash);
        Files.createDirectories(output);
        var states=new TreeMap<Integer,String>();for(BlockState state:Block.BLOCK_STATE_REGISTRY)states.put(Block.getId(state),stateName(state));
        byte[] dictionary=gson.toJson(states).getBytes(java.nio.charset.StandardCharsets.UTF_8);Files.write(output.resolve("states.json"),dictionary);
        report.addProperty("schema",1);report.addProperty("probe","NN-FULL-R13");report.addProperty("seed",level.getSeed());report.add("plan",plan);
        report.addProperty("state_dictionary_sha256",HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(dictionary)));
        report.addProperty("target_FULL_requests",chunks.size()*2);report.addProperty("simulation_frozen_before_probe",true);report.addProperty("release_ready",false);report.add("observations",observations);save("running");
        // This protocol requests final chunks explicitly; it never calls a FULL
        // observation a pre-FULL stage. Both snapshots require region ownership.
        for(var chunk:chunks)load(level,chunk[0],chunk[1],ChunkStatus.FULL,"full");
        for(var chunk:chunks)load(level,chunk[0],chunk[1],ChunkStatus.FULL,"settled");
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
                if(chunk.getMinY()!=-128||chunk.getHeight()!=1024)throw new IllegalStateException("Unexpected Nether bounds");
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
                    if(data==null)throw new IllegalStateException("Missing R11 section metadata at "+x+","+z);
                    meta.add(data);
                }
                var compound=new net.minecraft.nbt.CompoundTag();compound.put("Substrate",meta);
                Path metadata=folder.resolve(x+"_"+z+".substrate.nbt");
                net.minecraft.nbt.NbtIo.writeCompressed(compound,metadata);

                var record=new JsonObject();record.addProperty("x",x);record.addProperty("z",z);record.addProperty("phase",phase);
                record.addProperty("status",status.toString());record.addProperty("class",chunk.getClass().getName());record.addProperty("simulation_frozen",!level.tickRateManager().runsNormally());record.addProperty("file",phase+"/"+file.getFileName());record.addProperty("bytes",snapshot.length);
                record.addProperty("sha256",HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(snapshot)));
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
    private byte[] snapshot(net.minecraft.world.level.chunk.LevelChunkSection[] sections,int cx,int cz)throws IOException{
        var bytes=new ByteArrayOutputStream();
        try(var out=new DataOutputStream(new GZIPOutputStream(bytes))){
            out.writeInt(0x4e4e5238);out.writeInt(1);out.writeInt(cx);out.writeInt(cz);out.writeInt(-128);out.writeInt(1024);
            for(int y=-128;y<896;y++)for(int z=0;z<16;z++)for(int x=0;x<16;x++)out.writeInt(Block.getId(sections[(y+128)>>4].getBlockState(x,y&15,z)));
        }return bytes.toByteArray();
    }
    private void save(String stage)throws IOException{
        report.addProperty("stage",stage);Path temp=output.resolve("report.tmp");Files.writeString(temp,gson.toJson(report));Files.move(temp,output.resolve("report.json"),StandardCopyOption.REPLACE_EXISTING,StandardCopyOption.ATOMIC_MOVE);
    }
}
