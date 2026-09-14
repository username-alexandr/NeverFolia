package net.minecraft.world.level.levelgen.placement;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.function.Predicate;
import net.minecraft.core.BlockPos;
import net.minecraft.util.RandomSource;
import net.minecraft.world.level.WorldGenLevel;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.levelgen.feature.FeaturePlaceContext;
import net.minecraft.world.level.levelgen.feature.GlowstoneFeature;
import net.minecraft.world.level.levelgen.feature.SpringFeature;
import net.minecraft.world.level.levelgen.feature.configurations.NoneFeatureConfiguration;
import net.minecraft.world.level.levelgen.feature.configurations.SpringConfiguration;
import net.minecraft.world.level.material.Fluid;
import net.minecraft.world.level.material.FluidState;
import net.minecraft.world.level.material.Fluids;
import net.minecraft.world.ticks.TickPriority;

/** Optional R12. Proposals use the persisted pre-decoration substrate, never infer
 * ownership from the current material. External writes always retain precedence.
 * Glowstone shape is calculated by the existing feature against its own proposal
 * view; neighboring clusters cannot alter its branching. No live-world adapter.
 */
public final class NeverNetherProposalR12 {
    private NeverNetherProposalR12() { }
    public static boolean handles(WorldGenLevel level) {
        return !(level instanceof Plan) && NeverNetherDecorationR8.inWorld(level);
    }
    public static boolean handlesSpring(FeaturePlaceContext<SpringConfiguration> context) {
        return handles(context.level()) && context.config().state.isSource() && context.config().state.getType() == Fluids.LAVA;
    }
    public static int orePriority(BlockState state) {
        if(state.is(Blocks.NETHER_GOLD_ORE))return 150;
        if(state.is(Blocks.NETHER_QUARTZ_ORE))return 140;
        if(state.is(Blocks.MAGMA_BLOCK))return 130;
        if(state.is(Blocks.BLACKSTONE))return 120;
        if(state.is(Blocks.BASALT))return 110;
        if(state.is(Blocks.GRAVEL))return 100;
        return 0;
    }
    /** Explicit new overlap policy, not original biome-order/balance equivalence. */
    public static int priority(BlockState state) {
        int ore=orePriority(state);if(ore>0)return ore;
        if(state.is(Blocks.LAVA)&&state.getFluidState().isSource())return 200;
        if(state.is(Blocks.GLOWSTONE))return 80;
        if(!NeverNetherDecorationR8.isDecoratedPlant(state))return 0;
        if(state.is(Blocks.CRIMSON_STEM)||state.is(Blocks.WARPED_STEM))return 50;
        if(state.is(Blocks.SHROOMLIGHT))return 45;
        if(state.is(Blocks.NETHER_WART_BLOCK)||state.is(Blocks.WARPED_WART_BLOCK))return 40;
        if(state.is(Blocks.WEEPING_VINES_PLANT)||state.is(Blocks.TWISTING_VINES_PLANT))return 30;
        if(state.is(Blocks.WEEPING_VINES)||state.is(Blocks.TWISTING_VINES))return 25;
        return 20;
    }
    private static long mix(long x) {
        x=(x^(x>>>30))*0xbf58476d1ce4e5b9L;
        x=(x^(x>>>27))*0x94d049bb133111ebL;return x^(x>>>31);
    }
    public static long seed(long worldSeed,BlockPos pos,long salt) {
        long x=mix(worldSeed^salt);
        x=mix(x^(long)pos.getX()*0x9e3779b97f4a7c15L);
        x=mix(x^(long)pos.getY()*0xc2b2ae3d27d4eb4fL);
        return mix(x^(long)pos.getZ()*0x165667b19e3779f9L);
    }
    public static boolean glowstone(GlowstoneFeature feature,FeaturePlaceContext<NoneFeatureConfiguration> context) {
        var random=RandomSource.create(seed(context.level().getSeed(),context.origin(),0x523132474c4f57L));
        var plan=new Plan(context.level(),random,Blocks.GLOWSTONE.defaultBlockState(),1501,false);
        boolean accepted=feature.place(new FeaturePlaceContext<>(context.topFeature(),plan,context.chunkGenerator(),random,context.origin(),context.config()));
        return accepted && plan.commit();
    }
    public static boolean spring(SpringFeature feature,FeaturePlaceContext<SpringConfiguration> context) {
        if(!handlesSpring(context))throw new IllegalArgumentException("R12 accepts natural source lava only");
        var plan=new Plan(context.level(),context.random(),context.config().state.createLegacyBlock(),1,true);
        boolean accepted=feature.place(new FeaturePlaceContext<>(context.topFeature(),plan,context.chunkGenerator(),context.random(),context.origin(),context.config()));
        return accepted && plan.commit();
    }
    private record Write(BlockState state,int flags,int depth) { }
    private record Tick(Fluid fluid,int delay,TickPriority priority) { }
    private static final class Plan extends org.bukkit.craftbukkit.util.DelegatedLevelAccessor {
        private final WorldGenLevel actual;
        private final RandomSource random;
        private final BlockState expected;
        private final int budget;
        private final boolean ticksAllowed;
        private final Map<BlockPos,Write> writes=new LinkedHashMap<>();
        private final Map<BlockPos,Tick> ticks=new LinkedHashMap<>();
        Plan(WorldGenLevel level,RandomSource random,BlockState expected,int budget,boolean ticksAllowed) {
            this.actual=level;this.random=random;this.expected=expected;this.budget=budget;this.ticksAllowed=ticksAllowed;setDelegate(level);
        }
        @Override public BlockState getBlockState(BlockPos pos) {
            Write own=writes.get(pos);return own==null?NeverNetherSubstrateR10.original(actual,pos):own.state();
        }
        @Override public boolean isEmptyBlock(BlockPos p){return getBlockState(p).isAir();}
        @Override public boolean isStateAtPosition(BlockPos p,Predicate<BlockState> test){return test.test(getBlockState(p));}
        @Override public FluidState getFluidState(BlockPos p){return getBlockState(p).getFluidState();}
        @Override public boolean isFluidAtPosition(BlockPos p,Predicate<FluidState> test){return test.test(getFluidState(p));}
        @Override public RandomSource getRandom(){return random;}
        @Override public boolean setBlock(BlockPos pos,BlockState state,int flags){return setBlock(pos,state,flags,512);}
        @Override public boolean setBlock(BlockPos pos,BlockState state,int flags,int depth) {
            if(state!=expected)throw new IllegalArgumentException("Unexpected output of R12 feature: "+state);
            if(!actual.ensureCanWrite(pos))return false;
            if(!writes.containsKey(pos)&&writes.size()>=budget)throw new IllegalStateException("R12 feature budget exceeded");
            writes.put(pos.immutable(),new Write(state,flags,depth));return true;
        }
        @Override public void scheduleTick(BlockPos p,Fluid f,int delay){scheduleTick(p,f,delay,TickPriority.NORMAL);}
        @Override public void scheduleTick(BlockPos p,Fluid f,int delay,TickPriority priority) {
            if(!ticksAllowed||f!=Fluids.LAVA||delay!=0||priority!=TickPriority.NORMAL||!writes.containsKey(p))
                throw new IllegalStateException("Unexpected fluid tick in R12 proposal");
            ticks.put(p.immutable(),new Tick(f,delay,priority));
        }
        boolean commit() {
            boolean accepted=false;
            for(var entry:writes.entrySet()) {
                BlockPos pos=entry.getKey();Write w=entry.getValue();
                if(NeverNetherSubstrateR10.proposeBlock(actual,pos,w.state(),w.flags(),w.depth())) {
                    accepted=true;
                    Tick tick=ticks.get(pos);
                    if(tick!=null&&actual.getBlockState(pos)==w.state())actual.scheduleTick(pos,tick.fluid(),tick.delay(),tick.priority());
                }
            }
            return accepted;
        }
    }
}
