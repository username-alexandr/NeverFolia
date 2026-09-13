import java.lang.reflect.Proxy;
import java.util.HashSet;
import net.minecraft.SharedConstants;
import net.minecraft.core.BlockPos;
import net.minecraft.resources.Identifier;
import net.minecraft.server.Bootstrap;
import net.minecraft.util.RandomSource;
import net.minecraft.world.level.WorldGenLevel;
import net.minecraft.world.level.levelgen.placement.*;

/** Actual native registry/random/guard checks. No world is created by this class. */
public final class NeverNetherCandidateR9Smoke {
    private static int checks;
    private static void check(boolean test){if(!test)throw new AssertionError("check "+checks);checks++;}
    public static void main(String[] args) {
        var out=System.out;
        SharedConstants.tryDetectVersion();Bootstrap.bootStrap();
        WorldGenLevel view=(WorldGenLevel)Proxy.newProxyInstance(WorldGenLevel.class.getClassLoader(),
            new Class<?>[]{WorldGenLevel.class,NeverNetherPlanningViewR9.class},(self,method,argv)->{
                if(method.getName().equals("getSeed"))return 7270913L;
                throw new AssertionError("Unexpected world access: "+method);
            });
        BlockPos root=new BlockPos(-3392,65,-724);
        var legacy=RandomSource.create(42);
        check(NeverNetherFungusRandomR9.at(null,root,root,1,legacy)==legacy);
        check(legacy.nextLong()==RandomSource.create(42).nextLong());
        check(!NeverNetherSupportCandidateR9.matches(null));
        check(NeverNetherSupportCandidateR9.matches(Identifier.fromNamespaceAndPath("nova_structures","blackstone_base")));
        check(!NeverNetherSupportCandidateR9.matches(Identifier.fromNamespaceAndPath("minecraft","blackstone_base")));
        check(!NeverNetherSupportCandidateR9.matches(Identifier.fromNamespaceAndPath("nova_structures","blackstone_bricks_base")));
        check(!NeverNetherSupportCandidateR9.handles(null,null));
        var values=new HashSet<Long>();
        for(int i=-128;i<896;i++) {
            BlockPos cell=new BlockPos(-3392,i,-724);
            long seed=NeverNetherFungusRandomR9.seed(7270913L,root,cell,1);
            check(values.add(seed));
            check(seed==NeverNetherFungusRandomR9.seed(7270913L,root,cell,1));
            check(seed!=NeverNetherFungusRandomR9.seed(7270913L,root,cell.offset(0,4096,0),1));
            check(seed!=NeverNetherFungusRandomR9.seed(7270913L,root.offset(1,0,0),cell,1));
            check(seed!=NeverNetherFungusRandomR9.seed(7270913L,root,cell,2));
            long first=NeverNetherFungusRandomR9.at(view,root,cell,1,legacy).nextLong();
            // Branches at other cells consume any amount of randomness but do
            // not shift the current cell's proposed material or vine choices.
            var other=NeverNetherFungusRandomR9.at(view,root,cell.offset(1,0,0),1,legacy);
            for(int j=0;j<(i&15);j++)other.nextInt();
            check(first==NeverNetherFungusRandomR9.at(view,root,cell,1,legacy).nextLong());
        }
        out.println("NN-R9 native candidate: "+checks+" checks passed; no generated world acceptance");
    }
}
