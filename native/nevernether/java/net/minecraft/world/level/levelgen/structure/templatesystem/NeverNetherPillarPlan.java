package net.minecraft.world.level.levelgen.structure.templatesystem;

import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.function.IntFunction;

/** Pure, bounded planning. Never reads/writes chunks or consumes shared randomness. */
public final class NeverNetherPillarPlan {
    private NeverNetherPillarPlan() { }
    public enum Cell { REPLACEABLE, ANCHOR, PROTECTED, UNKNOWN }
    public enum Reason { ANCHORED, NO_ANCHOR, PROTECTED, UNKNOWN, OUT_OF_BOUNDS }
    public record Plan(List<Integer> y, Reason reason) {
        public Plan { y = List.copyOf(y); Objects.requireNonNull(reason); }
    }

    public static Plan plan(int originY, int direction, int minY, int maxY,
                            int maximumLength, IntFunction<Cell> inspect) {
        if ((direction != -1 && direction != 1) || maximumLength < 1 || maximumLength > 1000 || minY > maxY) {
            throw new IllegalArgumentException("Invalid vertical pillar contract");
        }
        Objects.requireNonNull(inspect);
        if (originY < minY || originY > maxY) return new Plan(List.of(), Reason.OUT_OF_BOUNDS);
        var pending = new ArrayList<Integer>();
        // Original trigger is processed separately. A length N allows N-1
        // extension blocks; distance N is inspected only as a potential anchor.
        for (int distance = 1; distance <= maximumLength; distance++) {
            long y = (long) originY + (long) direction * distance;
            if (y < minY || y > maxY) return new Plan(List.of(), Reason.OUT_OF_BOUNDS);
            Cell cell = Objects.requireNonNull(inspect.apply((int) y));
            if (cell == Cell.ANCHOR) return new Plan(pending, Reason.ANCHORED);
            if (cell == Cell.UNKNOWN) return new Plan(List.of(), Reason.UNKNOWN);
            if (cell == Cell.PROTECTED) return new Plan(List.of(), Reason.PROTECTED);
            if (distance < maximumLength) pending.add((int) y);
        }
        return new Plan(List.of(), Reason.NO_ANCHOR);
    }
}
