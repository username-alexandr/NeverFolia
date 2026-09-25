import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import org.bukkit.Bukkit;
import org.bukkit.craftbukkit.CraftWorld;
import org.bukkit.event.EventHandler;
import org.bukkit.event.Listener;
import org.bukkit.event.server.ServerLoadEvent;
import org.bukkit.plugin.java.JavaPlugin;
import net.minecraft.commands.CommandSource;
import net.minecraft.commands.CommandSourceStack;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.resources.Identifier;
import net.minecraft.server.commands.NeverNetherDntCommands;
import net.minecraft.server.commands.data.EntityDataAccessor;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.permissions.PermissionSet;
import net.minecraft.world.entity.*;
import net.minecraft.world.entity.monster.Ghast;
import net.minecraft.world.entity.npc.villager.AbstractVillager;
import net.minecraft.world.entity.projectile.Projectile;
import net.minecraft.world.entity.projectile.hurtingprojectile.LargeFireball;
import net.minecraft.world.effect.MobEffects;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.Items;
import net.minecraft.network.chat.Component;
import net.minecraft.world.phys.Vec2;
import net.minecraft.world.phys.Vec3;

/** LOCAL QA plugin; never installed in production builds. Runs on one actual Folia region. */
public final class NeverNetherDntQaPlugin extends JavaPlugin implements Listener {
 private final List<String> checks=new ArrayList<>();
 private final List<Entity> created=new ArrayList<>();
 private volatile LargeFireball capturedBall;
 @EventHandler public void launched(org.bukkit.event.entity.ProjectileLaunchEvent event) {
  Entity e=((org.bukkit.craftbukkit.entity.CraftEntity)event.getEntity()).getHandle();
  if(e instanceof LargeFireball ball && ca.spottedleaf.moonrise.common.util.TickThread.isTickThreadFor(ball) && ball.entityTags().contains("dnt_ghasted_fireball")) capturedBall=ball;
 }
 private void check(boolean ok,String label) {if(!ok)throw new AssertionError(label);checks.add(label);}
 @Override public void onEnable(){Bukkit.getPluginManager().registerEvents(this,this);}
 @EventHandler public void loaded(ServerLoadEvent ignored) {
  var world=Bukkit.getWorlds().stream().filter(w->w.getEnvironment()==org.bukkit.World.Environment.NETHER).findFirst().orElseThrow();
  world.getChunkAtAsync(0,0,true).thenAccept(chunk->Bukkit.getRegionScheduler().execute(this,world,0,0,()->run(((CraftWorld)world).getHandle())));
 }
 private Entity spawn(ServerLevel level,String id) {
  var type=BuiltInRegistries.ENTITY_TYPE.getOptional(Identifier.fromNamespaceAndPath("minecraft",id)).orElseThrow();
  var e=type.create(level,EntitySpawnReason.COMMAND);if(e==null)throw new AssertionError("create "+id);
  e.setPos(8.0,200.0,8.0);e.setNoGravity(true);e.setInvulnerable(true);
  if(e instanceof Mob mob)mob.setNoAi(true);
  if(!level.addFreshEntity(e))throw new AssertionError("spawn "+id);created.add(e);return e;
 }
 private CommandSourceStack source(ServerLevel level,Entity e) {
  return new CommandSourceStack(CommandSource.NULL,e.position(),Vec2.ZERO,level,PermissionSet.ALL_PERMISSIONS,"NN-QA",Component.literal("NN-QA"),level.getServer(),e);
 }
 private int action(ServerLevel level,Entity e,String s)throws Exception{return NeverNetherDntCommands.run(source(level,e),s);}
 private void run(ServerLevel level){
  String error=null;
  try {
   var villager=(AbstractVillager)spawn(level,"villager");
   check(action(level,villager,"sprint_on")==1 && villager.entityTags().contains("sprinting"),"region-owned tag add");
   action(level,villager,"sprint_off");check(!villager.entityTags().contains("sprinting"),"region-owned tag remove");
   villager.setItemSlot(EquipmentSlot.SADDLE,new ItemStack(Items.SADDLE));action(level,villager,"clear_saddle");
   check(villager.getItemBySlot(EquipmentSlot.SADDLE).isEmpty(),"saddle cleared");
   action(level,villager,"regenerate");var effect=villager.getEffect(MobEffects.REGENERATION);
   check(effect!=null && effect.getDuration()==1 && effect.getAmplifier()==6 && !effect.isVisible(),"regeneration duration/amplifier/particles");
   var boss=(Ghast)spawn(level,"ghast");boss.addTag("dnt_ghast_boss");
   for(int n=1;n<=9;n++)check(action(level,boss,"minion_increment")==Math.min(n,7),"minion count "+n);
   check(boss.entityTags().contains(NeverNetherDntCommands.LIMIT_TAG),"minion cap tag at 7");
   check(new EntityDataAccessor(boss).getData().toString().contains(NeverNetherDntCommands.LIMIT_TAG),"cap is persisted in entity NBT");
   var second=(Ghast)spawn(level,"ghast");second.addTag("dnt_ghast_boss");
   check(action(level,second,"minion_increment")==1,"independent boss counter");
   var originalOffers=villager.getOffers().size();
   action(level,villager,"offer_prepend");
   check(villager.getOffers().size()==originalOffers+1,"offer prepended");
   check(villager.getOffers().getFirst().getBaseCostA().getCount()==14,"initial price preserved");
   check(villager.getOffers().getFirst().getCostB().is(Items.COMPASS),"compass second cost preserved");
   villager.setItemSlot(EquipmentSlot.MAINHAND,new ItemStack(Items.EMERALD,11));action(level,villager,"offer_buy");
   check(villager.getOffers().getFirst().getBaseCostA().getCount()==11,"offer copies generated emerald count");
   villager.setItemSlot(EquipmentSlot.MAINHAND,new ItemStack(Items.DIAMOND));action(level,villager,"offer_sell");
   check(villager.getOffers().getFirst().getResult().is(Items.DIAMOND),"offer copies generated result");
   check(villager.getOffers().getFirst().getMaxUses()==1,"max uses preserved");
   action(level,villager,"loot_emeralds");check(villager.getItemBySlot(EquipmentSlot.MAINHAND).is(Items.EMERALD),"exact emerald loot table executes");
   for(int n=2;n<=5;n++){
    action(level,villager,"loot_chart_"+n);check(villager.getItemBySlot(EquipmentSlot.MAINHAND).is(Items.FILLED_MAP),"chart table level "+n);
    action(level,villager,"trade_"+n+"_added");check(villager.entityTags().contains("trade"+n+"added"),"trade tag "+n);
   }
   for(int power=1;power<=3;power++){
    var arrow=(Projectile)spawn(level,"arrow");arrow.setOwner(boss);arrow.setDeltaMovement(0.25,0.5,-0.75);
    var owner=arrow.owner;int before=level.getEntitiesOfClass(LargeFireball.class,arrow.getBoundingBox().inflate(3),e->true).size();
    capturedBall=null;
    check(action(level,arrow,"fireball_"+power)==1,"projectile converted "+power);
    var ball=capturedBall;
    check(ball!=null && ca.spottedleaf.moonrise.common.util.TickThread.isTickThreadFor(ball) && ball.explosionPower==power,"accepted projectile event "+power);created.add(ball);
    check(arrow.isRemoved(),"source projectile retired "+power);
    check(ball.owner==owner && ball.getDeltaMovement().equals(new Vec3(0.25,0.5,-0.75)),"projectile owner/motion preserved "+power);
   }
   // Actual fixed-function invocation, not just parsing. The function manager
   // drains/join its execution context synchronously on this owner tick thread.
   var trader=(AbstractVillager)spawn(level,"villager");int before=trader.getOffers().size();
   action(level,trader,"call_trade_2");
   check(trader.getOffers().size()==before+1 && trader.entityTags().contains("trade2added"),"fixed function call executes the full trade chain");
   for(String name:new String[]{"data","item","tag","scoreboard","function","loot"})
    check(level.getServer().getCommands().getDispatcher().getRoot().getChild(name)==null,"generic command remains disabled: "+name);
  }catch(Throwable ex){error=ex.toString();ex.printStackTrace();}
  finally {
   for(Entity e:created)if(!e.isRemoved())e.discard();
   try{getDataFolder().mkdirs();var json=new com.google.gson.JsonObject();json.addProperty("passed",error==null);json.addProperty("checks",checks.size());json.add("labels",new com.google.gson.Gson().toJsonTree(checks));if(error!=null)json.addProperty("error",error);Files.writeString(getDataFolder().toPath().resolve("result.json"),new com.google.gson.GsonBuilder().setPrettyPrinting().create().toJson(json));}
   catch(Exception ex){ex.printStackTrace();}
   getLogger().info("NN-DNT-R6 REGION QA "+(error==null?"PASS":"FAIL")+" checks="+checks.size());
  }
 }
}
