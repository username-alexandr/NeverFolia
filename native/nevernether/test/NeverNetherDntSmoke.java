import com.mojang.brigadier.CommandDispatcher;
import net.minecraft.SharedConstants;
import net.minecraft.server.Bootstrap;
import net.minecraft.commands.Commands;
import net.minecraft.commands.CommandSourceStack;
import net.minecraft.server.commands.NeverNetherDntCommands;
import net.minecraft.server.permissions.PermissionSet;

/** Registry/parser and fail-closed execution checks. No world or fake entity is created. */
public class NeverNetherDntSmoke {
 public static void main(String[] args) throws Exception {
  SharedConstants.tryDetectVersion();Bootstrap.bootStrap();
  var dispatcher=new CommandDispatcher<CommandSourceStack>();NeverNetherDntCommands.register(dispatcher);
  var compilation=Commands.createCompilationContext(PermissionSet.ALL_PERMISSIONS);
  int checks=0;
  for(String action:NeverNetherDntCommands.ACTIONS) {
   var parsed=dispatcher.parse("neverfolia:dnt "+action,compilation);
   if(parsed.getReader().canRead() || !parsed.getExceptions().isEmpty())throw new AssertionError(action);checks++;
   try {dispatcher.execute(parsed);throw new AssertionError("entity-less action accepted "+action);}
   catch(com.mojang.brigadier.exceptions.CommandSyntaxException expected){checks++;}
  }
  for(String root:new String[]{"data","scoreboard","item","tag","function","loot"}) {
   if(dispatcher.getRoot().getChild(root)!=null)throw new AssertionError("globally enabled "+root);checks++;
  }
  for(String command:new String[]{"neverfolia:dnt data merge entity @s {}","neverfolia:dnt call_trade_6","neverfolia:dnt sprint_on @e","neverfolia:dnt fireball_0"}) {
   try{dispatcher.execute(command,compilation);throw new AssertionError("unlisted command accepted");}
   catch(com.mojang.brigadier.exceptions.CommandSyntaxException expected){checks++;}
  }
  var unprivileged=Commands.createCompilationContext(PermissionSet.NO_PERMISSIONS);
  var parse=dispatcher.parse("neverfolia:dnt sprint_on",unprivileged);
  if(!parse.getReader().canRead())throw new AssertionError("permission gate absent");checks++;
  System.out.println("NN-DNT-R6: "+checks+" command parser/permission/fail-closed checks passed; not in-world QA");
 }
}
