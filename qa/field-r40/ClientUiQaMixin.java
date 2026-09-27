package cc.neverland.qa;

import com.google.gson.*;
import java.nio.file.*;
import java.util.*;
import net.minecraft.client.Minecraft;
import net.minecraft.client.resources.language.I18n;
import net.minecraft.core.component.DataComponents;
import net.minecraft.core.registries.Registries;
import net.minecraft.world.item.CreativeModeTabs;
import net.minecraft.world.item.ItemStack;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/** Test-only mixin, never shipped in the player mod. */
@Mixin(value=Minecraft.class,remap=false)
public abstract class ClientUiQaMixin {
    private static boolean neverland$finished;
    private static int neverland$joinedTicks;
    @Inject(method="tick",at=@At("TAIL"),require=1,remap=false)
    private void neverland$observe(CallbackInfo callback) {
        Minecraft mc=Minecraft.getInstance();
        if(neverland$finished||mc.level==null||mc.player==null||mc.gameMode==null)return;
        if(++neverland$joinedTicks<50)return;
        neverland$finished=true;JsonObject report=new JsonObject();boolean pass=false;
        try {
            if(!mc.gameMode.isCreative())throw new AssertionError("Not a creative test player");
            var registry=mc.level.registryAccess().lookupOrThrow(Registries.ENCHANTMENT);
            JsonObject expected=JsonParser.parseString(Files.readString(Path.of("expected-ui-enchants.json"))).getAsJsonObject();
            CreativeModeTabs.tryRebuildTabContents(mc.level.enabledFeatures(),mc.player.canUseGameMasterBlocks(),mc.level.registryAccess());
            Set<String> shown=new TreeSet<>();int books=0;
            for(var tab:CreativeModeTabs.allTabs())for(ItemStack stack:tab.getDisplayItems()) {
                var stored=stack.get(DataComponents.STORED_ENCHANTMENTS);
                if(stored==null)continue;books++;
                for(var enchantment:stored.keySet())shown.add(registry.getKey(enchantment.value()).toString());
            }
            JsonArray checks=new JsonArray();
            for(var entry:expected.entrySet()) {
                boolean visible=shown.contains(entry.getKey()),want=entry.getValue().getAsBoolean();
                JsonObject row=new JsonObject();row.addProperty("id",entry.getKey());row.addProperty("expected_visible",want);row.addProperty("actually_visible",visible);checks.add(row);
                if(visible!=want)throw new AssertionError("Wrong creative visibility for "+entry.getKey()+": "+visible);
            }
            if(!I18n.get("enchantment.dnt.swift_soar").equals("Стремительный полёт"))throw new AssertionError("Swift Soar translation not loaded");
            if(!I18n.get("enchantment.dnt.wither_coated").equals("Иссушающее покрытие"))throw new AssertionError("Wither Coated translation not loaded");
            report.add("checks",checks);report.addProperty("actual_display_book_entries",books);report.add("visible_enchantment_ids",new Gson().toJsonTree(shown));
            report.addProperty("swift_soar_ru",I18n.get("enchantment.dnt.swift_soar"));report.addProperty("wither_coated_ru",I18n.get("enchantment.dnt.wither_coated"));
            pass=true;
        }catch(Throwable failure){report.addProperty("error",failure.toString());failure.printStackTrace();}
        report.addProperty("pass",pass);report.addProperty("nonce",System.getProperty("neverfolia.qaNonce",""));
        report.addProperty("scope","Real Fabric client connected to isolated server; actual generated creative-tab item lists and loaded Russian language resources");
        try{Files.writeString(Path.of("client-ui-result.json"),new GsonBuilder().setPrettyPrinting().create().toJson(report));}
        catch(Exception error){error.printStackTrace();pass=false;}
        System.out.println("R40 CLIENT UI "+(pass?"PASS":"FAIL"));mc.stop();
    }
}
