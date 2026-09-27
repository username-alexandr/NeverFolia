package net.minecraft.world.level.chunk;

import java.io.DataOutputStream;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.BitSet;
import java.util.zip.GZIPOutputStream;

/** Diagnostic snapshot only: no block writes, no chunk loading, no world repair. */
public final class OceanWitnessR397 {
    private OceanWitnessR397() {}
    public static void record(String directory, int cx, int cz, byte[] cells,
                              boolean[] sky, BitSet extraLava,
                              OceanConnectivityR395.Proof proof) {
        if (directory.isEmpty() || cx < -1701 || cx > -1697 || cz < -771 || cz > -767) return;
        if (cells.length != 48 * 48 * 640 || sky.length != 48 * 48)
            throw new IllegalArgumentException("R397 witness dimensions differ");
        try {
            Path out = Path.of(directory).resolve("witness");
            Files.createDirectories(out);
            try (DataOutputStream stream = new DataOutputStream(new GZIPOutputStream(
                    Files.newOutputStream(out.resolve(cx + "_" + cz + ".bin.gz"),
                        StandardOpenOption.CREATE_NEW)))) {
                stream.writeInt(0x52333937); stream.writeInt(cx); stream.writeInt(cz);
                stream.writeInt(48); stream.writeInt(48); stream.writeInt(640); stream.writeInt(-511);
                stream.writeInt(cells.length); stream.write(cells);
                stream.writeInt(sky.length); for (boolean value : sky) stream.writeBoolean(value);
                byte[] lava = extraLava.toByteArray(), connected = proof.connected().toByteArray();
                stream.writeInt(lava.length); stream.write(lava);
                stream.writeInt(connected.length); stream.write(connected);
            }
        } catch (IOException error) {
            throw new IllegalStateException("Cannot retain immutable R397 witness", error);
        }
    }
}
