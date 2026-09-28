import com.google.gson.*;
import com.mojang.authlib.GameProfile;
import java.nio.file.Files;
import java.util.*;
import org.bukkit.Bukkit;
import org.bukkit.craftbukkit.CraftWorld;
import org.bukkit.event.*;
import org.bukkit.event.server.ServerLoadEvent;
import org.bukkit.plugin.java.JavaPlugin;
import net.minecraft.core.registries.*;
import net.minecraft.resources.*;
import net.minecraft.server.level.*;
import net.minecraft.server.permissions.PermissionSet;
import net.minecraft.world.entity.*;
import net.minecraft.world.entity.animal.happyghast.HappyGhast;
import net.minecraft.world.entity.player.Input;
import net.minecraft.world.entity.ai.attributes.*;
import net.minecraft.world.item.*;
import net.minecraft.world.item.enchantment.*;

/** Disposable CI fixtures. Real entity types, attributes, registry, tick effects,
 * function manager and input predicates. The rider is an unconnected ServerPlayer;
 * passenger links are an explicit fixture, NOT a network/mount-event test.
 * No thread checks or command permission checks are disabled.
 */
public final class R3915SwiftQa extends JavaPlugin implements Listener {
    private final JsonArray checks=new JsonArray(),levels=new JsonArray();
    private boolean started,finished;
    private ServerLevel level;
    private final boolean baseline=Boolean.getBoolean("neverfolia.qaBaseline");
    private final String nonce=System.getProperty("neverfolia.qaNonce","");
    private static final Identifier FLIGHT=id("sprint_flight_speed"),FOV=id("boost_player_fov");
    private static Identifier id(String path){return Identifier.fromNamespaceAndPath("nova_structures",path);}
    private void check(boolean ok,String name){JsonObject r=new JsonObject();r.addProperty("name",name);r.addProperty("pass",ok);checks.add(r);if(!ok)throw new AssertionError(name);}
    @Override public void onEnable(){Bukkit.getPluginManager().registerEvents(this,this);}
    @EventHandler public void loaded(ServerLoadEvent e){
        if(started)return;started=true;
        try {
            var world=Bukkit.getWorlds().stream().filter(w->w.getEnvironment()==org.bukkit.World.Environment.NORMAL).findFirst().orElseThrow();
            level=((CraftWorld)world).getHandle();
            Bukkit.getGlobalRegionScheduler().execute(this,()->{
                try{world.setChunkForceLoaded(0,0,true);world.getChunkAtAsync(0,0,true).whenComplete((c,error)->{
                    if(error!=null){finish(error);return;}
                    Bukkit.getRegionScheduler().runDelayed(this,world,0,0,task->test(),10);
                });}catch(Throwable error){finish(error);}
            });
        }catch(Throwable error){finish(error);}
    }
    private static void links(Entity vehicle,Entity passenger,boolean attach)throws Exception {
        // Controlled relation fixture instead of a fabricated network connection.
        var p=Entity.class.getDeclaredField("passengers");p.setAccessible(true);
        var v=Entity.class.getDeclaredField("vehicle");v.setAccessible(true);
        p.set(vehicle,attach?com.google.common.collect.ImmutableList.of(passenger):com.google.common.collect.ImmutableList.of());
        v.set(passenger,attach?vehicle:null);
    }
    private void input(ServerPlayer p,boolean forward,boolean sprint){
        p.setLastClientInput(new Input(forward,false,false,false,false,false,sprint));
        check(p.getLastClientInput().forward()==forward&&p.getLastClientInput().sprint()==sprint,"input fixture matches requested keys");
    }
    private void tick(HappyGhast ghast){EnchantmentHelper.tickEffects(level,ghast);}
    private void absent(AttributeInstance a,Identifier key,String why){check(a.getModifier(key)==null,why);}
    private void amount(AttributeInstance a,Identifier key,double expected,String why){
        var m=a.getModifier(key);check(m!=null&&Math.abs(m.amount()-expected)<1e-9&&m.operation()==AttributeModifier.Operation.ADD_MULTIPLIED_BASE,why);
    }
    private void test(){
        try {
            check(!nonce.isEmpty(),"fresh nonce supplied");check(level.getSeed()==-4651369264513492755L,"actual seed");
            check(ca.spottedleaf.moonrise.common.util.TickThread.isTickThreadFor(level,0,0),"actual owning region");
            var dispatcher=level.getServer().getCommands().getDispatcher();
            for(String root:new String[]{"data","tag","scoreboard","function","item","loot"})check(dispatcher.getRoot().getChild(root)==null,"generic "+root+" stays disabled");
            var holder=level.registryAccess().lookupOrThrow(Registries.ENCHANTMENT).getOrThrow(ResourceKey.create(Registries.ENCHANTMENT,id("swift_soar")));
            var effects=holder.value().effects().get(EnchantmentEffectComponents.TICK);
            check(baseline?(effects==null||effects.isEmpty()):(effects!=null&&effects.size()==3),"loaded tick graph matches baseline/candidate");
            for(int n=1;n<=3;n++)check(level.getServer().getFunctions().get(id("swift_soar_"+n)).isPresent()!=baseline,"compiled function "+n);
            var type=BuiltInRegistries.ENTITY_TYPE.getOptional(Identifier.fromNamespaceAndPath("minecraft","happy_ghast")).orElseThrow();
            for(int n=1;n<=3;n++) {
                HappyGhast ghast=(HappyGhast)type.create(level,EntitySpawnReason.COMMAND);
                check(ghast!=null,"create actual happy ghast "+n);ghast.setPos(8,400,8);ghast.setNoAi(true);ghast.setNoGravity(true);
                check(level.addFreshEntity(ghast),"add actual region-owned happy ghast "+n);
                ServerPlayer driver=null;
                try {
                    var harness=BuiltInRegistries.ITEM.getOptional(Identifier.fromNamespaceAndPath("minecraft","white_harness")).orElseThrow();
                    ItemStack item=new ItemStack(harness);item.enchant(holder,n);ghast.setItemSlot(EquipmentSlot.BODY,item);
                    driver=new ServerPlayer(level.getServer(),level,new GameProfile(UUID.nameUUIDFromBytes((nonce+"rider"+n).getBytes()),"SwiftQa"+n),ClientInformation.createDefault());
                    driver.setPos(8,400,8);links(ghast,driver,true);
                    check(ghast.getControllingPassenger()==driver,"real controlling-passenger lookup "+n);
                    check(ca.spottedleaf.moonrise.common.util.TickThread.isTickThreadFor(ghast)&&ca.spottedleaf.moonrise.common.util.TickThread.isTickThreadFor(driver),"both fixture entities satisfy owning-thread checks "+n);
                    var flight=Objects.requireNonNull(ghast.getAttribute(Attributes.FLYING_SPEED));var fov=Objects.requireNonNull(driver.getAttribute(Attributes.MOVEMENT_SPEED));
                    input(driver,true,false);tick(ghast);absent(flight,FLIGHT,"forward alone does not boost "+n);
                    input(driver,true,true);tick(ghast);
                    if(baseline){absent(flight,FLIGHT,"baseline has no flight effect "+n);absent(fov,FOV,"baseline has no FOV effect "+n);}
                    else {
                        double speed=new double[]{.2,.35,.5}[n-1],zoom=new double[]{.1,.175,.25}[n-1];
                        amount(flight,FLIGHT,speed,"actual enchantment tick applies exact flight modifier "+n);
                        amount(fov,FOV,zoom,"actual enchantment tick applies exact rider modifier "+n);
                        check(ghast.entityTags().contains("sprinting"),"native command owns sprint latch "+n);
                        int count=flight.getModifiers().size();tick(ghast);check(flight.getModifiers().size()==count,"repeat does not stack "+n);
                        input(driver,true,false);tick(ghast);amount(flight,FLIGHT,speed,"forward retains sprint latch "+n);
                        input(driver,false,false);tick(ghast);absent(flight,FLIGHT,"releasing forward removes flight modifier "+n);absent(fov,FOV,"releasing forward removes rider modifier "+n);
                        check(!ghast.entityTags().contains("sprinting"),"releasing forward clears latch "+n);
                        // Observe author dismount behavior, not actual mount events.
                        input(driver,true,true);tick(ghast);links(ghast,driver,false);tick(ghast);
                        absent(flight,FLIGHT,"unridden mount loses its boost "+n);
                        JsonObject row=new JsonObject();row.addProperty("tier",n);row.addProperty("speed_modifier",speed);row.addProperty("rider_modifier",zoom);row.addProperty("residual_rider_modifier_after_detach",fov.getModifier(FOV)!=null);levels.add(row);
                        fov.removeModifier(FOV);
                    }
                } finally {
                    if(driver!=null)links(ghast,driver,false);
                    ghast.discard();
                }
            }
            var low=net.minecraft.commands.Commands.createCompilationContext(PermissionSet.NO_PERMISSIONS);
            var parsed=dispatcher.parse("neverfolia:dnt sprint_on",low);
            check(parsed.getReader().canRead(),"unprivileged bridge remains rejected");
            finish(null);
        }catch(Throwable error){finish(error);}
    }
    private synchronized void finish(Throwable error){
        if(finished)return;finished=true;
        JsonObject r=new JsonObject();r.addProperty("pass",error==null);r.addProperty("seed",level==null?0:level.getSeed());r.addProperty("nonce",nonce);r.addProperty("baseline",baseline);r.add("checks",checks);r.add("levels",levels);
        r.addProperty("scope","Actual loaded enchantment ticks/functions and entity attributes; synthetic server-side rider input/relations, not a connected client or actual mount/dismount events.");r.addProperty("network_player_tested",false);
        if(error!=null){r.addProperty("error",error.toString());error.printStackTrace();}
        try{getDataFolder().mkdirs();Files.writeString(getDataFolder().toPath().resolve("result.json"),new GsonBuilder().setPrettyPrinting().create().toJson(r));}catch(Exception ex){ex.printStackTrace();error=ex;}
        getLogger().info("R3915 SWIFT "+(error==null?"PASS":"FAIL")+" nonce="+nonce);
    }
}
