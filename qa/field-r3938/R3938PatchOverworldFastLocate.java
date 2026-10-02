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

public final class R3938PatchOverworldFastLocate {
    private static final String TARGET =
        "net/minecraft/world/level/chunk/NeverOverworldFastLocate";
    private static final String NETHER =
        "net/minecraft/world/level/chunk/NeverNetherFastLocate";

    private static final String HANDLES_DESC =
        "(Lnet/minecraft/core/HolderSet;)Z";
    private static final String HANDLES_LEVEL_DESC =
        "(Lnet/minecraft/server/level/ServerLevel;Lnet/minecraft/core/HolderSet;)Z";
    private static final String FIND_DESC =
        "(Lnet/minecraft/world/level/chunk/ChunkGenerator;"
        + "Lnet/minecraft/server/level/ServerLevel;"
        + "Lnet/minecraft/core/HolderSet;"
        + "Lnet/minecraft/core/BlockPos;I)"
        + "Lcom/mojang/datafixers/util/Pair;";

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException("usage: input.class output.class");
        }

        byte[] input = Files.readAllBytes(Path.of(args[0]));
        ClassNode node = new ClassNode(Opcodes.ASM9);
        new ClassReader(input).accept(node, 0);
        if (!TARGET.equals(node.name)) {
            throw new IllegalStateException("unexpected target " + node.name);
        }

        int handlesPatched = 0;
        int findPatched = 0;

        for (MethodNode method : node.methods) {
            if ("handles".equals(method.name) && HANDLES_DESC.equals(method.desc)) {
                LabelNode original = new LabelNode();
                InsnList code = new InsnList();
                code.add(new VarInsnNode(Opcodes.ALOAD, 0));
                code.add(new MethodInsnNode(
                    Opcodes.INVOKESTATIC,
                    NETHER,
                    "handles",
                    HANDLES_DESC,
                    false
                ));
                code.add(new JumpInsnNode(Opcodes.IFEQ, original));
                code.add(new InsnNode(Opcodes.ICONST_1));
                code.add(new InsnNode(Opcodes.IRETURN));
                code.add(original);
                code.add(new FrameNode(Opcodes.F_SAME, 0, null, 0, null));
                method.instructions.insertBefore(method.instructions.getFirst(), code);
                ++handlesPatched;
                continue;
            }

            if ("find".equals(method.name) && FIND_DESC.equals(method.desc)) {
                LabelNode original = new LabelNode();
                InsnList code = new InsnList();
                code.add(new VarInsnNode(Opcodes.ALOAD, 1));
                code.add(new VarInsnNode(Opcodes.ALOAD, 2));
                code.add(new MethodInsnNode(
                    Opcodes.INVOKESTATIC,
                    NETHER,
                    "handles",
                    HANDLES_LEVEL_DESC,
                    false
                ));
                code.add(new JumpInsnNode(Opcodes.IFEQ, original));
                code.add(new VarInsnNode(Opcodes.ALOAD, 0));
                code.add(new VarInsnNode(Opcodes.ALOAD, 1));
                code.add(new VarInsnNode(Opcodes.ALOAD, 2));
                code.add(new VarInsnNode(Opcodes.ALOAD, 3));
                code.add(new VarInsnNode(Opcodes.ILOAD, 4));
                code.add(new MethodInsnNode(
                    Opcodes.INVOKESTATIC,
                    NETHER,
                    "find",
                    FIND_DESC,
                    false
                ));
                code.add(new InsnNode(Opcodes.ARETURN));
                code.add(original);
                code.add(new FrameNode(Opcodes.F_SAME, 0, null, 0, null));
                method.instructions.insertBefore(method.instructions.getFirst(), code);
                ++findPatched;
            }
        }

        if (handlesPatched != 1 || findPatched != 1) {
            throw new IllegalStateException(
                "expected handles/find patches once, got "
                + handlesPatched + "/" + findPatched
            );
        }

        ClassWriter writer = new ClassWriter(ClassWriter.COMPUTE_MAXS);
        node.accept(writer);
        Path output = Path.of(args[1]);
        Files.createDirectories(output.getParent());
        Files.write(output, writer.toByteArray());
        System.out.println("R3938_ASM_PATCH NeverOverworldFastLocate -> NeverNetherFastLocate delegation");
    }
}
