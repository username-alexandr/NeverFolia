import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Executors;
import java.util.concurrent.Callable;
import net.minecraft.world.level.levelgen.structure.pools.NeverNetherPieceBudget;
import net.minecraft.world.level.levelgen.structure.pools.NeverNetherPieceBudget.Entry;

public final class NeverNetherPieceBudgetTest {
    private static int assertions;
    static void check(boolean condition, String label) {
        if (!condition) throw new AssertionError(label);
        assertions++;
    }
    static void invalid(Runnable action) {
        try { action.run(); throw new AssertionError("Expected invalid quota rejection"); }
        catch (IllegalArgumentException expected) { assertions++; }
    }
    public static void main(String[] args) throws Exception {
        Entry a = new Entry("shared", 1), b = new Entry("other", 1);
        check(NeverNetherPieceBudget.allows(List.of(), List.of(a)), "first occurrence");
        check(!NeverNetherPieceBudget.allows(List.of(a), List.of(a)), "accepted occurrence consumes quota");
        check(NeverNetherPieceBudget.allows(List.of(a), List.of(b)), "independent group");
        check(NeverNetherPieceBudget.allows(List.of(a), List.of()), "vanilla candidate unchanged");
        check(!NeverNetherPieceBudget.allows(List.of(), List.of(new Entry("zero", 0))), "zero cap");
        check(!NeverNetherPieceBudget.allows(List.of(), List.of(a, a)), "nested list cannot duplicate cap=1");
        check(NeverNetherPieceBudget.allows(List.of(), List.of(a, b)), "separate nested groups");
        check(!NeverNetherPieceBudget.allows(List.of(a), List.of(new Entry("shared", 99))), "weak limit cannot bypass accepted cap");
        check(!NeverNetherPieceBudget.allows(List.of(new Entry("shared", 99)), List.of(a)), "new strong cap enforced");
        List<Entry> accepted = new ArrayList<>();
        for (int i=0; i<50; i++) check(NeverNetherPieceBudget.allows(accepted, List.of(a)), "failed geometry probe consumes nothing");
        accepted.add(a);
        check(!NeverNetherPieceBudget.allows(accepted, List.of(a)), "only accepted geometry counts");
        check(accepted.equals(List.of(a)), "input immutable");
        for (int n=1; n<=20; n++) {
            List<Entry> pieces = new ArrayList<>(); Entry e = new Entry("bounded", n);
            for(int i=0;i<n;i++) { check(NeverNetherPieceBudget.allows(pieces, List.of(e)), "under limit"); pieces.add(e); }
            check(!NeverNetherPieceBudget.allows(pieces, List.of(e)), "at limit");
        }
        invalid(() -> new Entry(null, 1)); invalid(() -> new Entry(" ", 1));
        invalid(() -> new Entry("a", -1)); invalid(() -> new Entry("a", 1025));
        try (var pool = Executors.newFixedThreadPool(8)) {
            List<Callable<Boolean>> starts = new ArrayList<>();
            for(int i=0;i<64;i++) starts.add(() -> {
                List<Entry> own = new ArrayList<>();
                if(!NeverNetherPieceBudget.allows(own, List.of(a))) return false;
                own.add(a);
                return !NeverNetherPieceBudget.allows(own, List.of(a));
            });
            for(var result : pool.invokeAll(starts)) check(result.get(), "independent concurrent starts");
        }
        System.out.println("NeverNether piece budget: " + assertions + " assertions passed; pure Java, not server worldgen");
    }
}
