import java.util.*;
import net.minecraft.world.level.chunk.OceanConnectivityR399;

public final class ConnectivityTest {
    static int tests;
    static void check(boolean ok,String name){if(!ok)throw new AssertionError(name);tests++;System.out.println("PASS "+name);}
    static int idx(int x,int y,int z,int w,int d){return (y*d+z)*w+x;}
    static BitSet solve(int w,int d,int h,byte[] a,boolean[] sky){return OceanConnectivityR399.solve(w,d,h,a,sky,new BitSet()).connected();}
    public static void main(String[] args) {
        final byte S=1,P=2,A=3,W=4,L=5;
        int w=80,d=80,h=8;byte[] a=new byte[w*d*h];Arrays.fill(a,S);boolean[] sky=new boolean[w*d];
        // Owner x=32..47. Ocean shaft at x=1 (outside old radius-1 witness).
        for(int x=1;x<=40;x++)a[idx(x,2,40,w,d)]=A;
        for(int y=2;y<h;y++)a[idx(1,y,40,w,d)]=W;sky[40*w+1]=true;
        byte[] before=a.clone();BitSet b=solve(w,d,h,a,sky);
        check(b.get(idx(40,2,40,w,d)),"side path two chunks away reaches under roof");
        check(!b.get(idx(40,3,40,w,d)),"solid roof stays blocked");
        check(Arrays.equals(a,before),"immutable input");
        a[idx(20,2,40,w,d)]=P;b=solve(w,d,h,a,sky);
        check(!b.get(idx(40,2,40,w,d)),"protected mine blocks the only path");
        a[idx(20,2,40,w,d)]=S;b=solve(w,d,h,a,sky);
        check(!b.get(idx(40,2,40,w,d)),"sealed cave not flooded");
        a[idx(20,2,40,w,d)]=0;b=solve(w,d,h,a,sky);
        check(!b.get(idx(40,2,40,w,d)),"unknown chunk is not passable");
        a[idx(20,2,40,w,d)]=A;a[idx(20,3,40,w,d)]=L;b=solve(w,d,h,a,sky);
        check(!b.get(idx(40,2,40,w,d)),"lava adjacency interrupts new water");
        a[idx(20,3,40,w,d)]=S;Arrays.fill(sky,false);b=solve(w,d,h,a,sky);
        check(b.isEmpty(),"underground water alone is not an ocean seed");
        sky[40*w+1]=true;b=solve(w,d,h,a,sky);
        for(int i=b.nextSetBit(0);i>=0;i=b.nextSetBit(i+1))if(a[i]==A)a[i]=W;
        check(solve(w,d,h,a,sky).equals(b),"air to water cannot change connectivity");
        byte[] big=new byte[80*80*640];Arrays.fill(big,A);boolean[] open=new boolean[6400];Arrays.fill(open,true);
        check(solve(80,80,640,big,open).cardinality()==big.length,"full 5x5 by 640 height supported");
        // Independently implemented queue oracle on many fixed small random shapes.
        Random r=new Random(399);
        for(int t=0;t<40;t++) {
            int width=3+r.nextInt(7),depth=3+r.nextInt(7),height=2+r.nextInt(8);
            byte[] v=new byte[width*depth*height];for(int i=0;i<v.length;i++)v[i]=(byte)r.nextInt(6);
            boolean[] s=new boolean[width*depth];for(int i=0;i<s.length;i++)s[i]=r.nextBoolean();
            BitSet want=new BitSet();ArrayDeque<int[]> q=new ArrayDeque<>();
            for(int z=0;z<depth;z++)for(int x=0;x<width;x++)if(s[z*width+x])q.add(new int[]{x,height-1,z});
            while(!q.isEmpty()) {
                int[] p=q.remove();int x=p[0],y=p[1],z=p[2];
                if(x<0||x>=width||y<0||y>=height||z<0||z>=depth)continue;
                int i=idx(x,y,z,width,depth);if(want.get(i)||(v[i]!=A&&v[i]!=W))continue;
                int[][] ns={{x-1,y,z},{x+1,y,z},{x,y-1,z},{x,y+1,z},{x,y,z-1},{x,y,z+1}};
                boolean lava=false;for(int[] n:ns)if(n[0]>=0&&n[0]<width&&n[1]>=0&&n[1]<height&&n[2]>=0&&n[2]<depth&&v[idx(n[0],n[1],n[2],width,depth)]==L)lava=true;
                if(lava)continue;want.set(i);for(int[] n:ns)q.add(n);
            }
            check(solve(width,depth,height,v,s).equals(want),"independent 3D oracle "+t);
        }
        System.out.println("R399_TESTS_PASSED="+tests);
    }
}
