import ca.spottedleaf.concurrentutil.util.Priority;
import com.google.gson.*;
import com.mojang.serialization.JsonOps;
import java.nio.file.*;
import java.time.Instant;
import java.util.*;
import java.util.concurrent.*;
import net.minecraft.core.registries.Registries;
import net.minecraft.nbt.NbtOps;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.level.chunk.status.ChunkStatus;
import net.minecraft.world.level.levelgen.structure.*;
import net.minecraft.world.level.levelgen.structure.pieces.StructurePieceSerializationContext;
import net.minecraft.world.level.levelgen.structure.placement.RandomSpreadStructurePlacement;
import org.bukkit.Bukkit;
import org.bukkit.craftbukkit.CraftWorld;
import org.bukkit.event.*;
import org.bukkit.event.server.ServerLoadEvent;
import org.bukkit.plugin.java.JavaPlugin;

/** Isolated-world QA only. Uses the normal scheduler/generator; never places a structure.
 * A STRUCTURE_STARTS snapshot is not reported as proof of placed blocks or walkability.
 */
public final class NeverNetherWorldgenQa extends JavaPlugin implements Listener {
    private final Gson gson = new GsonBuilder().create();
    private final Map<String, JsonObject> found = new TreeMap<>();
    private final JsonArray attempts = new JsonArray();
    private volatile boolean cancelled;
    private Thread worker;
    private long seed;
    @Override public void onEnable() {
        if (!Boolean.getBoolean("neverfolia.qa.isolated")) throw new IllegalStateException("Requires -Dneverfolia.qa.isolated=true on a NEW disposable test world");
        Bukkit.getPluginManager().registerEvents(this, this);
    }
    @Override public void onDisable() { cancelled = true; if (worker != null) worker.interrupt(); }
    @EventHandler public void loaded(ServerLoadEvent event) {
        if (worker != null) return;
        ServerLevel level = ((CraftWorld) Bukkit.getWorlds().stream().filter(w -> w.getEnvironment() == org.bukkit.World.Environment.NETHER).findFirst().orElseThrow()).getHandle();
        seed = level.getSeed();
        worker = Thread.ofPlatform().name("NeverNether-isolated-qa").unstarted(() -> {
            try {
                String mode = System.getProperty("neverfolia.qa.mode", "discover");
                if (mode.equals("discover")) discover(level);
                else if (mode.equals("full")) generateFull(level);
                else throw new IllegalArgumentException("Unknown QA mode " + mode);
                report("completed", null);
            } catch (Throwable error) {
                getLogger().log(java.util.logging.Level.SEVERE, "Worldgen QA failed", error);
                try { report("failed", error.toString()); } catch (Exception ignored) { }
            }
        });
        worker.start();
    }
    private JsonObject load(ServerLevel level, int x, int z, ChunkStatus status) throws Exception {
        if (cancelled) throw new InterruptedException();
        var future = new CompletableFuture<JsonObject>();
        level.moonrise$getChunkTaskScheduler().scheduleChunkLoad(x, z, status, true, Priority.NORMAL, chunk -> {
            try {
                if (chunk == null || !chunk.getPersistedStatus().isOrAfter(status)) throw new IllegalStateException("Missing/incomplete generated chunk " + x + "," + z);
                JsonObject out = new JsonObject(); out.addProperty("chunk_x", x); out.addProperty("chunk_z", z);
                out.addProperty("status", chunk.getPersistedStatus().toString());
                JsonObject starts = new JsonObject();
                var registry = level.registryAccess().lookupOrThrow(Registries.STRUCTURE);
                var context = StructurePieceSerializationContext.fromLevel(level);
                for (var entry : chunk.getAllStarts().entrySet()) {
                    StructureStart start = entry.getValue();
                    if (!start.isValid()) continue;
                    String id = registry.getKey(entry.getKey()).toString();
                    starts.add(id, NbtOps.INSTANCE.convertTo(JsonOps.INSTANCE, start.createTag(context, chunk.getPos())));
                }
                out.add("starts", starts); future.complete(out);
            } catch (Throwable error) { future.completeExceptionally(error); }
        });
        // This wait is on our private QA worker, never a Folia region thread.
        return future.get(90, TimeUnit.SECONDS);
    }
    private void observe(JsonObject result) {
        for (var e : result.getAsJsonObject("starts").entrySet()) {
            if (!e.getKey().startsWith("minecraft:")) {
                JsonObject record = e.getValue().getAsJsonObject().deepCopy();
                record.addProperty("observed_chunk_x", result.get("chunk_x").getAsInt());
                record.addProperty("observed_chunk_z", result.get("chunk_z").getAsInt());
                record.addProperty("observed_status", result.get("status").getAsString());
                if (found.putIfAbsent(e.getKey(), record) == null) getLogger().info("NATURAL START " + e.getKey() + " at " + result.get("chunk_x") + "," + result.get("chunk_z") + " pieces=" + record.getAsJsonArray("Children").size());
            }
        }
        JsonObject summary = new JsonObject();
        for (var item : result.entrySet()) if (!item.getKey().equals("starts")) summary.add(item.getKey(), item.getValue());
        JsonArray ids = new JsonArray(); result.getAsJsonObject("starts").keySet().stream().sorted().forEach(ids::add);
        summary.add("starts", ids); attempts.add(summary);
    }
    private void discover(ServerLevel level) throws Exception {
        var state = level.getChunkSource().getGeneratorState();
        var sets = level.registryAccess().lookupOrThrow(Registries.STRUCTURE_SET);
        int maxRing = Integer.getInteger("neverfolia.qa.rings", 10);
        if (maxRing < 0 || maxRing > 20) throw new IllegalArgumentException("rings must be 0..20");
        for (String name : List.of("custom_ambient", "custom_medium", "custom_major", "nether_monument")) {
            var id = net.minecraft.resources.Identifier.fromNamespaceAndPath("neverfolia", "never_nether/" + name);
            StructureSet set = sets.get(id).orElseThrow().value();
            var placement = (RandomSpreadStructurePlacement) set.placement();
            var expected = new TreeSet<String>();
            for (var entry : set.structures()) expected.add(entry.structure().unwrapKey().orElseThrow().identifier().toString());
            outer: for (int ring = 0; ring <= maxRing; ring++) {
                for (int gx = -ring; gx <= ring; gx++) for (int gz = -ring; gz <= ring; gz++) {
                    if (Math.max(Math.abs(gx), Math.abs(gz)) != ring) continue;
                    if (found.keySet().containsAll(expected)) break outer;
                    var pos = placement.getPotentialStructureChunk(state.getLevelSeed(), gx * placement.spacing(), gz * placement.spacing());
                    JsonObject result = load(level, pos.x(), pos.z(), ChunkStatus.STRUCTURE_STARTS);
                    result.addProperty("candidate_group", name); result.addProperty("grid_x", gx); result.addProperty("grid_z", gz);
                    observe(result);
                    if (attempts.size() % 10 == 0) report("running", null);
                }
            }
            var missing = new TreeSet<>(expected); missing.removeAll(found.keySet());
            getLogger().info("DISCOVERY GROUP " + name + " missing=" + missing + " totalAttempts=" + attempts.size());
            report("running", null);
        }
    }
    private void generateFull(ServerLevel level) throws Exception {
        Path plan = Path.of(System.getProperty("neverfolia.qa.plan", "plan.json"));
        JsonObject input = JsonParser.parseString(Files.readString(plan)).getAsJsonObject();
        if (input.get("seed").getAsLong() != seed) throw new IllegalArgumentException("Seed differs from plan");
        JsonArray chunks = input.getAsJsonArray("chunks");
        if (chunks.isEmpty() || chunks.size() > 4096) throw new IllegalArgumentException("Expected 1..4096 chunks");
        for (JsonElement e : chunks) {
            var coord = e.getAsJsonArray();
            observe(load(level, coord.get(0).getAsInt(), coord.get(1).getAsInt(), ChunkStatus.FULL));
            if (attempts.size() % 50 == 0) { report("running", null); getLogger().info("FULL " + attempts.size() + "/" + chunks.size()); }
        }
    }
    private void report(String status, String error) throws Exception {
        getDataFolder().mkdirs();
        JsonObject report = new JsonObject(); report.addProperty("schema", 1);
        report.addProperty("stage", "NN-WORLDGEN-R7"); report.addProperty("status", status);
        report.addProperty("seed", seed); report.addProperty("mode", System.getProperty("neverfolia.qa.mode", "discover"));
        report.addProperty("timestamp", Instant.now().toString());
        report.addProperty("found_custom_structures", found.size());
        var starts = new JsonObject(); found.forEach(starts::add);
        report.add("first_natural_starts", starts); report.add("attempts", attempts);
        report.addProperty("forced_structure_placement", false); report.addProperty("release_ready", false);
        if (error != null) report.addProperty("error", error);
        Path tmp = getDataFolder().toPath().resolve("result.json.tmp"), out = getDataFolder().toPath().resolve("result.json");
        try (var writer = Files.newBufferedWriter(tmp)) { gson.toJson(report, writer); }
        Files.move(tmp, out, StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE);
        if (!status.equals("running")) getLogger().info("NN-WORLDGEN-R7 " + status + " found=" + found.size() + " chunks=" + attempts.size());
    }
}
