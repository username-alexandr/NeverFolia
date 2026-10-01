import java.nio.file.Files;
import java.nio.file.Path;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.FrameNode;
import org.objectweb.asm.tree.InsnList;
import org.objectweb.asm.tree.InsnNode;
import org.objectweb.asm.tree.JumpInsnNode;
import org.objectweb.asm.tree.LabelNode;
import org.objectweb.asm.tree.MethodInsnNode;
import org.objectweb.asm.tree.MethodNode;
import org.objectweb.asm.tree.VarInsnNode;

public final class R3934PatchOceanMonument {
    private static final String CONTEXT =
        "Lnet/minecraft/world/level/levelgen/structure/Structure$GenerationContext;";
    private static final String BASE_DESC = "(" + CONTEXT + ")I";
    private static final String FIND_DESC =
        "(" + CONTEXT + ")Ljava/util/Optional;";
    private static final String HELPER =
        "net/minecraft/world/level/levelgen/structure/structures/NeverOverworldOceanMonumentR34";

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException("usage: input.class output.class");
        }

        byte[] input = Files.readAllBytes(Path.of(args[0]));
        ClassNode node = new ClassNode(Opcodes.ASM9);
        new ClassReader(input).accept(node, 0);

        int basePatched = 0;
        int gatePatched = 0;

        for (MethodNode method : node.methods) {
            if ("neverOverworldMonumentBaseY".equals(method.name) && BASE_DESC.equals(method.desc)) {
                InsnList code = new InsnList();
                code.add(new VarInsnNode(Opcodes.ALOAD, 0));
                code.add(new MethodInsnNode(
                    Opcodes.INVOKESTATIC, HELPER, "resolveBaseY", BASE_DESC, false
                ));
                code.add(new InsnNode(Opcodes.IRETURN));

                method.instructions.clear();
                method.instructions.add(code);
                method.tryCatchBlocks.clear();
                if (method.localVariables != null) method.localVariables.clear();
                method.maxStack = 1;
                method.maxLocals = 1;
                ++basePatched;
                continue;
            }

            if ("findGenerationPoint".equals(method.name) && FIND_DESC.equals(method.desc)) {
                LabelNode proceed = new LabelNode();
                InsnList guard = new InsnList();
                guard.add(new VarInsnNode(Opcodes.ALOAD, 1));
                guard.add(new MethodInsnNode(
                    Opcodes.INVOKESTATIC,
                    HELPER,
                    "allowsGeneration",
                    "(" + CONTEXT + ")Z",
                    false
                ));
                guard.add(new JumpInsnNode(Opcodes.IFNE, proceed));
                guard.add(new MethodInsnNode(
                    Opcodes.INVOKESTATIC,
                    "java/util/Optional",
                    "empty",
                    "()Ljava/util/Optional;",
                    false
                ));
                guard.add(new InsnNode(Opcodes.ARETURN));
                guard.add(proceed);
                guard.add(new FrameNode(Opcodes.F_SAME, 0, null, 0, null));
                method.instructions.insert(guard);
                ++gatePatched;
            }
        }

        if (basePatched != 1 || gatePatched != 1) {
            throw new IllegalStateException(
                "expected one base patch and one generation gate, got base="
                    + basePatched + " gate=" + gatePatched
            );
        }

        ClassWriter writer = new ClassWriter(ClassWriter.COMPUTE_MAXS);
        node.accept(writer);
        Files.createDirectories(Path.of(args[1]).getParent());
        Files.write(Path.of(args[1]), writer.toByteArray());
        System.out.println("R3934_ASM_PATCH monument base + steep-seabed gate replaced");
    }
}
