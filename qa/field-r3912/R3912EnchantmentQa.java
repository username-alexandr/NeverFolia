import cc.neverland.client.EnchantmentVisibility;
import com.google.gson.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.io.InputStreamReader;
import java.util.Objects;
import org.bukkit.Bukkit;
import org.bukkit.World;
import org.bukkit.craftbukkit.CraftWorld;
import org.bukkit.event.EventHandler;
import org.bukkit.event.Listener;
import org.bukkit.event.server.ServerLoadEvent;
import org.bukkit.plugin.java.JavaPlugin;
import net.minecraft.core.registries.Registries;
import net.minecraft.resources.Identifier;
import net.minecraft.resources.ResourceKey;

/** Registry/predicate test only. It never claims to launch the client or apply a Mixin. */
public final class R3912EnchantmentQa extends JavaPlugin implements Listener {
    private boolean ran;
    @Override public void onEnable() { Bukkit.getPluginManager().registerEvents(this,this); }
    @EventHandler public void loaded(ServerLoadEvent event) {
        if (ran) return;
        ran=true;
        String nonce=System.getProperty("neverfolia.r3912Nonce", "");
        JsonObject result=new JsonObject();
        JsonArray rows=new JsonArray();
        Throwable failure=null;
        try {
            if (nonce.isEmpty()) throw new AssertionError("Missing current-run nonce");
            World world=Bukkit.getWorlds().stream().filter(w->w.getEnvironment()==World.Environment.NORMAL).findFirst().orElseThrow();
            if (world.getSeed()!=-4651369264513492755L) throw new AssertionError("Wrong seed");
            result.addProperty("seed",Long.toString(world.getSeed()));
            var registry=((CraftWorld)world).getHandle().registryAccess().lookupOrThrow(Registries.ENCHANTMENT);
            JsonObject expected;
            try (var reader=new InputStreamReader(Objects.requireNonNull(getResource("expected.json")),StandardCharsets.UTF_8)) {
                expected=JsonParser.parseReader(reader).getAsJsonObject();
            }
            int hidden=0,shown=0;
            for (var e:expected.entrySet()) {
                String[] id=e.getKey().split(":",2);
                var holder=registry.getOrThrow(ResourceKey.create(Registries.ENCHANTMENT,Identifier.fromNamespaceAndPath(id[0],id[1])));
                boolean actual=EnchantmentVisibility.show(holder), want=e.getValue().getAsBoolean();
                JsonObject row=new JsonObject(); row.addProperty("id",e.getKey());
                row.addProperty("expected",want); row.addProperty("actual",actual); row.addProperty("present_in_registry",true);
                rows.add(row);
                if (actual!=want) throw new AssertionError("Wrong display classification: "+e.getKey());
                if (actual) shown++; else hidden++;
            }
            if (rows.size()!=35 || hidden!=16 || shown!=19) throw new AssertionError("Incomplete classification scope");
            result.addProperty("hidden_technical",hidden); result.addProperty("shown_gameplay_and_vanilla",shown);
        } catch(Throwable error) { failure=error; error.printStackTrace(); }
        result.addProperty("pass",failure==null); result.addProperty("nonce",nonce);
        result.addProperty("client_launched",false); result.addProperty("mixin_applied",false);
        result.addProperty("scope","Real loaded datapack registry and the byte-identical compiled predicate. Not client rendering, Mixin launch, loot or combat.");
        result.add("checks",rows);
        if (failure!=null) result.addProperty("error",failure.toString());
        try {
            Files.createDirectories(getDataFolder().toPath());
            Files.writeString(getDataFolder().toPath().resolve("result.json"),new GsonBuilder().setPrettyPrinting().create().toJson(result),StandardCharsets.UTF_8);
        } catch(Exception error) { error.printStackTrace(); failure=error; }
        getLogger().info("R3912 ENCHANT QA "+(failure==null?"PASS ":"FAIL ")+nonce);
    }
}
