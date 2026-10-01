import com.google.gson.*;
import java.nio.file.Files;
import java.util.*;
import org.bukkit.*;
import org.bukkit.event.*;
import org.bukkit.event.server.ServerLoadEvent;
import org.bukkit.generator.structure.Structure;
import org.bukkit.plugin.java.JavaPlugin;

public final class R3937NetherRegistryQa extends JavaPlugin implements Listener {
    private static final List<String> CUSTOM = List.of(
        "nova_structures:nether_keep",
        "nova_structures:piglin_donjon",
        "nova_structures:sealing_halls",
        "nova_structures:nether_port",
        "nova_structures:hamlet",
        "nova_structures:piglin_outstation",
        "explorify:black_spiral",
        "hearths:crimson_tower",
        "hearths:warped_tower",
        "structory_towers:nether/fortress_tower",
        "structory_towers:nether/strange_outpost",
        "structory_towers:nether/warped_outpost",
        "hearths:netherrack_spiral",
        "nova_structures:nether_skeleton_tower_fort",
        "nova_structures:nether_skeleton_tower_warped",
        "nova_structures:nether_skeleton_tower_crimson",
        "nova_structures:nether_skeleton_tower_soul",
        "nova_structures:piglin_camp",
        "nova_structures:piglin_camp_collony",
        "repurposed_structures:monument_nether"
    );

    private static final List<String> VANILLA = List.of(
        "minecraft:fortress",
        "minecraft:bastion_remnant",
        "minecraft:ruined_portal_nether",
        "minecraft:nether_fossil"
    );

    private boolean done;
    private final String nonce=System.getProperty("neverfolia.qaNonce","");

    @Override public void onEnable(){
        Bukkit.getPluginManager().registerEvents(this,this);
    }

    @EventHandler public void loaded(ServerLoadEvent event){
        if(done)return;
        done=true;
        JsonObject out=new JsonObject();
        JsonArray present=new JsonArray();
        JsonArray missing=new JsonArray();
        JsonArray vanillaMissing=new JsonArray();

        try{
            for(String id:CUSTOM){
                NamespacedKey key=NamespacedKey.fromString(id);
                Structure structure=key==null?null:Registry.STRUCTURE.get(key);
                if(structure==null)missing.add(id);else present.add(id);
            }
            for(String id:VANILLA){
                NamespacedKey key=NamespacedKey.fromString(id);
                if(key==null||Registry.STRUCTURE.get(key)==null)vanillaMissing.add(id);
            }

            out.addProperty("pass",missing.isEmpty()&&vanillaMissing.isEmpty());
            out.addProperty("nonce",nonce);
            out.addProperty("registry_size",Registry.STRUCTURE.size());
            out.addProperty("custom_expected",CUSTOM.size());
            out.addProperty("custom_present",present.size());
            out.add("present",present);
            out.add("missing",missing);
            out.add("vanilla_missing",vanillaMissing);
        }catch(Throwable t){
            out.addProperty("pass",false);
            out.addProperty("error",t.toString());
            t.printStackTrace();
        }

        try{
            getDataFolder().mkdirs();
            Files.writeString(
                getDataFolder().toPath().resolve("result.json"),
                new GsonBuilder().setPrettyPrinting().create().toJson(out)
            );
        }catch(Exception e){e.printStackTrace();}

        getLogger().info(
            "R3937 NETHER REGISTRY "+(out.get("pass").getAsBoolean()?"PASS ":"FAIL ")+nonce+
            " custom="+present.size()+"/"+CUSTOM.size()+" missing="+missing
        );
    }
}
