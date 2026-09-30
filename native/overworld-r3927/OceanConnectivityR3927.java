package net.minecraft.world.level.chunk;

import java.util.BitSet;

/**
 * R39.27 bounded ocean proof.
 *
 * Two trusted exterior anchors are used:
 *  1) the raised custom sea plane Y=128;
 *  2) broad native-water sheets at the vanilla aquifer sea level Y=63.
 *
 * The second anchor fixes the "air under a floating island" case where the
 * island blocks the Y=128 plane but the same void is still connected downward
 * to the native ocean. Small isolated aquifers are deliberately not seeds.
 *
 * CARVED_AIR is provenance only: a carved cave is traversable from a proven
 * ocean entrance, but a closed carved component remains dry.
 */
public final class OceanConnectivityR3927 {
    public static final byte UNKNOWN=0, SOLID=1, PROTECTED=2, AIR=3, WATER=4, LAVA=5, CARVED_AIR=6;
    private OceanConnectivityR3927() {}

    public record Proof(
        BitSet connected,
        int visited,
        int unprovenAir,
        int nativeSeaSeedCells,
        int nativeSeaComponents,
        int carvedAir,
        int connectedCarvedAir
    ) {}

    private record SeaSeed(int tail,int cells,int components) {}

    public static Proof solve(int width,int depth,int height,byte[] cells,int nativeSeaLayer) {
        int area=Math.multiplyExact(width,depth),count=Math.multiplyExact(area,height);
        if(width<1||depth<1||height<1||count>2_000_000||cells.length!=count
            ||nativeSeaLayer<0||nativeSeaLayer>=height)
            throw new IllegalArgumentException("Invalid R3927 bounded ocean volume");

        BitSet blocked=new BitSet(count);
        int carved=0;
        for(int i=0;i<count;i++) {
            byte c=cells[i];
            if(c<UNKNOWN||c>CARVED_AIR)throw new IllegalArgumentException("Unknown R3927 cell code");
            if(c==CARVED_AIR)carved++;
            if(c!=LAVA)continue;
            blocked.set(i);
            int x=i%width,z=(i/width)%depth;
            if(x>0)blocked.set(i-1);
            if(x+1<width)blocked.set(i+1);
            if(z>0)blocked.set(i-width);
            if(z+1<depth)blocked.set(i+width);
            if(i>=area)blocked.set(i-area);
            if(i+area<count)blocked.set(i+area);
        }

        BitSet connected=new BitSet(count);
        int[] queue=new int[count];
        int tail=0,top=(height-1)*area;

        // Raised custom ocean surface. Unlike R39.25/R40, nothing above this
        // plane participates in the proof.
        for(int p=0;p<area;p++) {
            int i=top+p;
            if(passable(cells[i]))tail=offer(i,cells,blocked,connected,queue,tail);
        }

        // Native ocean fallback under island roofs. A water sheet must be
        // broad or cross at least two edges of the 3x3 witness window.
        SeaSeed sea=seedNativeSea(width,depth,nativeSeaLayer,cells,blocked,connected,queue,tail);
        tail=sea.tail();

        int head=0;
        while(head<tail) {
            int i=queue[head++],x=i%width,z=(i/width)%depth;
            if(x>0)tail=offer(i-1,cells,blocked,connected,queue,tail);
            if(x+1<width)tail=offer(i+1,cells,blocked,connected,queue,tail);
            if(z>0)tail=offer(i-width,cells,blocked,connected,queue,tail);
            if(z+1<depth)tail=offer(i+width,cells,blocked,connected,queue,tail);
            if(i>=area)tail=offer(i-area,cells,blocked,connected,queue,tail);
            if(i+area<count)tail=offer(i+area,cells,blocked,connected,queue,tail);
        }

        int unproven=0,connectedCarved=0;
        for(int i=0;i<count;i++) {
            if((cells[i]==AIR||cells[i]==CARVED_AIR)&&!connected.get(i))unproven++;
            if(cells[i]==CARVED_AIR&&connected.get(i))connectedCarved++;
        }
        return new Proof(connected,tail,unproven,sea.cells(),sea.components(),carved,connectedCarved);
    }

    private static SeaSeed seedNativeSea(
        int width,int depth,int layer,byte[] cells,BitSet blocked,
        BitSet connected,int[] queue,int tail
    ) {
        int area=width*depth,base=layer*area;
        boolean[] seen=new boolean[area];
        int[] component=new int[area];
        int[] work=new int[area];
        int seedCells=0,accepted=0;
        int largeThreshold=Math.max(8,area/18);
        int edgeThreshold=Math.max(4,area/72);

        for(int start=0;start<area;start++) {
            if(seen[start]||cells[base+start]!=WATER||blocked.get(base+start))continue;
            int head=0,end=0,size=0,edges=0;
            seen[start]=true;work[end++]=start;
            while(head<end) {
                int p=work[head++],x=p%width,z=p/width;
                component[size++]=p;
                if(x==0)edges|=1;
                if(x==width-1)edges|=2;
                if(z==0)edges|=4;
                if(z==depth-1)edges|=8;
                if(x>0)end=seaOffer(p-1,base,cells,blocked,seen,work,end);
                if(x+1<width)end=seaOffer(p+1,base,cells,blocked,seen,work,end);
                if(z>0)end=seaOffer(p-width,base,cells,blocked,seen,work,end);
                if(z+1<depth)end=seaOffer(p+width,base,cells,blocked,seen,work,end);
            }
            boolean ocean=size>=largeThreshold
                || (size>=edgeThreshold&&Integer.bitCount(edges)>=2);
            if(!ocean)continue;
            accepted++;
            for(int n=0;n<size;n++) {
                int i=base+component[n];
                int before=tail;
                tail=offer(i,cells,blocked,connected,queue,tail);
                if(tail!=before)seedCells++;
            }
        }
        return new SeaSeed(tail,seedCells,accepted);
    }

    private static int seaOffer(int p,int base,byte[] cells,BitSet blocked,boolean[] seen,int[] work,int end) {
        if(seen[p])return end;
        seen[p]=true;
        if(cells[base+p]==WATER&&!blocked.get(base+p))work[end++]=p;
        return end;
    }

    private static boolean passable(byte c) {
        return c==AIR||c==WATER||c==CARVED_AIR;
    }

    private static int offer(int i,byte[] cells,BitSet blocked,BitSet connected,int[] queue,int tail) {
        if(connected.get(i)||blocked.get(i)||!passable(cells[i]))return tail;
        connected.set(i);
        queue[tail++]=i;
        return tail;
    }
}
