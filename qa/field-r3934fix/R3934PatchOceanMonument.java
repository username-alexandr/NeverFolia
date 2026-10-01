import java.nio.file.Files;
import java.nio.file.Path;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.InsnList;
import org.objectweb.asm.tree.InsnNode;
import org.objectweb.asm.tree.MethodInsnNode;
import org.objectweb.asm.tree.MethodNode;
import org.objectweb.asm.tree.VarInsnNode;

public final class R3934PatchOceanMonument {
    private static final String TARGET =
        "neverOverworldMonumentBaseY";
    private static final String DESC =
        "(Lnet/minecraft/world/level/levelgen/structure/Structure$GenerationContext;)I";
    private static final String HELPER =
        "net/minecraft/world/level/levelgen/structure/structures/NeverOverworldOceanMonumentR34";

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException("usage: input.class output.class");
        }

        byte[] input = Files.readAllBytes(Path.of(args[0]));
        ClassNode node = new ClassNode(Opcodes.ASM9);
        new ClassReader(input).accept(node, 0);

        int patched = 0;
        for (MethodNode method : node.methods) {
            if (!TARGET.equals(method.name) || !DESC.equals(method.desc)) continue;

            InsnList code = new InsnList();
            code.add(new VarInsnNode(Opcodes.ALOAD, 0));
            code.add(new MethodInsnNode(
                Opcodes.INVOKESTATIC,
                HELPER,
                "resolveBaseY",
                DESC,
                false
            ));
            code.add(new InsnNode(Opcodes.IRETURN));

            method.instructions.clear();
            method.instructions.add(code);
            method.tryCatchBlocks.clear();
            if (method.localVariables != null) method.localVariables.clear();
            method.maxStack = 1;
            method.maxLocals = 1;
            ++patched;
        }

        if (patched != 1) {
            throw new IllegalStateException("expected exactly one monument base resolver, got " + patched);
        }

        ClassWriter writer = new ClassWriter(ClassWriter.COMPUTE_MAXS);
        node.accept(writer);
        Files.createDirectories(Path.of(args[1]).getParent());
        Files.write(Path.of(args[1]), writer.toByteArray());
        System.out.println("R3934_ASM_PATCH monument base resolver replaced");
    }
}
