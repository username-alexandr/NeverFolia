import com.google.gson.*;
import java.nio.file.Files;
import java.util.*;
import org.bukkit.Bukkit;
import org.bukkit.GameMode;
import org.bukkit.Location;
import org.bukkit.craftbukkit.CraftWorld;
import org.bukkit.craftbukkit.entity.CraftPlayer;
import org.bukkit.event.*;
import org.bukkit.event.player.PlayerJoinEvent;
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

/** Isolated loopback client and actual mount API; key input is deliberately set
 * server-side. Uses real entity ownership, enchantment ticks and commands.
 * No reflection-based passenger graph, fake entity ownership or disabled checks.
 * This is not a graphical client or FOV rendering test.
 */
public final class R3915SwiftQa extends JavaPlugin implements Listener {
    private final JsonArray checks=new JsonArray(),levels=new JsonArray();
    private boolean started,finished;
    private ServerLevel level;
    private org.bukkit.World world;
    private org.bukkit.entity.Player player;
    private ServerPlayer driver;
    private HappyGhast ghast;
    private int tier=1;
    private final boolean baseline=Boolean.getBoolean("neverfolia.qaBaseline");
    private final String nonce=System.getProperty("neverfolia.qaNonce","");
    private static final Identifier FLIGHT=id("sprint_flight_speed"),FOV=id("boost_player_fov");
    private static Identifier id(String path){return Identifier.fromNamespaceAndPath("nova_structures",path);}
    private void check(boolean ok,String name){JsonObject r=new JsonObject();r.addProperty("name",name);r.addProperty("pass",ok);checks.add(r);if(!ok)throw new AssertionError(name);}
    @Override public void onEnable(){Bukkit.getPluginManager().registerEvents(this,this);}
    @EventHandler public void loaded(ServerLoadEvent e){
        try {
            world=Bukkit.getWorlds().stream().filter(w->w.getEnvironment()==org.bukkit.World.Environment.NORMAL).findFirst().orElseThrow();
            level=((CraftWorld)world).getHandle();
            Bukkit.getGlobalRegionScheduler().execute(this,()->{
                try{world.setChunkForceLoaded(0,0,true);world.getChunkAtAsync(0,0,true).whenComplete((c,error)->{
                    if(error!=null){finish(error);return;}
                    getLogger().info("R3915 LOOPBACK READY nonce="+nonce);
                });}catch(Throwable error){finish(error);}
            });
        }catch(Throwable error){finish(error);}
    }
    @EventHandler public void joined(PlayerJoinEvent e){
        if(started||!e.getPlayer().getName().equals("NLWaterQA"))return;started=true;
        player=e.getPlayer();player.setGameMode(GameMode.SURVIVAL);player.setInvulnerable(true);player.setGravity(false);
        player.teleportAsync(new Location(world,8.5,400,8.5)).whenComplete((ok,error)->{
            if(error!=null){finish(error);return;}
            Bukkit.getRegionScheduler().execute(this,world,0,0,()->{
                try{check(Boolean.TRUE.equals(ok),"connected player reached test region");driver=((CraftPlayer)player).getHandle();prepare();}catch(Throwable t){finish(t);}
            });
        });
    }
    private void input(boolean forward,boolean sprint){
        driver.setLastClientInput(new Input(forward,false,false,false,false,false,sprint));
        check(driver.getLastClientInput().forward()==forward&&driver.getLastClientInput().sprint()==sprint,"server-side key fixture matches requested keys");
    }
    private void tick(){EnchantmentHelper.tickEffects(level,ghast);}
    private void absent(AttributeInstance a,Identifier key,String why){check(a.getModifier(key)==null,why);}
    private void amount(AttributeInstance a,Identifier key,double expected,String why){
        var m=a.getModifier(key);check(m!=null&&Math.abs(m.amount()-expected)<1e-9&&m.operation()==AttributeModifier.Operation.ADD_MULTIPLIED_BASE,why);
    }
    private void prepare(){
        if(finished)return;
        try {
            check(!nonce.isEmpty(),"fresh nonce supplied");check(level.getSeed()==-4651369264513492755L,"actual seed");
            check(player.isOnline()&&!player.isOp(),"real connected non-operator player");
            check(ca.spottedleaf.moonrise.common.util.TickThread.isTickThreadFor(driver),"actual connected player ownership");
            if(tier==1){
                var dispatcher=level.getServer().getCommands().getDispatcher();
                for(String root:new String[]{"data","tag","scoreboard","function","item","loot"})check(dispatcher.getRoot().getChild(root)==null,"generic "+root+" stays disabled");
                var holder=level.registryAccess().lookupOrThrow(Registries.ENCHANTMENT).getOrThrow(ResourceKey.create(Registries.ENCHANTMENT,id("swift_soar")));
                var effects=holder.value().effects().get(EnchantmentEffectComponents.TICK);
                check(baseline?(effects==null||effects.isEmpty()):(effects!=null&&effects.size()==3),"loaded tick graph matches baseline/candidate");
                for(int n=1;n<=3;n++)check(level.getServer().getFunctions().get(id("swift_soar_"+n)).isPresent()!=baseline,"compiled function "+n);
            }
            input(false,false);
            absent(Objects.requireNonNull(driver.getAttribute(Attributes.MOVEMENT_SPEED)),FOV,"no preexisting rider modifier "+tier);
            var type=BuiltInRegistries.ENTITY_TYPE.getOptional(Identifier.fromNamespaceAndPath("minecraft","happy_ghast")).orElseThrow();
            ghast=(HappyGhast)type.create(level,EntitySpawnReason.COMMAND);
            check(ghast!=null,"create actual happy ghast "+tier);ghast.setPos(8,400,8);ghast.setNoAi(true);ghast.setNoGravity(true);
            var harness=BuiltInRegistries.ITEM.getOptional(Identifier.fromNamespaceAndPath("minecraft","white_harness")).orElseThrow();
            var holder=level.registryAccess().lookupOrThrow(Registries.ENCHANTMENT).getOrThrow(ResourceKey.create(Registries.ENCHANTMENT,id("swift_soar")));
            ItemStack item=new ItemStack(harness);item.enchant(holder,tier);ghast.setItemSlot(EquipmentSlot.BODY,item);
            check(level.addFreshEntity(ghast),"add real region-owned mount "+tier);
            Bukkit.getRegionScheduler().runDelayed(this,world,0,0,t->{
                try{check(ca.spottedleaf.moonrise.common.util.TickThread.isTickThreadFor(ghast),"registered mount ownership "+tier);check(driver.startRiding(ghast,true,true),"actual mount API "+tier);Bukkit.getRegionScheduler().runDelayed(this,world,0,0,x->testTier(),20);}catch(Throwable e){finish(e);}
            },2);
        }catch(Throwable e){finish(e);}
    }
    private void testTier(){
        try {
            int n=tier;
            check(player.isOnline()&&ghast.getControllingPassenger()==driver,"actual controlling connected player "+n);
            check(ca.spottedleaf.moonrise.common.util.TickThread.isTickThreadFor(ghast)&&ca.spottedleaf.moonrise.common.util.TickThread.isTickThreadFor(driver),"both entities owned by current region "+n);
            var flight=Objects.requireNonNull(ghast.getAttribute(Attributes.FLYING_SPEED));var fov=Objects.requireNonNull(driver.getAttribute(Attributes.MOVEMENT_SPEED));
            input(true,false);tick();absent(flight,FLIGHT,"forward alone does not boost "+n);
            input(true,true);tick();
            if(baseline){absent(flight,FLIGHT,"baseline has no flight effect "+n);absent(fov,FOV,"baseline has no rider effect "+n);}
            else {
                double speed=new double[]{.2,.35,.5}[n-1],zoom=new double[]{.1,.175,.25}[n-1];
                amount(flight,FLIGHT,speed,"actual enchantment tick applies flight modifier "+n);
                amount(fov,FOV,zoom,"actual enchantment tick applies rider modifier "+n);
                check(ghast.entityTags().contains("sprinting"),"native command owns sprint latch "+n);
                int count=flight.getModifiers().size();tick();check(flight.getModifiers().size()==count,"repeat does not stack "+n);
                input(true,false);tick();amount(flight,FLIGHT,speed,"forward retains sprint latch "+n);
                input(false,false);tick();absent(flight,FLIGHT,"releasing forward removes flight modifier "+n);absent(fov,FOV,"releasing forward removes rider modifier "+n);
                check(!ghast.entityTags().contains("sprinting"),"releasing forward clears latch "+n);
                input(true,true);tick();driver.stopRiding();tick();
                check(!driver.isPassenger(),"actual dismount API "+n);absent(flight,FLIGHT,"unridden mount loses boost "+n);
                JsonObject row=new JsonObject();row.addProperty("tier",n);row.addProperty("speed_modifier",speed);row.addProperty("rider_modifier",zoom);row.addProperty("residual_rider_modifier_after_detach",fov.getModifier(FOV)!=null);levels.add(row);
                // Fixture teardown only, after recording whether real cleanup failed.
                fov.removeModifier(FOV);
            }
            if(driver.isPassenger())driver.stopRiding();ghast.discard();ghast=null;
            if(tier++<3){Bukkit.getRegionScheduler().runDelayed(this,world,0,0,t->prepare(),2);return;}
            var low=net.minecraft.commands.Commands.createCompilationContext(PermissionSet.NO_PERMISSIONS);
            check(level.getServer().getCommands().getDispatcher().parse("neverfolia:dnt sprint_on",low).getReader().canRead(),"unprivileged bridge remains rejected");
            finish(null);
        }catch(Throwable e){finish(e);}
    }
    private synchronized void finish(Throwable error){
        if(finished)return;finished=true;
        JsonObject r=new JsonObject();r.addProperty("pass",error==null);r.addProperty("seed",level==null?0:level.getSeed());r.addProperty("nonce",nonce);r.addProperty("baseline",baseline);r.add("checks",checks);r.add("levels",levels);
        r.addProperty("scope","Real loopback non-operator player, mount/dismount, enchantment ticks/functions and attributes. Key input supplied server-side; no graphical client/FOV rendering test.");r.addProperty("network_player_tested",driver!=null&&player.isOnline());
        if(error!=null){r.addProperty("error",error.toString());error.printStackTrace();}
        try{getDataFolder().mkdirs();Files.writeString(getDataFolder().toPath().resolve("result.json"),new GsonBuilder().setPrettyPrinting().create().toJson(r));}catch(Exception e){e.printStackTrace();error=e;}
        getLogger().info("R3915 SWIFT "+(error==null?"PASS":"FAIL")+" nonce="+nonce);
    }
}
