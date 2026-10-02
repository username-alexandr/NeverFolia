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
    private static final String POLICY =
        "net/minecraft/world/level/chunk/NeverNetherFastLocatePolicy";

    private static final String HANDLES_DESC =
        "(Lnet/minecraft/core/HolderSet;)Z";
    private static final String TERRAIN_DESC =
        "(Lnet/minecraft/world/level/chunk/ChunkGenerator;"
        + "Lnet/minecraft/server/level/ServerLevel;"
        + "Lnet/minecraft/world/level/chunk/ChunkGeneratorStructureState;"
        + "Lnet/minecraft/world/level/ChunkPos;"
        + "Lnet/minecraft/core/Holder;)Z";
    private static final String CUSTOM_DESC =
        "(Lnet/minecraft/core/Holder;)Z";

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
        int terrainPatched = 0;

        for (MethodNode method : node.methods) {
            if ("handles".equals(method.name) && HANDLES_DESC.equals(method.desc)) {
                InsnList code = new InsnList();
                code.add(new VarInsnNode(Opcodes.ALOAD, 0));
                code.add(new MethodInsnNode(
                    Opcodes.INVOKESTATIC,
                    POLICY,
                    "handles",
                    HANDLES_DESC,
                    false
                ));
                code.add(new InsnNode(Opcodes.IRETURN));

                method.instructions.clear();
                method.instructions.add(code);
                method.tryCatchBlocks.clear();
                if (method.localVariables != null) method.localVariables.clear();
                method.maxStack = 1;
                method.maxLocals = 1;
                ++handlesPatched;
                continue;
            }

            if ("passesNeverOverworldTerrain".equals(method.name)
                && TERRAIN_DESC.equals(method.desc)) {
                LabelNode original = new LabelNode();
                InsnList guard = new InsnList();

                guard.add(new VarInsnNode(Opcodes.ALOAD, 4));
                guard.add(new MethodInsnNode(
                    Opcodes.INVOKESTATIC,
                    POLICY,
                    "isCustomNether",
                    CUSTOM_DESC,
                    false
                ));
                guard.add(new JumpInsnNode(Opcodes.IFEQ, original));

                guard.add(new VarInsnNode(Opcodes.ALOAD, 0));
                guard.add(new VarInsnNode(Opcodes.ALOAD, 1));
                guard.add(new VarInsnNode(Opcodes.ALOAD, 2));
                guard.add(new VarInsnNode(Opcodes.ALOAD, 3));
                guard.add(new VarInsnNode(Opcodes.ALOAD, 4));
                guard.add(new MethodInsnNode(
                    Opcodes.INVOKESTATIC,
                    POLICY,
                    "passesNetherTerrain",
                    TERRAIN_DESC,
                    false
                ));
                guard.add(new InsnNode(Opcodes.IRETURN));
                guard.add(original);
                guard.add(new FrameNode(Opcodes.F_SAME, 0, null, 0, null));

                method.instructions.insertBefore(method.instructions.getFirst(), guard);
                ++terrainPatched;
            }
        }

        if (handlesPatched != 1 || terrainPatched != 1) {
            throw new IllegalStateException(
                "expected handles/terrain patches once, got "
                + handlesPatched + "/" + terrainPatched
            );
        }

        ClassWriter writer = new ClassWriter(ClassWriter.COMPUTE_MAXS);
        node.accept(writer);
        Path output = Path.of(args[1]);
        Files.createDirectories(output.getParent());
        Files.write(output, writer.toByteArray());
        System.out.println(
            "R3938_ASM_PATCH NeverOverworldFastLocate extended for custom NeverNether"
        );
    }
}
