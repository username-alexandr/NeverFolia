package neverfolia.qa.r395;

import java.io.IOException;
import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.MessageDigest;
import java.security.ProtectionDomain;
import java.util.HexFormat;
import java.util.concurrent.atomic.AtomicBoolean;

/** CI-only: replaces one observer class, never a terrain or entity class. */
public final class AuditAgent {
    private static final String TARGET = "net/minecraft/world/level/chunk/NeverOverworldWaterAuditR38";
    private static byte[] resource(String name) throws IOException {
        try (var input = AuditAgent.class.getResourceAsStream(name)) {
            if (input == null) throw new IOException("Missing agent resource: " + name);
            return input.readAllBytes();
        }
    }
    public static void premain(String args, Instrumentation instrumentation) throws Exception {
        if (System.getProperty("neverfolia.waterAuditRunId", "").isBlank()) {
            throw new IllegalArgumentException("A unique waterAuditRunId is required");
        }
        final byte[] replacement = resource("/r395/audit.class");
        final String expected = new String(resource("/r395/expected.sha256"), java.nio.charset.StandardCharsets.US_ASCII).trim();
        final AtomicBoolean applied = new AtomicBoolean();
        instrumentation.addTransformer(new ClassFileTransformer() {
            @Override public byte[] transform(ClassLoader loader, String name, Class<?> redefining,
                                               ProtectionDomain domain, byte[] original) {
                if (!TARGET.equals(name)) return null;
                try {
                    String actual = HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(original));
                    if (redefining != null || !actual.equals(expected) || !applied.compareAndSet(false, true)) {
                        throw new IllegalStateException("Unexpected or repeated observer definition: " + actual);
                    }
                    System.err.println("NL_R395_AUDIT_AGENT_APPLIED original=" + actual
                        + " run=" + System.getProperty("neverfolia.waterAuditRunId"));
                    return replacement.clone();
                } catch (Exception error) {
                    // JVM transformers can be ignored on failure. The external evidence gate
                    // therefore requires exactly one APPLIED marker and rejects REJECTED.
                    System.err.println("NL_R395_AUDIT_AGENT_REJECTED " + error);
                    return null;
                }
            }
        }, false);
    }
}
