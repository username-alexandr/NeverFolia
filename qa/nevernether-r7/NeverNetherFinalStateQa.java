import java.nio.file.*;
import java.util.*;
import com.google.gson.*;
import net.minecraft.SharedConstants;
import net.minecraft.server.Bootstrap;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.commands.arguments.blocks.BlockStateParser;

/** Real 26.2 block-state parser; no world or registry fallback is synthesized. */
public final class NeverNetherFinalStateQa {
    public static void main(String[] args) throws Exception {
        if (args.length != 2) throw new IllegalArgumentException("usage: values.txt output.json");
        SharedConstants.tryDetectVersion(); Bootstrap.bootStrap();
        var failures = new TreeMap<String, String>(); int total = 0;
        for (String value : new TreeSet<>(Files.readAllLines(Path.of(args[0])))) {
            total++;
            try { BlockStateParser.parseForBlock(BuiltInRegistries.BLOCK, value, true); }
            catch (com.mojang.brigadier.exceptions.CommandSyntaxException e) { failures.put(value, e.getMessage()); }
        }
        if (total == 0) throw new IllegalArgumentException("Empty final-state sample");
        var out = new JsonObject(); out.addProperty("schema", 1); out.addProperty("distinct_states", total);
        out.addProperty("valid", total - failures.size()); out.addProperty("passed", failures.isEmpty());
        out.add("failures", new Gson().toJsonTree(failures));
        Files.writeString(Path.of(args[1]), new GsonBuilder().setPrettyPrinting().create().toJson(out));
        System.out.println("Final-state codec: " + (total-failures.size()) + "/" + total);
        if (!failures.isEmpty()) System.exit(2);
    }
}
