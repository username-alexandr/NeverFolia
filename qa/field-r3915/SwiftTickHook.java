import java.lang.classfile.*;
import java.lang.classfile.instruction.InvokeInstruction;
import java.lang.constant.*;
import java.lang.reflect.AccessFlag;
import java.nio.file.*;

/** Standard Java 25 build-time transform. Verification mode also validates the
 * final class assembled with byte-preserved original structural attributes.
 */
public final class SwiftTickHook {
    private static final String TYPE="net/minecraft/world/item/enchantment/EnchantmentHelper";
    private static final String HELPER="net/minecraft/world/item/enchantment/NeverFoliaSwiftLifecycleR3915";
    private static final String DESC="(Lnet/minecraft/server/level/ServerLevel;Lnet/minecraft/world/entity/LivingEntity;)V";
    private static boolean target(MethodModel m){return m.methodName().equalsString("tickEffects")&&m.methodType().equalsString(DESC);}
    private static void verify(ClassFile cf,byte[] bytes){
        var errors=cf.verify(bytes);if(!errors.isEmpty())throw new IllegalStateException(errors.toString());
        var model=cf.parse(bytes);
        if(!model.thisClass().asInternalName().equals(TYPE))throw new IllegalArgumentException("Wrong verified class");
        var matches=model.methods().stream().filter(SwiftTickHook::target).toList();
        if(matches.size()!=1)throw new IllegalStateException("Wrong method count");
        var method=matches.getFirst();
        long count=method.code().orElseThrow().elementStream().filter(e->e instanceof InvokeInstruction i&&i.owner().asInternalName().equals(HELPER)&&i.name().equalsString("tick")).count();
        if(count!=1)throw new IllegalStateException("Wrong hook count");
        System.out.println("SWIFT_TICK_HOOK descriptor="+DESC+" hooks="+count+" verify=PASS");
    }
    public static void main(String[] args)throws Exception {
        if(args.length!=2)throw new IllegalArgumentException("input.class output.class OR --verify final.class");
        ClassFile cf=ClassFile.of();
        if(args[0].equals("--verify")){verify(cf,Files.readAllBytes(Path.of(args[1])));return;}
        Path input=Path.of(args[0]),output=Path.of(args[1]);
        if(Files.exists(output))throw new IllegalArgumentException("Output exists");
        byte[] raw=Files.readAllBytes(input);ClassModel model=cf.parse(raw);
        if(!model.thisClass().asInternalName().equals(TYPE))throw new IllegalArgumentException("Wrong class");
        var matches=model.methods().stream().filter(SwiftTickHook::target).toList();
        if(matches.size()!=1||!matches.getFirst().flags().has(AccessFlag.STATIC)||matches.getFirst().code().isEmpty())throw new IllegalArgumentException("Wrong target");
        for(var e:matches.getFirst().code().orElseThrow())if(e instanceof InvokeInstruction i&&i.owner().asInternalName().contains("NeverFoliaSwiftLifecycle"))throw new IllegalArgumentException("Hook already exists");
        CodeTransform insert=new CodeTransform(){
            @Override public void atStart(CodeBuilder b){b.aload(1).invokestatic(ClassDesc.of(HELPER.replace('/','.')),"tick",MethodTypeDesc.ofDescriptor("(Lnet/minecraft/world/entity/LivingEntity;)V"));}
            @Override public void accept(CodeBuilder b,CodeElement e){b.with(e);}
        };
        byte[] patched=cf.transformClass(model,ClassTransform.transformingMethodBodies(SwiftTickHook::target,insert));
        verify(cf,patched);Files.write(output,patched,StandardOpenOption.CREATE_NEW);
    }
}
