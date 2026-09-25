package net.minecraft.world.level.levelgen.placement;

import java.lang.reflect.InvocationHandler;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.LinkedHashMap;
import java.util.Set;
import java.util.function.Predicate;
import java.util.stream.Stream;
import net.minecraft.core.BlockPos;
import net.minecraft.resources.Identifier;
import net.minecraft.util.RandomSource;
import net.minecraft.world.level.WorldGenLevel;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.BlockState;

/** EXPERIMENT ONLY. Read-before-decoration view and commutative plant arbitration.
 * Deliberately not installed by the production patch chain. This is not a terrain
 * snapshot: structure/non-flora changes can still affect reads and need separate QA.
 */
public final class NeverNetherFloraCandidateR8 {
    private NeverNetherFloraCandidateR8() { }
    private static final Set<String> IDS = Set.of("crimson_fungus", "warped_fungus", "crimson_forest_vegetation",
        "warped_forest_vegetation", "nether_sprouts", "twisting_vines", "weeping_vines");
    public static boolean handles(PlacedFeature feature, PlacementContext context) {
        Identifier id=feature.feature().unwrapKey().map(key->key.identifier()).orElse(null);
        if (!NeverNetherDecorationR8.inWorld(context.getLevel()) || id==null || !id.getNamespace().equals("minecraft") || !IDS.contains(id.getPath())) return false;
        var configured=feature.feature().value();
        if(configured.feature() instanceof net.minecraft.world.level.levelgen.feature.HugeFungusFeature)
            return configured.config() instanceof net.minecraft.world.level.levelgen.feature.HugeFungusConfiguration huge && !huge.planted;
        return configured.feature() instanceof net.minecraft.world.level.levelgen.feature.NetherForestVegetationFeature
            || configured.feature() instanceof net.minecraft.world.level.levelgen.feature.TwistingVinesFeature
            || configured.feature() instanceof net.minecraft.world.level.levelgen.feature.WeepingVinesFeature;
    }
    private static long mix(long x) { x=(x^(x>>>30))*0xbf58476d1ce4e5b9L;x=(x^(x>>>27))*0x94d049bb133111ebL;return x^(x>>>31); }
    private static RandomSource seed(WorldGenLevel level, String id, BlockPos p) {
        long h=0xcbf29ce484222325L; for(int i=0;i<id.length();i++)h=(h^id.charAt(i))*0x100000001b3L;
        return RandomSource.create(mix(mix(mix(mix(level.getSeed()^h)^((long)p.getX()*0x9e3779b97f4a7c15L))^((long)p.getY()*0xc2b2ae3d27d4eb4fL))^((long)p.getZ()*0x165667b19e3779f9L)));
    }
    public static boolean place(PlacedFeature feature, PlacementContext context, RandomSource random, BlockPos origin) {
        WorldGenLevel actual=context.getLevel();
        View sampling=new View(actual,random);
        PlacementContext sampled=new PlacementContext(sampling.proxy,context.generator(),context.topFeature());
        Stream<BlockPos> positions=Stream.of(origin);
        for(PlacementModifier modifier:feature.placement())positions=positions.flatMap(p->modifier.getPositions(sampled,random,p));
        String id=feature.feature().unwrapKey().orElseThrow().identifier().toString();
        // Fully collect origins before any local output is applied. The supplied
        // count/density modifiers remain unchanged; no chunk-edge rejection.
        var candidates=positions.map(BlockPos::immutable).toList();
        if(candidates.size()>65536)throw new IllegalStateException("Unexpected flora candidate budget");
        boolean any=false;
        for(BlockPos p:candidates) {
            var local=seed(actual,id,p);var planned=new View(actual,local);
            if(feature.feature().value().place(planned.proxy,context.generator(),local,p)) {planned.commit();any=true;}
        }
        return any;
    }
    private static int rank(BlockState state) {
        if(state.is(Blocks.CRIMSON_STEM)||state.is(Blocks.WARPED_STEM))return 8;
        if(state.is(Blocks.SHROOMLIGHT))return 7;
        if(state.is(Blocks.NETHER_WART_BLOCK)||state.is(Blocks.WARPED_WART_BLOCK))return 6;
        if(state.is(Blocks.WEEPING_VINES_PLANT)||state.is(Blocks.TWISTING_VINES_PLANT))return 4;
        if(state.is(Blocks.WEEPING_VINES)||state.is(Blocks.TWISTING_VINES))return 3;
        return 2;
    }
    /** Total-order winner for plant proposals only; no state is filtered from validation. */
    public static BlockState winner(BlockState a, BlockState b) {
        if(!NeverNetherDecorationR8.isDecoratedPlant(a)||!NeverNetherDecorationR8.isDecoratedPlant(b)) throw new IllegalArgumentException("Plant arbitration only");
        int ar=rank(a),br=rank(b);
        return ar>br || ar==br && Block.getId(a)>=Block.getId(b) ? a : b;
    }
    private record Write(BlockState state,int flags,int limit) { }
    private static final class View implements InvocationHandler {
        final WorldGenLevel actual,proxy;
        final RandomSource random;
        final LinkedHashMap<BlockPos,Write> writes=new LinkedHashMap<>();
        View(WorldGenLevel actual,RandomSource random) {
            this.actual=actual;this.random=random;
            proxy=(WorldGenLevel)Proxy.newProxyInstance(WorldGenLevel.class.getClassLoader(),new Class<?>[]{WorldGenLevel.class},this);
        }
        BlockState read(BlockPos p) {
            Write own=writes.get(p);if(own!=null)return own.state();
            BlockState state=actual.getBlockState(p);
            return NeverNetherDecorationR8.isDecoratedPlant(state)?Blocks.AIR.defaultBlockState():state;
        }
        @SuppressWarnings("unchecked")
        @Override public Object invoke(Object self,Method method,Object[] raw)throws Throwable {
            Object[] args=raw==null?new Object[0]:raw;String name=method.getName();
            if(name.equals("getBlockState"))return read((BlockPos)args[0]);
            if(name.equals("getFluidState"))return read((BlockPos)args[0]).getFluidState();
            if(name.equals("isEmptyBlock"))return read((BlockPos)args[0]).isAir();
            if(name.equals("isStateAtPosition"))return ((Predicate<BlockState>)args[1]).test(read((BlockPos)args[0]));
            if(name.equals("isFluidAtPosition"))return ((Predicate<net.minecraft.world.level.material.FluidState>)args[1]).test(read((BlockPos)args[0]).getFluidState());
            if(name.equals("getRandom"))return random;
            if(name.equals("setBlock")) {
                BlockPos pos=((BlockPos)args[0]).immutable();BlockState state=(BlockState)args[1];
                if(!actual.ensureCanWrite(pos))return false;
                if(!state.isAir()&&!NeverNetherDecorationR8.isDecoratedPlant(state))throw new IllegalStateException("Unexpected flora output: "+state);
                if(writes.size()>32768)throw new IllegalStateException("Flora write budget exceeded");
                writes.put(pos,new Write(state,(Integer)args[2],args.length>3?(Integer)args[3]:512));return true;
            }
            if(name.equals("destroyBlock")||name.equals("removeBlock")||name.equals("scheduleTick")||name.equals("addFreshEntity"))
                throw new IllegalStateException("Unexpected side effect in flora planner: "+name);
            if(name.equals("hashCode"))return System.identityHashCode(self);
            if(name.equals("equals"))return self==args[0];
            if(name.equals("toString"))return "NeverNetherR8FloraView";
            if(method.isDefault())return InvocationHandler.invokeDefault(self,method,args);
            try{return method.invoke(actual,args);}catch(InvocationTargetException e){throw e.getCause();}
        }
        void commit() {
            for(var entry:writes.entrySet()) {
                BlockPos p=entry.getKey();Write write=entry.getValue();BlockState next=write.state(),current=actual.getBlockState(p);
                if(next.isAir())continue; // origin clear is a planning operation, not destruction of another tree
                if(current.hasBlockEntity())continue;
                if(NeverNetherDecorationR8.isDecoratedPlant(current)) {
                    if(winner(current,next)==current)continue;
                } else if(!current.isAir() && (!current.canBeReplaced() || !current.getFluidState().isEmpty()))continue;
                actual.setBlock(p,next,write.flags(),write.limit());
            }
        }
    }
}
