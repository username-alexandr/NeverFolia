import java.lang.classfile.*;
import java.lang.classfile.instruction.InvokeInstruction;
import java.lang.constant.*;
import java.nio.file.*;

/** Build-time transformer, not a runtime agent. Only the exact static tickEffects
 * descriptor is patched; all other methods/elements pass through unchanged.
 * Uses the standard JDK 25 class-file API, no downloaded transformer dependency.
 */
public final class SwiftTickHook {
    private static final String TYPE="net/minecraft/world/item/enchantment/EnchantmentHelper";
    private static final String DESC="(Lnet/minecraft/server/level/ServerLevel;Lnet/minecraft/world/entity/LivingEntity;)V";
    private static boolean target(MethodModel m){return m.methodName().equalsString("tickEffects")&&m.methodType().equalsString(DESC);}
    public static void main(String[] args)throws Exception {
        if(args.length!=2)throw new IllegalArgumentException("input.class output.class");
        Path input=Path.of(args[0]),output=Path.of(args[1]);
        if(Files.exists(output))throw new IllegalArgumentException("Output exists");
        byte[] raw=Files.readAllBytes(input);ClassFile cf=ClassFile.of();ClassModel model=cf.parse(raw);
        if(!model.thisClass().asInternalName().equals(TYPE))throw new IllegalArgumentException("Wrong class");
        var matches=model.methods().stream().filter(SwiftTickHook::target).toList();
        if(matches.size()!=1||!matches.getFirst().flags().has(AccessFlag.STATIC)||matches.getFirst().code().isEmpty())throw new IllegalArgumentException("Wrong target");
        for(var e:matches.getFirst().code().orElseThrow())if(e instanceof InvokeInstruction i&&i.owner().asInternalName().contains("NeverFoliaSwiftLifecycle"))throw new IllegalArgumentException("Hook already exists");
        CodeTransform insert=new CodeTransform(){
            @Override public void atStart(CodeBuilder b){b.aload(1).invokestatic(ClassDesc.of("net.minecraft.world.item.enchantment.NeverFoliaSwiftLifecycleR3915"),"tick",MethodTypeDesc.ofDescriptor("(Lnet/minecraft/world/entity/LivingEntity;)V"));}
            @Override public void accept(CodeBuilder b,CodeElement e){b.with(e);}
        };
        byte[] patched=cf.transformClass(model,ClassTransform.transformingMethodBodies(SwiftTickHook::target,insert));
        var errors=cf.verify(patched);if(!errors.isEmpty())throw new IllegalStateException(errors.toString());
        var method=cf.parse(patched).methods().stream().filter(SwiftTickHook::target).findFirst().orElseThrow();
        long count=method.code().orElseThrow().elementStream().filter(e->e instanceof InvokeInstruction i&&i.owner().asInternalName().equals("net/minecraft/world/item/enchantment/NeverFoliaSwiftLifecycleR3915")).count();
        if(count!=1)throw new IllegalStateException("Wrong hook count");
        Files.write(output,patched,StandardOpenOption.CREATE_NEW);
        System.out.println("SWIFT_TICK_HOOK descriptor="+DESC+" hooks="+count+" verify=PASS");
    }
}
