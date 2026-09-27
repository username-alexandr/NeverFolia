import java.util.*;
import net.minecraft.world.level.chunk.SpanOceanR40;

/** Independent per-voxel BFS oracle, not a reimplementation of the span algorithm. */
public final class SpanOceanTest {
    private static int checked;
    public static void main(String[] args) {
        Random random=new Random(4081726L);
        for(int t=0;t<600;t++) {
            int w=1+random.nextInt(11),d=1+random.nextInt(9),h=1+random.nextInt(17);
            byte[] cells=new byte[w*d*h];boolean[] sky=new boolean[w*d];BitSet extra=new BitSet();
            for(int i=0;i<cells.length;i++) {cells[i]=(byte)random.nextInt(8);if(random.nextInt(70)==0)extra.set(i);}
            for(int i=0;i<sky.length;i++)sky[i]=random.nextBoolean();
            compare(w,d,h,cells,sky,extra);
            byte[] switched=cells.clone();for(int i=0;i<switched.length;i++)if(switched[i]==3)switched[i]=4;
            require(SpanOceanR40.solve(w,d,h,cells,sky,extra).connected().equals(SpanOceanR40.solve(w,d,h,switched,sky,extra).connected()),"AIR/WATER reachability changed");
        }
        int w=80,d=80,h=640;byte[] ocean=new byte[w*d*h];Arrays.fill(ocean,(byte)4);boolean[] sky=new boolean[w*d];Arrays.fill(sky,true);
        var large=SpanOceanR40.solve(w,d,h,ocean,sky,new BitSet());
        require(large.visitedCells()==ocean.length&&large.spans()==w*d,"Large uniform ocean should need one span per column");
        // One horizontal tunnel under a sealed roof, connected at its far end.
        w=7;d=3;h=8;byte[] tunnel=new byte[w*d*h];Arrays.fill(tunnel,(byte)1);sky=new boolean[w*d];
        for(int x=0;x<w;x++)tunnel[((1*w+x)*h)+2]=3;
        for(int y=2;y<h;y++)tunnel[((1*w+6)*h)+y]=4;sky[w+6]=true;
        var a=SpanOceanR40.solve(w,d,h,tunnel,sky,new BitSet());require(a.connected().get(w*h+2),"Side opening under roof missed");
        tunnel[((w+4)*h)+2]=2;require(!SpanOceanR40.solve(w,d,h,tunnel,sky,new BitSet()).connected().get(w*h+2),"Protected corridor leaked");
        tunnel[((w+4)*h)+2]=0;require(!SpanOceanR40.solve(w,d,h,tunnel,sky,new BitSet()).connected().get(w*h+2),"Unknown chunk seeded an ocean");
        tunnel[((w+4)*h)+2]=7;require(!SpanOceanR40.solve(w,d,h,tunnel,sky,new BitSet()).connected().get(w*h+2),"Ice was treated as removable");
        tunnel[((w+4)*h)+2]=6;require(SpanOceanR40.solve(w,d,h,tunnel,sky,new BitSet()).connected().get(w*h+2),"Known removable plant blocked an ocean");
        invalid(()->SpanOceanR40.solve(0,1,1,new byte[0],new boolean[0],new BitSet()));
        invalid(()->SpanOceanR40.solve(Integer.MAX_VALUE,Integer.MAX_VALUE,2,new byte[1],new boolean[1],new BitSet()));
        invalid(()->SpanOceanR40.solve(1,1,1,new byte[]{99},new boolean[]{true},new BitSet()));
        invalid(()->SpanOceanR40.solve(1,1,1,new byte[]{3},new boolean[0],new BitSet()));
        BitSet outside=new BitSet();outside.set(1);invalid(()->SpanOceanR40.solve(1,1,1,new byte[]{3},new boolean[]{true},outside));
        System.out.println("SPAN_OCEAN_PASS independent_random_volumes="+checked+" large_volume_cells="+ocean.length+" large_volume_spans="+large.spans());
    }
    private static void compare(int w,int d,int h,byte[] cells,boolean[] sky,BitSet extra) {
        byte[] before=cells.clone();boolean[] oldSky=sky.clone();BitSet oldExtra=(BitSet)extra.clone();
        BitSet expected=oracle(w,d,h,cells,sky,extra);var actual=SpanOceanR40.solve(w,d,h,cells,sky,extra);
        require(expected.equals(actual.connected()),"Independent BFS mismatch at sample "+checked);
        require(expected.cardinality()==actual.visitedCells(),"Incorrect visited count");
        require(Arrays.equals(before,cells)&&Arrays.equals(oldSky,sky)&&oldExtra.equals(extra),"Mutated input snapshot");
        checked++;
    }
    private static BitSet oracle(int w,int d,int h,byte[] cells,boolean[] sky,BitSet extra) {
        BitSet blocked=(BitSet)extra.clone();
        for(int x=0;x<w;x++)for(int z=0;z<d;z++)for(int y=0;y<h;y++) {
            if(cells[(z*w+x)*h+y]!=5)continue;
            for(int[] v:directions())if(valid(x+v[0],z+v[1],y+v[2],w,d,h))blocked.set(((z+v[1])*w+x+v[0])*h+y+v[2]);
        }
        BitSet seen=new BitSet();ArrayDeque<int[]> q=new ArrayDeque<>();
        for(int x=0;x<w;x++)for(int z=0;z<d;z++)if(sky[z*w+x])put(x,z,h-1,w,d,h,cells,blocked,seen,q);
        while(!q.isEmpty()) {int[] p=q.remove();for(int[] v:directions())put(p[0]+v[0],p[1]+v[1],p[2]+v[2],w,d,h,cells,blocked,seen,q);}
        return seen;
    }
    private static boolean valid(int x,int z,int y,int w,int d,int h){return x>=0&&x<w&&z>=0&&z<d&&y>=0&&y<h;}
    private static int[][] directions(){return new int[][]{{1,0,0},{-1,0,0},{0,1,0},{0,-1,0},{0,0,1},{0,0,-1}};}
    private static void put(int x,int z,int y,int w,int d,int h,byte[] cells,BitSet blocked,BitSet seen,ArrayDeque<int[]> q) {
        if(!valid(x,z,y,w,d,h))return;int i=(z*w+x)*h+y;byte s=cells[i];
        if(seen.get(i)||blocked.get(i)||(s!=3&&s!=4&&s!=6))return;
        seen.set(i);q.add(new int[]{x,z,y});
    }
    private static void invalid(Runnable r){try{r.run();throw new AssertionError("Invalid input accepted");}catch(IllegalArgumentException expected){}}
    private static void require(boolean ok,String why){if(!ok)throw new AssertionError(why);}
}
