import java.util.*;
import net.minecraft.world.level.chunk.OceanSnapshotR40;

public final class OceanSnapshotTest {
    private static int cases;
    public static void main(String[] args) {
        Random random=new Random(401922L);
        for(int sample=0;sample<32;sample++) {
            byte[] cells=new byte[OceanSnapshotR40.CELLS];boolean[] sky=new boolean[256];BitSet edge=new BitSet();
            for(int i=0;i<cells.length;i++)cells[i]=(byte)random.nextInt(8);
            for(int c=0;c<256;c++){sky[c]=random.nextBoolean();if(random.nextBoolean())edge.set(c*640);if(random.nextBoolean())edge.set(c*640+639);}
            long seed=random.nextLong();int x=random.nextInt(),z=random.nextInt();
            byte[] encoded=OceanSnapshotR40.encode(seed,x,z,cells,sky,edge);
            var read=OceanSnapshotR40.decode(encoded,seed,x,z);
            need(Arrays.equals(cells,read.cells())&&Arrays.equals(sky,read.sky())&&edge.equals(read.boundaryLava()),"Round-trip drift");
            need(Arrays.equals(encoded,OceanSnapshotR40.encode(seed,x,z,cells,sky,edge)),"Unstable encoding");
            invalid(()->OceanSnapshotR40.decode(encoded,seed+1,x,z));
            invalid(()->OceanSnapshotR40.decode(encoded,seed,x^1,z));
            invalid(()->OceanSnapshotR40.decode(encoded,seed,x,z^1));
            invalid(()->OceanSnapshotR40.decode(Arrays.copyOf(encoded,encoded.length/2),seed,x,z));
            byte[] altered=encoded.clone();altered[altered.length/2]^=0x40;invalid(()->OceanSnapshotR40.decode(altered,seed,x,z));
            cases++;
        }
        byte[] cells=new byte[OceanSnapshotR40.CELLS];boolean[] sky=new boolean[256];BitSet edge=new BitSet();
        cells[100]=8;invalid(()->OceanSnapshotR40.encode(1,0,0,cells,sky,edge));cells[100]=0;
        edge.set(3);invalid(()->OceanSnapshotR40.encode(1,0,0,cells,sky,edge));edge.clear();
        invalid(()->OceanSnapshotR40.encode(1,0,0,new byte[1],sky,edge));
        invalid(()->OceanSnapshotR40.decode(new byte[0],1,0,0));
        System.out.println("OCEAN_SNAPSHOT_PASS round_trips="+cases+" corruption_identity_tests="+(cases*5)+" malformed_array_tests=4");
    }
    private static void invalid(Runnable r) {
        try{r.run();throw new AssertionError("Malformed snapshot accepted");}
        catch(IllegalArgumentException|IllegalStateException expected){}
    }
    private static void need(boolean value,String why){if(!value)throw new AssertionError(why);}
}
