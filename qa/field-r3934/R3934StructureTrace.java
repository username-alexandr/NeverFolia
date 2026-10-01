import com.google.gson.*;
import java.nio.file.Files;
import java.util.*;
import org.bukkit.*;
import org.bukkit.event.*;
import org.bukkit.event.server.ServerLoadEvent;
import org.bukkit.plugin.java.JavaPlugin;

public final class R3934StructureTrace extends JavaPlugin implements Listener {
    private World world;
    private final List<int[]> targets = new ArrayList<>();
    private int index;
    private boolean started, finished;
    private final String nonce = System.getProperty("neverfolia.qaNonce", "");
    private static final int CENTER_X = -205;
    private static final int CENTER_Z = -224;
    private static final int RADIUS = 8;

    @Override public void onEnable() {
        Bukkit.getPluginManager().registerEvents(this, this);
    }

    @EventHandler public void loaded(ServerLoadEvent e) {
        if (started) return;
        started = true;
        try {
            world = Bukkit.getWorlds().stream()
                .filter(w -> w.getEnvironment() == World.Environment.NORMAL)
                .findFirst().orElseThrow();
            if (world.getSeed() != -4651369264513492755L) {
                throw new AssertionError("Wrong seed " + world.getSeed());
            }
            for (int dz = -RADIUS; dz <= RADIUS; ++dz) {
                for (int dx = -RADIUS; dx <= RADIUS; ++dx) {
                    targets.add(new int[]{CENTER_X + dx, CENTER_Z + dz});
                }
            }
            Bukkit.getGlobalRegionScheduler().execute(this, this::next);
        } catch (Throwable t) {
            finish(t);
        }
    }

    private void next() {
        if (finished) return;
        if (index == targets.size()) {
            finish(null);
            return;
        }
        int[] t = targets.get(index);
        int cx = t[0], cz = t[1];
        world.getChunkAtAsync(cx, cz, true).whenComplete((chunk, error) -> {
            if (error != null) {
                finish(error);
                return;
            }
            Bukkit.getRegionScheduler().execute(this, world, cx, cz, () -> {
                try {
                    // Touch snapshot so FULL chunk data is materialized and saved.
                    chunk.getChunkSnapshot(false, true, false);
                    ++index;
                    if ((index % 25) == 0 || index == targets.size()) {
                        getLogger().info("R3934 GENERATED " + index + "/" + targets.size());
                    }
                    Bukkit.getGlobalRegionScheduler().execute(this, this::next);
                } catch (Throwable x) {
                    finish(x);
                }
            });
        });
    }

    private synchronized void finish(Throwable e) {
        if (finished) return;
        finished = true;
        JsonObject o = new JsonObject();
        o.addProperty("pass", e == null);
        o.addProperty("nonce", nonce);
        o.addProperty("seed", world == null ? 0 : world.getSeed());
        o.addProperty("center_chunk_x", CENTER_X);
        o.addProperty("center_chunk_z", CENTER_Z);
        o.addProperty("radius", RADIUS);
        o.addProperty("generated_chunks", index);
        if (e != null) {
            o.addProperty("error", e.toString());
            e.printStackTrace();
        }
        try {
            getDataFolder().mkdirs();
            Files.writeString(
                getDataFolder().toPath().resolve("result.json"),
                new GsonBuilder().setPrettyPrinting().create().toJson(o)
            );
        } catch (Exception x) {
            x.printStackTrace();
        }
        getLogger().info("R3934 STRUCTURE TRACE " + (e == null ? "PASS " : "FAIL ") + nonce);
    }
}
