import java.util.ArrayList;
import net.minecraft.SharedConstants;
import net.minecraft.server.Bootstrap;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.levelgen.placement.NeverNetherDecorationR8;
import net.minecraft.world.level.levelgen.placement.NeverNetherFloraCandidateR8;
import org.bukkit.craftbukkit.util.DelegatedLevelAccessor;

/** Actual registry-based algebra/guard checks, not a generated-world acceptance test. */
public final class NeverNetherCandidateSmoke {
    private static int checks;
    private static void check(boolean value) {if(!value)throw new AssertionError("check "+checks);checks++;}
    public static void main(String[] args) {
        var output=System.out;
        SharedConstants.tryDetectVersion();Bootstrap.bootStrap();
        var states=new ArrayList<BlockState>();
        for(var state:Block.BLOCK_STATE_REGISTRY)if(NeverNetherDecorationR8.isDecoratedPlant(state))states.add(state);
        check(!states.isEmpty());
        for(var a:states) {
            check(NeverNetherFloraCandidateR8.winner(a,a)==a);
            for(var b:states) {
                check(NeverNetherFloraCandidateR8.winner(a,b)==NeverNetherFloraCandidateR8.winner(b,a));
                var c=states.get((Block.getId(a)^Block.getId(b))%states.size());
                check(NeverNetherFloraCandidateR8.winner(NeverNetherFloraCandidateR8.winner(a,b),c)==NeverNetherFloraCandidateR8.winner(a,NeverNetherFloraCandidateR8.winner(b,c)));
            }
        }
        check(NeverNetherFloraCandidateR8.winner(Blocks.CRIMSON_STEM.defaultBlockState(),Blocks.NETHER_WART_BLOCK.defaultBlockState()).is(Blocks.CRIMSON_STEM));
        try {NeverNetherFloraCandidateR8.winner(Blocks.NETHERRACK.defaultBlockState(),states.getFirst());throw new AssertionError("rock accepted as plant");}
        catch(IllegalArgumentException expected){checks++;}
        check(!NeverNetherDecorationR8.inWorld(null));
        var wrapper=new DelegatedLevelAccessor(){};wrapper.setDelegate(wrapper);
        check(!NeverNetherDecorationR8.inWorld(wrapper)); // cyclic wrapper must be bounded
        var random=net.minecraft.util.RandomSource.create(42);
        check(NeverNetherDecorationR8.supportRandom(null,null,null,random)==random);
        check(random.nextLong()==net.minecraft.util.RandomSource.create(42).nextLong());
        output.println("NN-R8 candidate registry/algebra: "+checks+" checks passed for "+states.size()+" plant states; no world generated");
    }
}
