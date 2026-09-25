import java.lang.reflect.*;
import java.util.*;
import java.util.concurrent.*;
import net.minecraft.SharedConstants;
import net.minecraft.server.Bootstrap;
import net.minecraft.core.*;
import net.minecraft.world.level.biome.*;
import net.minecraft.world.level.block.*;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.chunk.*;
import net.minecraft.world.level.levelgen.placement.NeverNetherSubstrateR10;

/** Native section/provenance/algebra tests with synthetic sections, NOT a world test.
 * Reflective installation is confined to this test; the production-facing hook
 * only captures actual generation chunks at the pre-FEATURES barrier.
 */
public final class NeverNetherCandidateR10Smoke {
    private static int checks;
    private static final BlockPos POS = new BlockPos(-3410,31,-684);
    private static Constructor<?> dataConstructor;
    private static Field ownWrite;
    private static void check(boolean value,String label) { if(!value)throw new AssertionError(label); checks++; }
    private static LevelChunkSection section(BlockState initial) {
        var biome = new Biome.BiomeBuilder().hasPrecipitation(false).temperature(0.5f).downfall(0.0f)
            .generationSettings(BiomeGenerationSettings.EMPTY).mobSpawnSettings(MobSpawnSettings.EMPTY)
            .specialEffects(new BiomeSpecialEffects.Builder().waterColor(0).build()).build();
        var holder = Holder.direct(biome);
        var ids = new IdMapper<Holder<Biome>>(); ids.add(holder);
        return new LevelChunkSection(new PalettedContainer<>(initial,Strategy.createForBlockStates(Block.BLOCK_STATE_REGISTRY)),
            new PalettedContainer<Holder<Biome>>(holder,Strategy.createForBiomes(ids)));
    }
    private static LevelChunkSection captured(BlockState initial) throws Exception {
        var s=section(initial); s.neverNetherR10Data=(NeverNetherSubstrateR10.SectionData)dataConstructor.newInstance(s); return s;
    }
    private static BlockState at(LevelChunkSection s){return s.getBlockState(POS.getX()&15,POS.getY()&15,POS.getZ()&15);}
    private static void set(LevelChunkSection s,BlockState v){s.setBlockState(POS.getX()&15,POS.getY()&15,POS.getZ()&15,v,false);}
    private static void permutations(List<BlockState> prefix,List<BlockState> rest) throws Exception {
        if(rest.isEmpty()) {
            var s=captured(Blocks.NETHERRACK.defaultBlockState());
            for(var p:prefix)check(NeverNetherSubstrateR10.proposeSection(s,POS,p),"eligible proposal");
            check(at(s).is(Blocks.NETHER_GOLD_ORE),"all permutation orders choose gold");
            check(NeverNetherSubstrateR10.original(s,POS).is(Blocks.NETHERRACK),"immutable substrate survives writes");
            check(!s.hasOnlyAir(),"section counters maintained"); return;
        }
        for(int i=0;i<rest.size();i++){
            var next=new ArrayList<>(prefix);next.add(rest.get(i));var remaining=new ArrayList<>(rest);remaining.remove(i);permutations(next,remaining);
        }
    }
    @SuppressWarnings("unchecked") public static void main(String[] args)throws Exception {
        var out=System.out;SharedConstants.tryDetectVersion();Bootstrap.bootStrap();
        Class<?> klass=Class.forName("net.minecraft.world.level.levelgen.placement.NeverNetherSubstrateR10$SectionData");
        dataConstructor=klass.getDeclaredConstructor(LevelChunkSection.class);dataConstructor.setAccessible(true);
        ownWrite=NeverNetherSubstrateR10.class.getDeclaredField("OWN_WRITE");ownWrite.setAccessible(true);
        var values=new ArrayList<BlockState>();
        for(var state:Block.BLOCK_STATE_REGISTRY)if(NeverNetherSubstrateR10.priority(state)>0)values.add(state);
        for(var a:values){check(NeverNetherSubstrateR10.winner(a,a)==a,"idempotent winner");for(var b:values){
            check(NeverNetherSubstrateR10.winner(a,b)==NeverNetherSubstrateR10.winner(b,a),"commutative winner");
            for(var c:values)check(NeverNetherSubstrateR10.winner(NeverNetherSubstrateR10.winner(a,b),c)==NeverNetherSubstrateR10.winner(a,NeverNetherSubstrateR10.winner(b,c)),"associative winner");
        }}
        try {NeverNetherSubstrateR10.winner(Blocks.CHEST.defaultBlockState(),values.getFirst());throw new AssertionError("unrecognized state accepted");}
        catch(IllegalArgumentException expected){checks++;}
        permutations(List.of(),List.of(Blocks.NETHER_GOLD_ORE.defaultBlockState(),Blocks.NETHER_QUARTZ_ORE.defaultBlockState(),Blocks.MAGMA_BLOCK.defaultBlockState(),Blocks.BLACKSTONE.defaultBlockState(),Blocks.BASALT.defaultBlockState()));
        for(boolean sameValue:new boolean[]{false,true}) {
            var s=captured(Blocks.NETHERRACK.defaultBlockState());
            check(NeverNetherSubstrateR10.proposeSection(s,POS,Blocks.NETHER_QUARTZ_ORE.defaultBlockState()),"initial quartz");
            BlockState foreign=sameValue?Blocks.NETHER_QUARTZ_ORE.defaultBlockState():Blocks.BLACKSTONE.defaultBlockState();
            set(s,foreign);
            check(!NeverNetherSubstrateR10.proposeSection(s,POS,Blocks.NETHER_GOLD_ORE.defaultBlockState()),"external direct writer protected even at same value");
            check(at(s)==foreign,"external writer remains intact");
        }
        var chest=captured(Blocks.CHEST.defaultBlockState());
        check(!NeverNetherSubstrateR10.proposeSection(chest,POS,Blocks.NETHER_GOLD_ORE.defaultBlockState()),"block entity protected");
        var s=captured(Blocks.NETHERRACK.defaultBlockState());
        var other=captured(Blocks.NETHERRACK.defaultBlockState());
        NeverNetherSubstrateR10.proposeSection(s,POS,Blocks.MAGMA_BLOCK.defaultBlockState());
        check(at(other).is(Blocks.NETHERRACK),"equal coordinates in different section identities isolated");
        var uncaptured=section(Blocks.NETHERRACK.defaultBlockState());
        try {NeverNetherSubstrateR10.proposeSection(uncaptured,POS,Blocks.MAGMA_BLOCK.defaultBlockState());throw new AssertionError("missing baseline accepted");}
        catch(IllegalStateException expected){checks++;}
        set(uncaptured,Blocks.GOLD_BLOCK.defaultBlockState());check(at(uncaptured).is(Blocks.GOLD_BLOCK),"untracked normal section writes unchanged");
        var concurrent=captured(Blocks.NETHERRACK.defaultBlockState());
        try(var pool=Executors.newFixedThreadPool(4)){
            var tasks=new ArrayList<Callable<Boolean>>();for(int n=0;n<128;n++){var v=values.get(n%values.size());tasks.add(()->NeverNetherSubstrateR10.proposeSection(concurrent,POS,v));}
            for(var f:pool.invokeAll(tasks))check(f.get(),"synchronized independent proposal");
        }
        check(at(concurrent).is(Blocks.NETHER_GOLD_ORE),"concurrent proposals choose same winner");
        check(((ThreadLocal<?>)ownWrite.get(null)).get()==null,"write token does not leak");
        check(!NeverNetherSubstrateR10.scope(null),"unknown/live context not accepted");
        out.println("NN-R10 native section/provenance/algebra: "+checks+" checks passed; no world or restart validation performed");
    }
}
