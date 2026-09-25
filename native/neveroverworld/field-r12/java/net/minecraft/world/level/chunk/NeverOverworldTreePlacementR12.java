package net.minecraft.world.level.chunk;

import java.lang.reflect.InvocationHandler;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.LinkedHashMap;
import java.util.function.Predicate;
import net.minecraft.core.BlockPos;
import net.minecraft.server.level.WorldGenRegion;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.LevelAccessor;
import net.minecraft.world.level.LevelSimulatedReader;
import net.minecraft.world.level.WorldGenLevel;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.levelgen.feature.TreeFeature;
import net.minecraft.world.level.material.FluidState;

/** FIELD-R12 height revision: new standing trees start no lower than ocean-2.
 * Existing trees are never erased. Roots/trunk/foliage are still staged before
 * decorators; only the admission rule changed from a block census to origin Y.
 * No terrain-height queries or neighbouring-block scans decide admission.
 */
public final class NeverOverworldTreePlacementR12 {
    private NeverOverworldTreePlacementR12() {}

    static boolean worldgenScope(WorldGenLevel level) {
        return level instanceof WorldGenRegion
            && level.getLevel().dimension().equals(Level.OVERWORLD)
            && level.getMinY() == -512 && level.getHeight() == 1024;
    }

    public static Proposal begin(WorldGenLevel level, BlockPos origin) {
        return new Proposal(level, worldgenScope(level), origin.getY());
    }

    private static Proposal proposal(Object level) {
        if (!Proxy.isProxyClass(level.getClass())) return null;
        InvocationHandler handler = Proxy.getInvocationHandler(level);
        return handler instanceof Proposal p && p.staging ? p : null;
    }

    public static boolean allowsCandidateWater(LevelSimulatedReader level, BlockPos pos) {
        return pos.getY() <= NeverOverworldFieldPolicyR12.OCEAN_Y && proposal(level) != null;
    }

    /** Only the actual FallenTreeFeature uses this predicate. Horizontal
     * branches on a standing tree never make it a fallen-tree exception. */
    public static boolean fallenPosition(LevelAccessor level, BlockPos pos) {
        if (TreeFeature.validTreePos(level, pos)) return true;
        return pos.getY() <= NeverOverworldFieldPolicyR12.OCEAN_Y
            && level.getBlockState(pos).is(Blocks.WATER)
            && (proposal(level) != null || level instanceof WorldGenLevel w && worldgenScope(w));
    }

    public static final class Proposal implements InvocationHandler {
        private static final int MAX_WRITES = 32768;
        private final WorldGenLevel delegate;
        private final WorldGenLevel view;
        private final boolean heightAllowed;
        private final LinkedHashMap<BlockPos, Write> writes = new LinkedHashMap<>();
        private boolean staging;
        private boolean invalid;
        private record Write(BlockState state, int flags, int limit) {}

        // Package-private native fixture entry; no runtime bypass flag.
        Proposal(WorldGenLevel delegate, boolean enabled, int originY) {
            this.delegate = delegate;
            this.staging = enabled;
            this.heightAllowed = !enabled || NeverOverworldFieldPolicyR12.acceptStandingTree(originY);
            this.view = enabled ? (WorldGenLevel)Proxy.newProxyInstance(
                WorldGenLevel.class.getClassLoader(), new Class<?>[]{WorldGenLevel.class}, this) : delegate;
        }

        public WorldGenLevel view() { return this.view; }

        /** Called before TreeFeature reads its random source or stages blocks. */
        public boolean canStart() { return this.heightAllowed; }

        private BlockState state(BlockPos pos) {
            Write write = writes.get(pos);
            return write == null ? delegate.getBlockState(pos) : write.state();
        }

        @SuppressWarnings("unchecked")
        @Override
        public Object invoke(Object proxy, Method method, Object[] args) throws Throwable {
            if (staging) {
                switch (method.getName()) {
                    case "setBlock": {
                        BlockPos pos = ((BlockPos)args[0]).immutable();
                        if (!delegate.ensureCanWrite(pos) || delegate.isOutsideBuildHeight(pos)
                            || !writes.containsKey(pos) && writes.size() >= MAX_WRITES) {
                            invalid = true;
                            return false;
                        }
                        BlockState state = (BlockState)args[1];
                        // No block-entity or other side-effecting placements are
                        // allowed before admission; vanilla decorators run later.
                        if (state.hasBlockEntity()) throw new IllegalStateException("Tree proposal contains a premature block entity");
                        writes.put(pos, new Write(state, (Integer)args[2], args.length == 4 ? (Integer)args[3] : Block.UPDATE_LIMIT));
                        return true;
                    }
                    case "getBlockState": return state((BlockPos)args[0]);
                    case "getFluidState": return state((BlockPos)args[0]).getFluidState();
                    case "isEmptyBlock": return state((BlockPos)args[0]).isAir();
                    case "isStateAtPosition": return ((Predicate<BlockState>)args[1]).test(state((BlockPos)args[0]));
                    case "isFluidAtPosition": return ((Predicate<FluidState>)args[1]).test(state((BlockPos)args[0]).getFluidState());
                    case "removeBlock", "destroyBlock", "addFreshEntity", "addFreshEntityWithPassengers", "scheduleTick", "setBlockEntity":
                        throw new IllegalStateException("Side effect during unpublished tree proposal: " + method.getName());
                    default: break;
                }
            }
            try {
                return method.invoke(delegate, args);
            } catch (InvocationTargetException ex) {
                throw ex.getCause();
            }
        }

        public boolean acceptAndCommit() {
            if (!staging) return true;
            if (invalid || !canStart()) return false;
            commit();
            return true;
        }

        void commit() {
            if (invalid) throw new IllegalStateException("Cannot publish invalid tree proposal");
            // Validate the whole proposal before publishing any block.
            for (BlockPos pos : writes.keySet()) {
                if (!delegate.ensureCanWrite(pos) || delegate.isOutsideBuildHeight(pos)) {
                    throw new IllegalStateException("Tree proposal lost its worldgen write zone");
                }
            }
            for (var entry : writes.entrySet()) {
                Write write = entry.getValue();
                delegate.setBlock(entry.getKey(), write.state(), write.flags(), write.limit());
            }
            writes.clear();
            staging = false; // Decorators and leaf-distance updates now use vanilla writes.
        }
    }
}
