import java.util.List;
import java.util.concurrent.Executors;
import net.minecraft.world.level.levelgen.structure.templatesystem.NeverNetherPillarPlan;
import static net.minecraft.world.level.levelgen.structure.templatesystem.NeverNetherPillarPlan.*;

public final class NeverNetherPillarPlanTest {
    private static int checks;
    private static void check(boolean ok) { if (!ok) throw new AssertionError("check " + checks); checks++; }
    public static void main(String[] args) throws Exception {
        var simple = plan(10, -1, -123, 378, 1000, y -> y == 5 ? Cell.ANCHOR : Cell.REPLACEABLE);
        check(simple.reason() == Reason.ANCHORED && simple.y().equals(List.of(9, 8, 7, 6)));
        check(plan(0, 1, -123, 378, 5, y -> y == 5 ? Cell.ANCHOR : Cell.REPLACEABLE).y().equals(List.of(1, 2, 3, 4)));
        check(plan(10, -1, -123, 378, 4, y -> y == 5 ? Cell.ANCHOR : Cell.REPLACEABLE).y().isEmpty());
        check(plan(0, -1, -123, 378, 10, y -> Cell.ANCHOR).y().isEmpty());
        check(plan(0, -1, -123, 378, 10, y -> Cell.UNKNOWN).reason() == Reason.UNKNOWN);
        check(plan(0, -1, -123, 378, 10, y -> Cell.PROTECTED).reason() == Reason.PROTECTED);
        check(plan(0, -1, -123, 378, 10, y -> Cell.REPLACEABLE).reason() == Reason.NO_ANCHOR);
        check(plan(-123, -1, -123, 378, 10, y -> { throw new AssertionError("out-of-bounds read"); }).reason() == Reason.OUT_OF_BOUNDS);
        check(plan(378, 1, -123, 378, 10, y -> { throw new AssertionError("roof read"); }).reason() == Reason.OUT_OF_BOUNDS);
        check(plan(379, -1, -123, 378, 10, y -> { throw new AssertionError(); }).reason() == Reason.OUT_OF_BOUNDS);
        for (int origin = -120; origin <= 375; origin += 5) {
            final int y0 = origin;
            for (int dir : new int[]{-1, 1}) {
                var p = plan(origin, dir, -123, 378, 10, y -> y == y0 + 3 * dir ? Cell.ANCHOR : Cell.REPLACEABLE);
                check(p.y().equals(List.of(origin + dir, origin + 2 * dir)));
                final int step = dir;
                var q = plan(origin, dir, -123, 378, 10, y -> y == y0 + step * 2 ? Cell.PROTECTED : Cell.REPLACEABLE);
                check(q.reason() == Reason.PROTECTED && q.y().isEmpty());
            }
        }
        try (var executor = Executors.newFixedThreadPool(4)) {
            var tasks = java.util.stream.IntStream.range(0, 128).mapToObj(i -> (java.util.concurrent.Callable<Boolean>) () ->
                plan(10, -1, -123, 378, 1000, y -> y == 5 ? Cell.ANCHOR : Cell.REPLACEABLE).equals(simple)).toList();
            for (var result : executor.invokeAll(tasks)) check(result.get());
        }
        try { simple.y().add(1); throw new AssertionError(); } catch (UnsupportedOperationException expected) { checks++; }
        System.out.println("NeverNether pillar planner: " + checks + " checks passed; no world access");
    }
}
