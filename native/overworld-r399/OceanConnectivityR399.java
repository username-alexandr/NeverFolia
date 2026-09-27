package net.minecraft.world.level.chunk;

import java.util.BitSet;

/** Bounded positive six-neighbour reachability. Missing space is never an ocean seed. */
public final class OceanConnectivityR399 {
    public static final byte UNKNOWN=0, SOLID=1, PROTECTED=2, AIR=3, WATER=4, LAVA=5;
    private OceanConnectivityR399() {}
    public record Proof(BitSet connected, int visited, int unprovenAir) {}

    public static Proof solve(int width, int depth, int height, byte[] cells,
                              boolean[] openSkyColumns, BitSet extraLavaBarrier) {
        if (width<1 || depth<1 || height<1) throw new IllegalArgumentException("Invalid dimensions");
        int area=Math.multiplyExact(width,depth), count=Math.multiplyExact(area,height);
        if(count>8_000_000 || cells.length!=count || openSkyColumns.length!=area
            || extraLavaBarrier.length()>count) throw new IllegalArgumentException("Invalid bounded ocean volume");
        BitSet blocked=(BitSet)extraLavaBarrier.clone();
        for(int i=0;i<count;i++) {
            if(cells[i]<UNKNOWN || cells[i]>LAVA)throw new IllegalArgumentException("Unknown cell code");
            if(cells[i]!=LAVA)continue;
            int x=i%width,z=(i/width)%depth;
            if(x>0)blocked.set(i-1);if(x+1<width)blocked.set(i+1);
            if(z>0)blocked.set(i-width);if(z+1<depth)blocked.set(i+width);
            if(i>=area)blocked.set(i-area);if(i+area<count)blocked.set(i+area);
        }
        BitSet connected=new BitSet(count);int[] queue=new int[count];int head=0,tail=0;
        int top=(height-1)*area;
        for(int p=0;p<area;p++)if(openSkyColumns[p])tail=offer(top+p,cells,blocked,connected,queue,tail);
        while(head<tail) {
            int i=queue[head++],x=i%width,z=(i/width)%depth;
            if(x>0)tail=offer(i-1,cells,blocked,connected,queue,tail);
            if(x+1<width)tail=offer(i+1,cells,blocked,connected,queue,tail);
            if(z>0)tail=offer(i-width,cells,blocked,connected,queue,tail);
            if(z+1<depth)tail=offer(i+width,cells,blocked,connected,queue,tail);
            if(i>=area)tail=offer(i-area,cells,blocked,connected,queue,tail);
            if(i+area<count)tail=offer(i+area,cells,blocked,connected,queue,tail);
        }
        int unproven=0;for(int i=0;i<count;i++)if(cells[i]==AIR&&!connected.get(i))unproven++;
        return new Proof(connected,tail,unproven);
    }
    private static int offer(int i,byte[] cells,BitSet blocked,BitSet connected,int[] queue,int tail) {
        if(connected.get(i)||blocked.get(i)||(cells[i]!=AIR&&cells[i]!=WATER))return tail;
        connected.set(i);queue[tail++]=i;return tail;
    }
}
