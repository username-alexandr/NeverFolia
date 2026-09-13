package net.minecraft.world.level.levelgen.structure.pools;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

/** Immutable-input quota calculation. No counters shared between starts or threads. */
public final class NeverNetherPieceBudget {
    private NeverNetherPieceBudget() { }

    public record Entry(String group, int limit) {
        public Entry {
            if (group == null || group.isBlank() || limit < 0 || limit > 1024) {
                throw new IllegalArgumentException("Invalid NeverNether piece quota");
            }
        }
    }

    /** Accepted entries only; probing a rejected candidate consumes no quota.
     * Inconsistent limits for a group use the most restrictive accepted/candidate
     * limit, so differently named templates cannot bypass a shared group limit.
     */
    public static boolean allows(List<Entry> accepted, List<Entry> candidate) {
        if (candidate.isEmpty()) return true; // Vanilla fast path.
        Map<String, Integer> counts = new HashMap<>();
        Map<String, Integer> limits = new HashMap<>();
        for (Entry entry : accepted) add(entry, counts, limits);
        for (Entry entry : candidate) add(entry, counts, limits);
        for (Entry entry : candidate) {
            if (counts.get(entry.group()) > limits.get(entry.group())) return false;
        }
        return true;
    }

    private static void add(Entry entry, Map<String, Integer> counts, Map<String, Integer> limits) {
        counts.merge(entry.group(), 1, Math::addExact);
        limits.merge(entry.group(), entry.limit(), Math::min);
    }
}
