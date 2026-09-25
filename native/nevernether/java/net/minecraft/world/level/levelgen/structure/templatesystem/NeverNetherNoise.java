package net.minecraft.world.level.levelgen.structure.templatesystem;

import java.util.LinkedHashMap;
import java.util.Map;
import net.minecraft.world.level.levelgen.structure.templatesystem.noise.OpenSimplex2F;

/** Bounded cache of fully constructed, read-only samplers. Never reseed a shared sampler. */
public final class NeverNetherNoise {
    private NeverNetherNoise() { }
    private record Seeded(long seed, OpenSimplex2F noise) { }
    private static final Map<Long, Seeded> CACHE = new LinkedHashMap<>(16, 0.75f, true);
    private static volatile Seeded last;

    private static Seeded sampler(long seed) {
        Seeded snapshot = last;
        if (snapshot != null && snapshot.seed == seed) return snapshot;
        synchronized (CACHE) {
            snapshot = CACHE.get(seed);
            if (snapshot == null) {
                snapshot = new Seeded(seed, new OpenSimplex2F(seed));
                CACHE.put(seed, snapshot);
                if (CACHE.size() > 16) CACHE.remove(CACHE.keySet().iterator().next());
            }
            last = snapshot;
        }
        return snapshot;
    }

    public static double sample(long seed, double x, double y, double z) {
        if (!Double.isFinite(x) || !Double.isFinite(y) || !Double.isFinite(z)) {
            throw new IllegalArgumentException("Non-finite noise coordinate");
        }
        return sampler(seed).noise.noise3_Classic(x, y, z);
    }
}
